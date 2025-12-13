"""
NPC 对话编排器

核心职责：
1. 加载 NPC 人设
2. 通过 MCP 工具检索相关知识
3. 构建证据链
4. 构建 Prompt
5. 调用 LLM（支持 Tool Calling）
6. 应用护栏检查
7. 管理会话记忆
8. 返回带证据链的响应
"""

from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from app.core.config import settings
from app.core.logging import get_logger
from app.integrations.llm import get_llm_client, LLMClient
from app.memory.session import SessionMemory
from app.prompts.builder import PromptBuilder
from app.retrieval.knowledge import KnowledgeRetriever
from app.guardrails.cultural import CulturalGuardrail
from app.mcp.protocol import MCPToolCall, MCPToolResult
from app.mcp.tool_client import MCPToolClient, get_mcp_client
from app.evidence.chain import EvidenceChainBuilder, EvidenceChainResult
from app.evidence.validator import EvidenceValidator, ValidationLevel

logger = get_logger(__name__)


class NPCOrchestrator:
    """NPC 对话编排器"""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        knowledge_retriever: Optional[KnowledgeRetriever] = None,
        session_memory: Optional[SessionMemory] = None,
        guardrail: Optional[CulturalGuardrail] = None,
        mcp_client: Optional[MCPToolClient] = None,
    ):
        self.llm = llm_client or get_llm_client()
        self.retriever = knowledge_retriever or KnowledgeRetriever()
        self.memory = session_memory or SessionMemory()
        self.guardrail = guardrail or CulturalGuardrail()
        self.prompt_builder = PromptBuilder()
        self.mcp_client = mcp_client or get_mcp_client()
        self.evidence_builder = EvidenceChainBuilder(
            min_evidence_count=settings.MIN_EVIDENCE_COUNT,
            min_confidence_threshold=settings.MIN_CONFIDENCE_THRESHOLD,
        )
        self.evidence_validator = EvidenceValidator(
            level=ValidationLevel.NORMAL,
            min_confidence=settings.MIN_CONFIDENCE_THRESHOLD,
            require_verified_for_history=settings.REQUIRE_VERIFIED_FOR_HISTORY,
        )

    async def chat(
        self,
        npc_id: UUID,
        npc_persona: dict[str, Any],
        user_message: str,
        session_id: str,
        visitor_id: Optional[UUID] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        处理 NPC 对话请求

        Args:
            npc_id: NPC ID
            npc_persona: NPC 人设配置
            user_message: 用户消息
            session_id: 会话 ID
            visitor_id: 游客 ID（可选）
            context: 额外上下文（场景、时间等）

        Returns:
            对话响应，包含回复内容和元数据
        """
        logger.info(
            "processing_chat",
            npc_id=str(npc_id),
            session_id=session_id,
            message_length=len(user_message),
        )

        # 1. 获取会话历史
        history = await self.memory.get_history(session_id)

        # 2. 检索相关知识
        knowledge_domains = npc_persona.get("knowledge_domains", [])
        relevant_docs = await self.retriever.search(
            query=user_message,
            domains=knowledge_domains,
            top_k=3,
        )

        # 3. 构建 Prompt
        messages = self.prompt_builder.build(
            persona=npc_persona,
            user_message=user_message,
            history=history,
            retrieved_docs=relevant_docs,
            context=context,
        )

        # 4. 调用 LLM
        response = await self.llm.chat(
            messages=messages,
            temperature=settings.TEMPERATURE,
            max_tokens=settings.MAX_RESPONSE_TOKENS,
        )

        # 5. 护栏检查
        guardrail_result = await self.guardrail.check(
            response=response.content,
            persona=npc_persona,
        )

        if not guardrail_result.passed:
            logger.warning(
                "guardrail_triggered",
                npc_id=str(npc_id),
                reason=guardrail_result.reason,
            )
            # 使用兜底回复
            fallback_responses = npc_persona.get("conversation_config", {}).get(
                "fallback_responses", ["抱歉，这个问题我不太清楚。"]
            )
            response_content = fallback_responses[0] if fallback_responses else "抱歉，请换个问题。"
        else:
            response_content = response.content

        # 6. 保存到会话记忆
        await self.memory.add_message(session_id, "user", user_message)
        await self.memory.add_message(session_id, "assistant", response_content)

        return {
            "content": response_content,
            "npc_id": str(npc_id),
            "session_id": session_id,
            "sources": [doc.get("title", "") for doc in relevant_docs],
            "guardrail_passed": guardrail_result.passed,
            "tokens_used": response.usage.total_tokens if response.usage else None,
        }

    async def chat_with_mcp(
        self,
        npc_id: UUID,
        npc_persona: Dict[str, Any],
        user_message: str,
        session_id: str,
        trace_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        site_id: Optional[str] = None,
        visitor_id: Optional[UUID] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        使用 MCP 工具的 NPC 对话（推荐使用此方法）

        与 chat() 的区别：
        1. 通过 MCP 工具调用 core-backend 获取知识
        2. 构建证据链并验证
        3. 证据不足时使用保守回答
        4. 返回 evidence_ids 用于追溯

        Args:
            npc_id: NPC ID
            npc_persona: NPC 人设配置
            user_message: 用户消息
            session_id: 会话 ID
            trace_id: 追踪 ID
            tenant_id: 租户 ID
            site_id: 站点 ID
            visitor_id: 游客 ID
            context: 额外上下文

        Returns:
            对话响应，包含 evidence_ids
        """
        trace_id = trace_id or str(uuid4())

        logger.info(
            "processing_chat_with_mcp",
            npc_id=str(npc_id),
            session_id=session_id,
            trace_id=trace_id,
        )

        # 1. 获取会话历史
        history = await self.memory.get_history(session_id)

        # 2. 通过 MCP 工具检索知识
        knowledge_domains = npc_persona.get("knowledge_domains", [])
        tool_results = await self._execute_knowledge_search(
            query=user_message,
            domains=knowledge_domains,
            trace_id=trace_id,
            tenant_id=tenant_id,
            site_id=site_id,
            session_id=session_id,
        )

        # 3. 构建证据链
        evidence_result = self.evidence_builder.build_from_tool_results(
            tool_results=tool_results,
            trace_id=trace_id,
        )

        # 4. 验证证据
        query_classification = self.evidence_validator.classify_query(
            query=user_message,
            knowledge_domains=knowledge_domains,
        )
        validation_result = self.evidence_validator.validate(
            evidence_result=evidence_result,
            query_type=query_classification.get("query_type"),
            knowledge_domains=knowledge_domains,
        )

        # 5. 如果证据不足，使用保守回答
        if validation_result.should_use_fallback:
            logger.warning(
                "insufficient_evidence",
                trace_id=trace_id,
                reason=validation_result.reason,
                confidence=validation_result.confidence,
            )

            fallback_responses = npc_persona.get("conversation_config", {}).get(
                "fallback_responses", []
            )
            response_content = self.evidence_validator.get_fallback_response(
                validation_result=validation_result,
                topic=user_message[:50],
                knowledge_domains=knowledge_domains,
                custom_fallbacks=fallback_responses,
            )

            await self.memory.add_message(session_id, "user", user_message)
            await self.memory.add_message(session_id, "assistant", response_content)

            return {
                "content": response_content,
                "npc_id": str(npc_id),
                "session_id": session_id,
                "trace_id": trace_id,
                "evidence_ids": validation_result.evidence_ids,
                "evidence_sufficient": False,
                "confidence": validation_result.confidence,
                "guardrail_passed": True,
                "fallback_used": True,
            }

        # 6. 从证据中提取知识文档
        relevant_docs = [
            {
                "id": e.id,
                "title": e.title,
                "content": e.content_snippet,
                "source": e.source,
            }
            for e in evidence_result.evidence_chain.evidences
        ]

        # 7. 构建 Prompt
        messages = self.prompt_builder.build(
            persona=npc_persona,
            user_message=user_message,
            history=history,
            retrieved_docs=relevant_docs,
            context=context,
        )

        # 8. 调用 LLM
        response = await self.llm.chat(
            messages=messages,
            temperature=settings.TEMPERATURE,
            max_tokens=settings.MAX_RESPONSE_TOKENS,
        )

        # 9. 护栏检查
        guardrail_result = await self.guardrail.check(
            response=response.content,
            persona=npc_persona,
        )

        if not guardrail_result.passed:
            logger.warning(
                "guardrail_triggered",
                npc_id=str(npc_id),
                trace_id=trace_id,
                reason=guardrail_result.reason,
            )
            fallback_responses = npc_persona.get("conversation_config", {}).get(
                "fallback_responses", ["抱歉，这个问题我不太清楚。"]
            )
            response_content = fallback_responses[0] if fallback_responses else "抱歉，请换个问题。"
        else:
            response_content = response.content

        # 10. 保存到会话记忆
        await self.memory.add_message(session_id, "user", user_message)
        await self.memory.add_message(session_id, "assistant", response_content)

        return {
            "content": response_content,
            "npc_id": str(npc_id),
            "session_id": session_id,
            "trace_id": trace_id,
            "evidence_ids": [e.id for e in evidence_result.evidence_chain.evidences],
            "evidence_sufficient": True,
            "confidence": evidence_result.confidence_score,
            "sources": [doc.get("title", "") for doc in relevant_docs],
            "guardrail_passed": guardrail_result.passed,
            "fallback_used": False,
            "tokens_used": response.usage.total_tokens if response.usage else None,
        }

    async def _execute_knowledge_search(
        self,
        query: str,
        domains: List[str],
        trace_id: str,
        tenant_id: Optional[str] = None,
        site_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> List[MCPToolResult]:
        """通过 MCP 工具执行知识检索"""
        tool_call = MCPToolCall(
            tool_name="knowledge.search",
            params={
                "query": query,
                "domains": domains,
                "top_k": 5,
                "min_score": 0.6,
            },
            trace_id=trace_id,
            tenant_id=tenant_id or settings.DEFAULT_TENANT_ID,
            site_id=site_id or settings.DEFAULT_SITE_ID,
            session_id=session_id,
        )

        result = await self.mcp_client.execute(tool_call)
        return [result]

    async def get_greeting(
        self,
        npc_persona: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """获取 NPC 问候语"""
        templates = npc_persona.get("conversation_config", {}).get("greeting_templates", [])
        if templates:
            # TODO: 根据上下文选择合适的问候语
            return templates[0]
        return "你好！有什么可以帮助你的吗？"
