"""
Agent Runtime

NPC 对话闭环实现：
1. 获取 NPC 人设
2. 获取 Prompt
3. 检索证据
4. 调用 LLM 生成
5. 输出校验
6. 记录事件 + 写入 trace_ledger
7. 返回响应
"""

import time
import structlog
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.tools import (
    ToolClient,
    get_tool_client,
    ToolContext,
    ResilientToolClient,
    get_resilient_tool_client,
)
from app.tools.client import generate_trace_id
from app.tools.schemas import NPCProfile, ContentItem, EvidenceItem, PromptInfo
from app.llm import get_llm_adapter, BaseLLMAdapter
from app.llm.base import LLMResponse as LegacyLLMResponse
from app.providers.llm import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMError,
    LLMErrorType,
    get_llm_provider,
)
from app.agent.schemas import (
    ChatRequest,
    ChatResponse,
    PolicyMode,
    CitationItem,
)
from app.agent.validator import OutputValidator

logger = structlog.get_logger(__name__)


class AgentRuntime:
    """
    Agent Runtime

    实现 NPC 对话闭环
    """

    def __init__(
        self,
        tool_client: Optional[ResilientToolClient] = None,
        llm_provider: Optional[LLMProvider] = None,
        validator: Optional[OutputValidator] = None,
        use_legacy_adapter: bool = False,
        use_resilient_client: bool = True,
    ):
        # 使用弹性客户端（带缓存、超时、重试、降级）
        if use_resilient_client:
            self.tool_client = tool_client or get_resilient_tool_client()
        else:
            self.tool_client = tool_client or get_tool_client()
        self._use_legacy_adapter = use_legacy_adapter
        self._use_resilient_client = use_resilient_client

        if use_legacy_adapter:
            # 兼容旧的 LLM Adapter
            self._legacy_adapter = get_llm_adapter()
            self.llm_provider = None
        else:
            # 使用新的 LLM Provider
            self.llm_provider = llm_provider or get_llm_provider(
                sandbox_mode=settings.LLM_SANDBOX_MODE
            )
            self._legacy_adapter = None

        self.validator = validator or OutputValidator(
            min_evidence_count=settings.MIN_EVIDENCE_COUNT,
            min_confidence_threshold=settings.MIN_CONFIDENCE_THRESHOLD,
            require_verified_for_history=settings.REQUIRE_VERIFIED_FOR_HISTORY,
        )

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """
        处理对话请求

        完整流程：
        1. 生成/使用 trace_id 和 session_id
        2. 获取 NPC 人设
        3. 获取 Prompt
        4. 获取会话历史（多轮对话记忆）
        5. 检索证据
        6. 调用 LLM 生成
        7. 输出校验
        8. 保存会话记忆
        9. 记录事件 + 写入 trace_ledger
        10. 返回响应
        """
        start_time = time.time()

        # 1. 生成 trace_id 和 session_id
        trace_id = request.trace_id or generate_trace_id()
        session_id = request.session_id or self._generate_session_id()

        # 构建工具调用上下文
        ctx = ToolContext(
            tenant_id=request.tenant_id,
            site_id=request.site_id,
            trace_id=trace_id,
            user_id=request.user_id,
            session_id=session_id,
            npc_id=request.npc_id,
        )

        log = logger.bind(
            trace_id=trace_id,
            npc_id=request.npc_id,
            tenant_id=request.tenant_id,
            site_id=request.site_id,
        )
        log.info("chat_start", query=request.query[:50])

        tool_calls = []
        evidence_ids = []
        citations = []

        try:
            # 2. 获取 NPC 人设
            log.info("step_get_npc_profile")
            npc_profile = await self.tool_client.get_npc_profile(request.npc_id, ctx)
            tool_calls.append({"name": "get_npc_profile", "status": "success" if npc_profile else "error"})

            if not npc_profile:
                return self._build_error_response(
                    trace_id=trace_id,
                    error=f"NPC not found: {request.npc_id}",
                    latency_ms=self._calc_latency(start_time),
                )

            # 3. 获取 Prompt（从 Prompt Registry 加载）
            log.info("step_get_prompt")
            prompt_info = await self.tool_client.get_prompt_active(request.npc_id, ctx, "system")
            prompt_version = prompt_info.version if prompt_info else None
            prompt_source = prompt_info.metadata.get("source", "unknown") if prompt_info else None
            tool_calls.append({
                "name": "get_prompt_active",
                "status": "success" if prompt_info else "error",
                "version": prompt_version,
                "source": prompt_source,
            })

            system_prompt = prompt_info.prompt_text if prompt_info else self._build_default_prompt(npc_profile)

            # 从 prompt policy 获取配置（如果来自 registry）
            prompt_policy = {}
            if prompt_info and prompt_info.metadata.get("source") == "prompt_registry":
                prompt_policy = prompt_info.metadata.get("policy", {})

            # 4. 获取会话历史（多轮对话记忆，NPC 隔离）
            conversation_context = ""
            if settings.MEMORY_ENABLED:
                log.info("step_get_session_memory", npc_id=request.npc_id)
                conversation_context = await self._get_conversation_context(
                    tenant_id=request.tenant_id,
                    site_id=request.site_id,
                    session_id=session_id,
                    npc_id=request.npc_id,  # NPC 隔离
                    npc_name=npc_profile.display_name or npc_profile.name,
                )
                if conversation_context:
                    tool_calls.append({"name": "get_session_memory", "status": "success", "npc_id": request.npc_id})

            # 5. 检索证据
            log.info("step_retrieve_evidence")
            evidences = await self._retrieve_evidence(request.query, npc_profile, ctx)
            tool_calls.append({"name": "retrieve_evidence", "status": "success", "count": len(evidences)})

            # 转换为引用格式
            citations = [
                CitationItem(
                    evidence_id=e.id,
                    title=e.title,
                    source_ref=e.source_ref,
                    excerpt=e.excerpt[:100] if e.excerpt else None,
                    confidence=e.confidence,
                )
                for e in evidences
            ]
            evidence_ids = [e.id for e in evidences]

            # 5.5 证据闸门检查（Evidence Gate）
            log.info("step_evidence_gate")
            from app.guardrails import get_evidence_gate, QueryIntent
            evidence_gate = get_evidence_gate()
            gate_result = evidence_gate.check_before_llm(request.query, citations)
            tool_calls.append({
                "name": "evidence_gate",
                "status": "passed" if gate_result.passed else "blocked",
                "intent": gate_result.intent.value,
                "citations_count": gate_result.citations_count,
                "reason": gate_result.reason,
            })

            # 如果证据闸门未通过，强制保守模式
            if not gate_result.passed:
                log.warning("evidence_gate_blocked", reason=gate_result.reason)
                answer_text = evidence_gate.get_conservative_response(
                    intent=gate_result.intent,
                    query=request.query,
                    npc_name=npc_profile.display_name or npc_profile.name,
                )
                policy_mode = PolicyMode.CONSERVATIVE
                latency_ms = self._calc_latency(start_time)

                # 跳过 LLM 调用，直接返回保守响应
                await self._log_and_trace(
                    ctx=ctx,
                    request=request,
                    tool_calls=tool_calls,
                    evidence_ids=evidence_ids,
                    policy_mode=policy_mode,
                    answer_text=answer_text,
                    latency_ms=latency_ms,
                    prompt_version=prompt_version,
                    prompt_source=prompt_source,
                )

                return ChatResponse(
                    trace_id=trace_id,
                    session_id=session_id,
                    policy_mode=policy_mode,
                    answer_text=answer_text,
                    citations=[],
                    followup_questions=[],
                    npc_name=npc_profile.display_name or npc_profile.name,
                    latency_ms=latency_ms,
                )

            # 6. 调用 LLM 生成（拼接会话上下文）
            log.info("step_llm_generate")
            # 将会话历史拼接到 system_prompt
            full_system_prompt = system_prompt
            if conversation_context:
                full_system_prompt = f"{system_prompt}\n\n{conversation_context}"

            llm_result = await self._call_llm(
                system_prompt=full_system_prompt,
                user_message=request.query,
                npc_profile=npc_profile,
                citations=citations,
                trace_id=trace_id,
                prompt_policy=prompt_policy,
            )

            llm_response = llm_result["response"]
            llm_error = llm_result.get("error")
            llm_fallback = llm_result.get("fallback", False)

            # 记录 LLM 调用信息到 tool_calls
            tool_calls.append({
                "name": "llm_generate",
                "status": "fallback" if llm_fallback else ("error" if llm_error else "success"),
                "provider": llm_result.get("provider", "unknown"),
                "model": llm_result.get("model", "unknown"),
                "tokens_input": llm_response.tokens_input if hasattr(llm_response, 'tokens_input') else 0,
                "tokens_output": llm_response.tokens_output if hasattr(llm_response, 'tokens_output') else 0,
                "latency_ms": llm_response.latency_ms if hasattr(llm_response, 'latency_ms') else 0,
                "error": str(llm_error) if llm_error else None,
            })

            # 6.5 LLM 输出后的证据闸门检查
            post_gate_result = evidence_gate.check_after_llm(
                query=request.query,
                response_text=llm_response.text,
                citations=citations,
                intent=gate_result.intent,
            )

            # 如果检测到无证据的史实断言，过滤或降级
            if not post_gate_result.passed:
                log.warning(
                    "post_llm_gate_blocked",
                    forbidden_assertions=post_gate_result.forbidden_assertions,
                )
                if gate_result.requires_filtering:
                    # 过滤禁止的断言
                    llm_response.text = evidence_gate.filter_forbidden_assertions(
                        llm_response.text,
                        npc_name=npc_profile.display_name or npc_profile.name,
                    )
                tool_calls.append({
                    "name": "post_evidence_gate",
                    "status": "filtered",
                    "forbidden_assertions": post_gate_result.forbidden_assertions[:3],
                })

            # 7. 输出校验
            log.info("step_validate")
            validation = self.validator.validate(
                text=llm_response.text,
                citations=citations,
                query=request.query,
                npc_persona=npc_profile.persona,
            )

            # 根据校验结果确定最终输出
            if validation.policy_mode == PolicyMode.REFUSE:
                answer_text = validation.filtered_text or "抱歉，这个问题不在我的知识范围内。"
                policy_mode = PolicyMode.REFUSE
                citations = []  # 拒绝时不返回引用
            elif validation.policy_mode == PolicyMode.CONSERVATIVE:
                answer_text = validation.filtered_text or llm_response.text
                policy_mode = PolicyMode.CONSERVATIVE
            else:
                answer_text = llm_response.text
                policy_mode = PolicyMode.NORMAL

            latency_ms = self._calc_latency(start_time)

            # 7. 合并工具审计记录
            if self._use_resilient_client and hasattr(self.tool_client, 'get_audits'):
                tool_audits = self.tool_client.get_audits()
                tool_calls.extend(tool_audits)
                self.tool_client.clear_audits()

            # 8. 保存会话记忆
            if settings.MEMORY_ENABLED:
                log.info("step_save_session_memory")
                await self._save_conversation_turn(
                    tenant_id=request.tenant_id,
                    site_id=request.site_id,
                    session_id=session_id,
                    user_query=request.query,
                    assistant_response=answer_text,
                    npc_id=request.npc_id,
                    trace_id=trace_id,
                )

            # 9. 记录事件 + 写入 trace_ledger（包含 prompt version）
            log.info("step_log_and_trace", prompt_version=prompt_version)
            await self._log_and_trace(
                ctx=ctx,
                request=request,
                tool_calls=tool_calls,
                evidence_ids=evidence_ids,
                policy_mode=policy_mode,
                answer_text=answer_text,
                latency_ms=latency_ms,
                prompt_version=prompt_version,
                prompt_source=prompt_source,
            )

            # 10. 构建响应
            followup_questions = self._generate_followup_questions(
                query=request.query,
                npc_profile=npc_profile,
                evidences=evidences,
            )

            log.info("chat_complete", policy_mode=policy_mode.value, latency_ms=latency_ms)

            return ChatResponse(
                trace_id=trace_id,
                session_id=session_id,
                policy_mode=policy_mode,
                answer_text=answer_text,
                citations=citations if policy_mode == PolicyMode.NORMAL else [],
                followup_questions=followup_questions,
                npc_name=npc_profile.display_name or npc_profile.name,
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = self._calc_latency(start_time)
            log.error("chat_error", error=str(e), latency_ms=latency_ms)

            # 记录错误到 trace_ledger
            await self._log_and_trace(
                ctx=ctx,
                request=request,
                tool_calls=tool_calls,
                evidence_ids=evidence_ids,
                policy_mode=PolicyMode.CONSERVATIVE,
                answer_text="",
                latency_ms=latency_ms,
                error=str(e),
            )

            return self._build_error_response(
                trace_id=trace_id,
                error=str(e),
                latency_ms=latency_ms,
            )

    async def _retrieve_evidence(
        self,
        query: str,
        npc_profile: NPCProfile,
        ctx: ToolContext,
    ) -> List[EvidenceItem]:
        """检索证据"""
        # 尝试使用 retrieve_evidence 工具
        evidences = await self.tool_client.retrieve_evidence(
            query=query,
            ctx=ctx,
            domains=npc_profile.knowledge_domains,
            limit=5,
        )

        if evidences:
            return evidences

        # 如果 retrieve_evidence 不可用，回退到 search_content
        contents = await self.tool_client.search_content(
            query=query,
            ctx=ctx,
            limit=5,
        )

        # 将 content 转换为 evidence 格式
        return [
            EvidenceItem(
                id=c.id,
                source_type="knowledge_base",
                source_ref=f"content:{c.id}",
                title=c.title,
                excerpt=c.body[:300] if c.body else "",
                confidence=c.credibility_score,
                verified=c.verified,
                tags=c.tags,
            )
            for c in contents
        ]

    async def _call_llm(
        self,
        system_prompt: str,
        user_message: str,
        npc_profile: NPCProfile,
        citations: List[CitationItem],
        trace_id: str,
        prompt_policy: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        调用 LLM 生成回复

        支持：
        - 新的 LLMProvider 接口
        - 旧的 LLM Adapter 兼容
        - 降级处理（LLM 不可用时返回保守回复）
        - 审计记录
        """
        log = logger.bind(trace_id=trace_id, npc_id=npc_profile.npc_id)

        # 构建引用列表
        citation_dicts = [
            {
                "id": c.evidence_id,
                "title": c.title,
                "source_ref": c.source_ref,
                "excerpt": c.excerpt,
            }
            for c in citations
        ]

        # 获取保守模式模板
        conservative_template = prompt_policy.get(
            "conservative_template",
            "这个问题我不太清楚，建议您询问村中其他长辈或查阅相关文献。"
        )

        if self._use_legacy_adapter and self._legacy_adapter:
            # 使用旧的 LLM Adapter
            try:
                legacy_response = await self._legacy_adapter.generate(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    context={
                        "npc_name": npc_profile.display_name or npc_profile.name,
                        "npc_type": npc_profile.npc_type,
                        "knowledge_domains": npc_profile.knowledge_domains,
                    },
                    citations=citation_dicts,
                    max_tokens=npc_profile.max_response_length or 500,
                )
                return {
                    "response": legacy_response,
                    "provider": "legacy",
                    "model": getattr(legacy_response, 'model', 'unknown'),
                    "fallback": False,
                }
            except Exception as e:
                log.error("legacy_llm_error", error=str(e))
                if settings.LLM_FALLBACK_ENABLED:
                    return self._build_fallback_response(conservative_template, e)
                raise

        # 使用新的 LLM Provider
        if not self.llm_provider:
            log.error("llm_provider_not_configured")
            return self._build_fallback_response(conservative_template, None)

        try:
            llm_request = LLMRequest(
                system_prompt=system_prompt,
                user_message=user_message,
                context={
                    "npc_name": npc_profile.display_name or npc_profile.name,
                    "npc_type": npc_profile.npc_type,
                    "knowledge_domains": npc_profile.knowledge_domains,
                },
                citations=citation_dicts,
                max_tokens=npc_profile.max_response_length or 500,
                temperature=settings.TEMPERATURE,
                trace_id=trace_id,
                npc_id=npc_profile.npc_id,
            )

            llm_response = await self.llm_provider.generate(llm_request)

            log.info(
                "llm_generate_success",
                provider=self.llm_provider.provider_name,
                model=self.llm_provider.model_name,
                tokens_input=llm_response.tokens_input,
                tokens_output=llm_response.tokens_output,
                latency_ms=llm_response.latency_ms,
            )

            return {
                "response": llm_response,
                "provider": self.llm_provider.provider_name,
                "model": self.llm_provider.model_name,
                "fallback": False,
            }

        except LLMError as e:
            log.error(
                "llm_generate_error",
                error_type=e.error_type.value,
                error=e.message,
                retryable=e.retryable,
            )

            if settings.LLM_FALLBACK_ENABLED:
                return self._build_fallback_response(conservative_template, e)
            raise

        except Exception as e:
            log.error("llm_unexpected_error", error=str(e))

            if settings.LLM_FALLBACK_ENABLED:
                return self._build_fallback_response(conservative_template, e)
            raise

    def _build_fallback_response(
        self,
        conservative_template: str,
        error: Optional[Exception],
    ) -> Dict[str, Any]:
        """构建降级响应"""
        return {
            "response": LLMResponse(
                text=conservative_template,
                model="fallback",
                tokens_input=0,
                tokens_output=0,
                finish_reason="fallback",
                latency_ms=0,
            ),
            "provider": "fallback",
            "model": "fallback",
            "fallback": True,
            "error": error,
        }

    def _build_default_prompt(self, npc_profile: NPCProfile) -> str:
        """构建默认 Prompt"""
        persona = npc_profile.persona or {}
        identity = persona.get("identity", {})
        personality = persona.get("personality", {})

        parts = [
            f"你是{npc_profile.display_name or npc_profile.name}。",
        ]

        if identity.get("era"):
            parts.append(f"你生活在{identity['era']}。")
        if identity.get("role"):
            parts.append(f"你的身份是{identity['role']}。")
        if identity.get("background"):
            parts.append(f"背景：{identity['background']}")
        if personality.get("traits"):
            parts.append(f"你的性格特点：{'、'.join(personality['traits'])}。")
        if personality.get("speaking_style"):
            parts.append(f"说话风格：{personality['speaking_style']}")
        if npc_profile.knowledge_domains:
            parts.append(f"你擅长的领域：{'、'.join(npc_profile.knowledge_domains)}。")
        if npc_profile.must_cite_sources:
            parts.append("回答时请引用可靠来源。")

        return "\n".join(parts)

    async def _log_and_trace(
        self,
        ctx: ToolContext,
        request: ChatRequest,
        tool_calls: List[Dict[str, Any]],
        evidence_ids: List[str],
        policy_mode: PolicyMode,
        answer_text: str,
        latency_ms: int,
        error: Optional[str] = None,
        prompt_version: Optional[int] = None,
        prompt_source: Optional[str] = None,
        persona_version: Optional[int] = None,
    ) -> None:
        """记录事件和追踪（包含 npc_id、persona_version、prompt_version）"""
        # 记录用户事件
        await self.tool_client.log_user_event(
            event_type="npc_chat",
            ctx=ctx,
            event_data={
                "npc_id": request.npc_id,
                "query": request.query[:100],
                "policy_mode": policy_mode.value,
                "evidence_count": len(evidence_ids),
                "prompt_version": prompt_version,
                "prompt_source": prompt_source,
                "persona_version": persona_version,
            },
        )

        # 写入 trace_ledger（包含 npc_id、persona_version、prompt_version）
        await self.tool_client.create_trace(
            ctx=ctx,
            request_type="npc_chat",
            request_input={
                "query": request.query,
                "npc_id": request.npc_id,
                "session_id": ctx.session_id,
                "prompt_version": prompt_version,
                "prompt_source": prompt_source,
                "persona_version": persona_version,
            },
            tool_calls=tool_calls,
            evidence_ids=evidence_ids,
            policy_mode=policy_mode.value,
            response_output={"answer_text": answer_text[:500]} if answer_text else None,
            latency_ms=latency_ms,
            status="error" if error else "success",
            error=error,
        )

    def _generate_followup_questions(
        self,
        query: str,
        npc_profile: NPCProfile,
        evidences: List[EvidenceItem],
    ) -> List[str]:
        """生成后续问题建议"""
        questions = []

        # 基于知识领域生成问题
        for domain in npc_profile.knowledge_domains[:2]:
            questions.append(f"能给我讲讲{domain}吗？")

        # 基于证据生成问题
        for e in evidences[:1]:
            if e.title:
                questions.append(f"关于{e.title}，还有什么有趣的故事吗？")

        return questions[:3]

    def _build_error_response(
        self,
        trace_id: str,
        error: str,
        latency_ms: int,
        session_id: str = "",
    ) -> ChatResponse:
        """构建错误响应"""
        return ChatResponse(
            trace_id=trace_id,
            session_id=session_id or self._generate_session_id(),
            policy_mode=PolicyMode.CONSERVATIVE,
            answer_text="抱歉，系统暂时无法处理您的请求，请稍后再试。",
            citations=[],
            followup_questions=[],
            latency_ms=latency_ms,
        )

    def _calc_latency(self, start_time: float) -> int:
        """计算延迟（毫秒）"""
        return int((time.time() - start_time) * 1000)

    def _generate_session_id(self) -> str:
        """生成 session_id"""
        import uuid
        return f"session-{uuid.uuid4().hex[:16]}"

    async def _get_conversation_context(
        self,
        tenant_id: str,
        site_id: str,
        session_id: str,
        npc_id: str,
        npc_name: str,
    ) -> str:
        """
        获取会话上下文（NPC 隔离 + 偏好记忆）

        重要：明确标注仅供上下文，不作为事实依据
        """
        try:
            from app.memory import get_session_memory, get_preference_memory

            memory = await get_session_memory()
            pref_memory = await get_preference_memory()

            # 获取 NPC 隔离的短记忆
            messages = await memory.get_recent_messages(
                tenant_id=tenant_id,
                site_id=site_id,
                session_id=session_id,
                npc_id=npc_id,  # NPC 隔离
            )

            # 获取跨 NPC 共享的偏好记忆
            preference = await pref_memory.get_preference(
                tenant_id=tenant_id,
                site_id=site_id,
                session_id=session_id,
            )

            parts = []

            # 添加偏好记忆
            pref_prompt = preference.to_prompt_format()
            if pref_prompt:
                parts.append(pref_prompt)

            # 添加短记忆
            if messages:
                short_prompt = memory.build_context_prompt(messages, npc_name)
                parts.append(short_prompt)

            return "\n\n".join(parts) if parts else ""

        except Exception as e:
            logger.warning("get_conversation_context_failed", error=str(e))
            return ""

    async def _save_conversation_turn(
        self,
        tenant_id: str,
        site_id: str,
        session_id: str,
        user_query: str,
        assistant_response: str,
        npc_id: str,
        trace_id: str,
    ) -> None:
        """保存对话轮次到会话记忆（NPC 隔离）"""
        try:
            from app.memory import get_session_memory, Message, MessageRole

            memory = await get_session_memory()

            # 保存用户消息（NPC 隔离）
            await memory.append_message(
                tenant_id=tenant_id,
                site_id=site_id,
                session_id=session_id,
                npc_id=npc_id,  # NPC 隔离
                message=Message(
                    role=MessageRole.USER,
                    content=user_query,
                    npc_id=npc_id,
                    trace_id=trace_id,
                ),
            )

            # 保存助手回复（NPC 隔离）
            await memory.append_message(
                tenant_id=tenant_id,
                site_id=site_id,
                session_id=session_id,
                npc_id=npc_id,  # NPC 隔离
                message=Message(
                    role=MessageRole.ASSISTANT,
                    content=assistant_response,
                    npc_id=npc_id,
                    trace_id=trace_id,
                ),
            )

        except Exception as e:
            logger.warning("save_conversation_turn_failed", error=str(e))
