"""
工具执行器

负责执行工具调用、审计记录、错误处理
"""

import hashlib
import json
import time
import structlog
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.schemas import (
    ToolContext,
    ToolCallRequest,
    ToolCallResponse,
    ToolAudit,
    GetNPCProfileInput,
    GetNPCProfileOutput,
    SearchContentInput,
    SearchContentOutput,
    ContentItem,
    GetSiteMapInput,
    GetSiteMapOutput,
    POIItem,
    CreateDraftContentInput,
    CreateDraftContentOutput,
    LogUserEventInput,
    LogUserEventOutput,
    GetPromptActiveInput,
    GetPromptActiveOutput,
    RetrieveEvidenceInput,
    RetrieveEvidenceOutput,
    EvidenceItem,
    SubmitFeedbackInput,
    SubmitFeedbackOutput,
    ListFeedbackInput,
    ListFeedbackOutput,
    FeedbackItem,
)
from app.tools.registry import ToolRegistry, get_tool_registry
from app.database.models import (
    NPCProfile,
    Content,
    TraceLedger,
    PolicyMode,
)
from app.database.models.user_feedback import UserFeedback, FeedbackStatus

logger = structlog.get_logger(__name__)


class ToolExecutor:
    """工具执行器"""

    def __init__(self, session: AsyncSession, registry: Optional[ToolRegistry] = None):
        self.session = session
        self.registry = registry or get_tool_registry()

    async def execute(self, request: ToolCallRequest) -> ToolCallResponse:
        """
        执行工具调用

        1. 验证工具存在
        2. 校验输入参数
        3. 执行工具逻辑
        4. 记录审计日志
        5. 返回结果
        """
        start_time = time.time()
        ctx = request.context

        # 结构化日志
        log = logger.bind(
            trace_id=ctx.trace_id,
            tool_name=request.tool_name,
            tenant_id=ctx.tenant_id,
            site_id=ctx.site_id,
            user_id=ctx.user_id,
        )

        # 计算请求 payload hash
        payload_hash = self._hash_payload(request.input)

        try:
            # 1. 获取工具定义
            tool_def = self.registry.get(request.tool_name)
            if not tool_def:
                raise ValueError(f"Unknown tool: {request.tool_name}")

            # 2. 校验输入
            validated_input = tool_def.input_schema(**request.input)

            # 3. 执行工具
            log.info("tool_call_start")
            output = await self._dispatch(request.tool_name, validated_input, ctx)

            # 4. 计算延迟
            latency_ms = int((time.time() - start_time) * 1000)

            # 5. 记录审计
            audit = ToolAudit(
                trace_id=ctx.trace_id,
                tool_name=request.tool_name,
                status="success",
                latency_ms=latency_ms,
                request_payload_hash=payload_hash,
            )
            await self._record_audit(ctx, request.tool_name, audit, output)

            log.info("tool_call_success", latency_ms=latency_ms)

            return ToolCallResponse(
                success=True,
                output=output if isinstance(output, dict) else output.model_dump(),
                audit=audit,
            )

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_type = type(e).__name__
            error_message = str(e)

            audit = ToolAudit(
                trace_id=ctx.trace_id,
                tool_name=request.tool_name,
                status="error",
                latency_ms=latency_ms,
                error_type=error_type,
                error_message=error_message,
                request_payload_hash=payload_hash,
            )
            await self._record_audit(ctx, request.tool_name, audit, None, error_message)

            log.error("tool_call_error", error_type=error_type, error=error_message)

            return ToolCallResponse(
                success=False,
                error=error_message,
                error_type=error_type,
                audit=audit,
            )

    async def _dispatch(
        self,
        tool_name: str,
        validated_input: Any,
        ctx: ToolContext,
    ) -> Any:
        """分发到具体工具实现"""
        handlers = {
            "get_npc_profile": self._handle_get_npc_profile,
            "search_content": self._handle_search_content,
            "get_site_map": self._handle_get_site_map,
            "create_draft_content": self._handle_create_draft_content,
            "log_user_event": self._handle_log_user_event,
            "get_prompt_active": self._handle_get_prompt_active,
            "retrieve_evidence": self._handle_retrieve_evidence,
            "submit_feedback": self._handle_submit_feedback,
            "list_feedback": self._handle_list_feedback,
        }

        handler = handlers.get(tool_name)
        if not handler:
            raise NotImplementedError(f"Tool handler not implemented: {tool_name}")

        return await handler(validated_input, ctx)

    # ============================================================
    # 工具实现
    # ============================================================

    async def _handle_get_npc_profile(
        self,
        input: GetNPCProfileInput,
        ctx: ToolContext,
    ) -> GetNPCProfileOutput:
        """获取 NPC 人设"""
        stmt = select(NPCProfile).where(
            NPCProfile.tenant_id == ctx.tenant_id,
            NPCProfile.site_id == ctx.site_id,
            NPCProfile.npc_id == input.npc_id,
            NPCProfile.deleted_at.is_(None),
        )

        if input.version is not None:
            stmt = stmt.where(NPCProfile.version == input.version)
        else:
            stmt = stmt.where(NPCProfile.active == True)

        result = await self.session.execute(stmt)
        profile = result.scalar_one_or_none()

        if not profile:
            raise ValueError(f"NPC profile not found: {input.npc_id}")

        return GetNPCProfileOutput(
            npc_id=profile.npc_id,
            version=profile.version,
            active=profile.active,
            name=profile.name,
            display_name=profile.display_name,
            npc_type=profile.npc_type,
            persona=profile.persona,
            knowledge_domains=profile.knowledge_domains or [],
            greeting_templates=profile.greeting_templates or [],
            fallback_responses=profile.fallback_responses or [],
            max_response_length=profile.max_response_length,
            must_cite_sources=profile.must_cite_sources,
        )

    async def _handle_search_content(
        self,
        input: SearchContentInput,
        ctx: ToolContext,
    ) -> SearchContentOutput:
        """
        搜索内容
        
        P0 稳定性保证：
        - 任何搜索失败都不抛 500
        - 异常时返回空结果
        """
        log = logger.bind(query=input.query[:50], trace_id=ctx.trace_id)
        
        try:
            like_pattern = f"%{input.query}%"

            stmt = select(Content).where(
                Content.tenant_id == ctx.tenant_id,
                Content.site_id == ctx.site_id,
                Content.deleted_at.is_(None),
                (Content.title.ilike(like_pattern) | Content.body.ilike(like_pattern)),
            )

            if input.content_type:
                stmt = stmt.where(Content.content_type == input.content_type)
            if input.status:
                stmt = stmt.where(Content.status == input.status)
            if input.tags:
                stmt = stmt.where(Content.tags.overlap(input.tags))

            stmt = stmt.order_by(Content.credibility_score.desc()).limit(input.limit)

            result = await self.session.execute(stmt)
            contents = result.scalars().all()

            items = [
                ContentItem(
                    id=str(c.id),
                    content_type=c.content_type,
                    title=c.title,
                    summary=c.summary,
                    body=c.body[:500] if c.body and len(c.body) > 500 else (c.body or ""),
                    tags=c.tags or [],
                    domains=c.domains or [],
                    credibility_score=c.credibility_score,
                    verified=c.verified,
                )
                for c in contents
            ]

            log.info("search_content_success", hit_count=len(items))

            return SearchContentOutput(
                items=items,
                total=len(items),
                query=input.query,
            )
        except Exception as e:
            log.error("search_content_error", error=str(e))
            # 返回空结果，不抛异常
            return SearchContentOutput(
                items=[],
                total=0,
                query=input.query,
            )

    async def _handle_get_site_map(
        self,
        input: GetSiteMapInput,
        ctx: ToolContext,
    ) -> GetSiteMapOutput:
        """获取站点地图"""
        from app.database.models import Site

        # 获取站点信息
        site_stmt = select(Site).where(
            Site.id == ctx.site_id,
            Site.tenant_id == ctx.tenant_id,
        )
        site_result = await self.session.execute(site_stmt)
        site = site_result.scalar_one_or_none()

        if not site:
            raise ValueError(f"Site not found: {ctx.site_id}")

        pois = []
        routes = []

        if input.include_pois:
            # 从 content 表获取 POI 类型的内容
            poi_stmt = select(Content).where(
                Content.tenant_id == ctx.tenant_id,
                Content.site_id == ctx.site_id,
                Content.content_type == "poi",
                Content.status == "published",
                Content.deleted_at.is_(None),
            )
            poi_result = await self.session.execute(poi_stmt)
            poi_contents = poi_result.scalars().all()

            pois = [
                POIItem(
                    id=str(c.id),
                    name=c.title,
                    type=c.category or "default",
                    description=c.summary,
                )
                for c in poi_contents
            ]

        if input.include_routes:
            # 从 content 表获取 route 类型的内容
            route_stmt = select(Content).where(
                Content.tenant_id == ctx.tenant_id,
                Content.site_id == ctx.site_id,
                Content.content_type == "route",
                Content.status == "published",
                Content.deleted_at.is_(None),
            )
            route_result = await self.session.execute(route_stmt)
            route_contents = route_result.scalars().all()

            routes = [
                {"id": str(c.id), "name": c.title, "description": c.summary}
                for c in route_contents
            ]

        return GetSiteMapOutput(
            site_id=site.id,
            site_name=site.name,
            pois=pois,
            routes=routes,
        )

    async def _handle_create_draft_content(
        self,
        input: CreateDraftContentInput,
        ctx: ToolContext,
    ) -> CreateDraftContentOutput:
        """创建草稿内容"""
        content = Content(
            tenant_id=ctx.tenant_id,
            site_id=ctx.site_id,
            content_type=input.content_type,
            title=input.title,
            body=input.body,
            summary=input.summary,
            tags=input.tags,
            domains=input.domains,
            source=input.source,
            status="draft",
            created_by=ctx.user_id or "system",
        )

        self.session.add(content)
        await self.session.flush()
        await self.session.refresh(content)

        return CreateDraftContentOutput(
            content_id=str(content.id),
            status=content.status,
            created_at=content.created_at,
        )

    async def _handle_log_user_event(
        self,
        input: LogUserEventInput,
        ctx: ToolContext,
    ) -> LogUserEventOutput:
        """记录用户事件"""
        from app.database.models.analytics_event import AnalyticsEvent

        event = AnalyticsEvent(
            tenant_id=ctx.tenant_id,
            site_id=ctx.site_id,
            trace_id=ctx.trace_id,
            user_id=input.user_id or ctx.user_id,
            session_id=input.session_id or ctx.session_id,
            event_type=input.event_type,
            event_data=input.event_data,
        )

        self.session.add(event)
        await self.session.flush()
        await self.session.refresh(event)

        return LogUserEventOutput(
            event_id=str(event.id),
            logged_at=event.created_at,
        )

    async def _handle_get_prompt_active(
        self,
        input: GetPromptActiveInput,
        ctx: ToolContext,
    ) -> GetPromptActiveOutput:
        """
        获取 NPC 当前激活的 Prompt

        优先从 npc_prompts 表（Prompt Registry）加载
        如果不存在，回退到 npc_profiles 表
        """
        from app.database.models import NPCPrompt

        # 1. 优先从 Prompt Registry 加载
        stmt = select(NPCPrompt).where(
            NPCPrompt.tenant_id == ctx.tenant_id,
            NPCPrompt.site_id == ctx.site_id,
            NPCPrompt.npc_id == input.npc_id,
            NPCPrompt.active == True,
            NPCPrompt.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        prompt_record = result.scalar_one_or_none()

        if prompt_record:
            # 从 Prompt Registry 返回
            policy = prompt_record.policy or {}
            meta = prompt_record.meta or {}

            return GetPromptActiveOutput(
                npc_id=prompt_record.npc_id,
                prompt_type=input.prompt_type,
                prompt_text=prompt_record.content,
                version=prompt_record.version,
                metadata={
                    "source": "prompt_registry",
                    "name": meta.get("name"),
                    "description": prompt_record.description,
                    "author": prompt_record.author,
                    "policy": policy,
                    "require_citations": policy.get("require_citations", True),
                    "max_response_length": policy.get("max_response_length", 500),
                    "forbidden_topics": policy.get("forbidden_topics", []),
                    "conservative_template": policy.get("conservative_template"),
                },
            )

        # 2. 回退到 NPC Profile
        stmt = select(NPCProfile).where(
            NPCProfile.tenant_id == ctx.tenant_id,
            NPCProfile.site_id == ctx.site_id,
            NPCProfile.npc_id == input.npc_id,
            NPCProfile.active == True,
            NPCProfile.deleted_at.is_(None),
        )

        result = await self.session.execute(stmt)
        profile = result.scalar_one_or_none()

        if not profile:
            raise ValueError(f"NPC profile not found: {input.npc_id}")

        # 根据 prompt_type 构建 prompt 文本
        persona = profile.persona or {}
        identity = persona.get("identity", {})
        personality = persona.get("personality", {})
        constraints = persona.get("constraints", {})

        if input.prompt_type == "system":
            prompt_text = self._build_system_prompt(profile, identity, personality, constraints)
        elif input.prompt_type == "greeting":
            templates = profile.greeting_templates or []
            prompt_text = templates[0] if templates else f"你好，我是{profile.display_name or profile.name}。"
        elif input.prompt_type == "fallback":
            responses = profile.fallback_responses or []
            prompt_text = responses[0] if responses else "抱歉，这个问题我不太清楚。"
        else:
            raise ValueError(f"Unknown prompt_type: {input.prompt_type}")

        return GetPromptActiveOutput(
            npc_id=profile.npc_id,
            prompt_type=input.prompt_type,
            prompt_text=prompt_text,
            version=profile.version,
            metadata={
                "source": "npc_profile",
                "name": profile.name,
                "display_name": profile.display_name,
                "npc_type": profile.npc_type,
                "knowledge_domains": profile.knowledge_domains or [],
                "max_response_length": profile.max_response_length,
                "must_cite_sources": profile.must_cite_sources,
            },
        )

    async def _handle_retrieve_evidence(
        self,
        input: RetrieveEvidenceInput,
        ctx: ToolContext,
    ) -> RetrieveEvidenceOutput:
        """
        检索证据
        
        P0 稳定性保证：
        - 任何检索失败都不抛 500
        - Qdrant 不可用时自动降级到 trgm
        - 所有异常都被捕获并记录

        支持三种检索策略：
        1. trgm: pg_trgm 相似度搜索
        2. qdrant: Qdrant 向量语义检索
        3. hybrid: 混合检索（trgm + qdrant）
        """
        from app.core.config import settings

        original_strategy = input.strategy
        strategy = original_strategy
        if not strategy or strategy not in ("trgm", "qdrant", "hybrid"):
            strategy = settings.RETRIEVAL_STRATEGY
        
        log = logger.bind(
            query=input.query[:50],
            original_strategy=original_strategy,
            strategy=strategy,
            trace_id=ctx.trace_id,
        )

        fallback_reason = None
        strategy_used = strategy

        # 向后兼容：use_trgm=False 时使用 LIKE
        if not input.use_trgm and strategy == "trgm":
            try:
                return await self._retrieve_evidence_like(input, ctx, log)
            except Exception as e:
                log.error("retrieve_evidence_like_error", error=str(e))
                # LIKE 失败返回空结果，不抛异常
                return self._empty_evidence_output(
                    input.query, "like", "like_error", str(e)
                )

        if strategy == "trgm":
            try:
                return await self._retrieve_evidence_trgm(input, ctx, log)
            except Exception as e:
                log.error("retrieve_evidence_trgm_error", error=str(e))
                return self._empty_evidence_output(
                    input.query, "trgm", "trgm_error", str(e)
                )

        # qdrant 或 hybrid 策略：需要兜底
        if strategy == "qdrant":
            try:
                result = await self._retrieve_evidence_qdrant_safe(input, ctx, log)
                if result is not None:
                    return result
                # Qdrant 不可用，fallback 到 trgm
                fallback_reason = "qdrant_unavailable"
                strategy_used = "trgm_fallback"
            except Exception as e:
                log.warning("retrieve_evidence_qdrant_fallback", error=str(e))
                fallback_reason = f"qdrant_error: {str(e)[:100]}"
                strategy_used = "trgm_fallback"

        elif strategy == "hybrid":
            try:
                result = await self._retrieve_evidence_hybrid_safe(input, ctx, log)
                if result is not None:
                    return result
                # Hybrid 失败，fallback 到 trgm
                fallback_reason = "hybrid_unavailable"
                strategy_used = "trgm_fallback"
            except Exception as e:
                log.warning("retrieve_evidence_hybrid_fallback", error=str(e))
                fallback_reason = f"hybrid_error: {str(e)[:100]}"
                strategy_used = "trgm_fallback"

        # Fallback 到 trgm
        log.warning(
            "retrieve_evidence_fallback_trgm",
            original_strategy=strategy,
            fallback_reason=fallback_reason,
        )
        try:
            result = await self._retrieve_evidence_trgm(input, ctx, log)
            # 标记为 fallback
            result.strategy_used = strategy_used
            result.fallback_reason = fallback_reason
            return result
        except Exception as e:
            log.error("retrieve_evidence_trgm_fallback_error", error=str(e))
            return self._empty_evidence_output(
                input.query, strategy_used, fallback_reason, str(e)
            )

    def _empty_evidence_output(
        self,
        query: str,
        strategy_used: str,
        fallback_reason: str,
        error: str,
    ) -> RetrieveEvidenceOutput:
        """返回空的证据输出（用于错误兜底）"""
        return RetrieveEvidenceOutput(
            items=[],
            total=0,
            query=query,
            strategy_used=strategy_used,
            search_method=strategy_used,
            fallback_reason=fallback_reason,
            score_distribution=None,
        )

    async def _retrieve_evidence_qdrant_safe(
        self,
        input: RetrieveEvidenceInput,
        ctx: ToolContext,
        log,
    ) -> Optional[RetrieveEvidenceOutput]:
        """
        安全的 Qdrant 检索（不抛异常）
        
        返回 None 表示需要 fallback
        """
        from app.retrieval.qdrant_client import get_qdrant_client

        try:
            qdrant = get_qdrant_client()
            
            # 检查 Qdrant 可用性
            if not qdrant.is_available:
                log.warning("qdrant_not_available", error=qdrant.last_error)
                return None

            results = await qdrant.search(
                query=input.query,
                tenant_id=ctx.tenant_id,
                site_id=ctx.site_id,
                limit=input.limit,
                min_score=input.min_score,
                domains=input.domains,
            )

            # 如果 Qdrant 返回空结果但没有错误，仍然是有效结果
            items = [
                EvidenceItem(
                    id=r.id,
                    source_type=r.source_type,
                    source_ref=r.source_ref,
                    title=r.title,
                    excerpt=r.excerpt[:300] if r.excerpt and len(r.excerpt) > 300 else r.excerpt,
                    confidence=r.confidence,
                    verified=r.verified,
                    tags=r.tags,
                    retrieval_score=r.score,
                    qdrant_score=r.qdrant_score if hasattr(r, 'qdrant_score') else r.score,
                )
                for r in results
            ]

            scores = [r.score for r in results]
            score_distribution = None
            if scores:
                score_distribution = {
                    "min": min(scores),
                    "max": max(scores),
                    "avg": sum(scores) / len(scores),
                    "count": len(scores),
                }

            log.info("retrieve_evidence_qdrant_success", hit_count=len(items))

            return RetrieveEvidenceOutput(
                items=items,
                total=len(items),
                query=input.query,
                strategy_used="qdrant",
                search_method="qdrant",
                score_distribution=score_distribution,
            )

        except Exception as e:
            log.warning("retrieve_evidence_qdrant_error", error=str(e))
            return None

    async def _retrieve_evidence_hybrid_safe(
        self,
        input: RetrieveEvidenceInput,
        ctx: ToolContext,
        log,
    ) -> Optional[RetrieveEvidenceOutput]:
        """
        安全的 Hybrid 检索（不抛异常）
        
        返回 None 表示需要 fallback
        """
        from app.retrieval.hybrid import HybridRetriever
        from app.retrieval.qdrant_client import get_qdrant_client

        try:
            qdrant = get_qdrant_client()
            
            # 检查 Qdrant 可用性（hybrid 需要 qdrant）
            if not qdrant.is_available:
                log.warning("hybrid_qdrant_not_available", error=qdrant.last_error)
                return None

            hybrid = HybridRetriever(
                session=self.session,
                qdrant_client=qdrant,
            )

            results = await hybrid.search(
                query=input.query,
                tenant_id=ctx.tenant_id,
                site_id=ctx.site_id,
                limit=input.limit,
                min_score=input.min_score,
                domains=input.domains,
            )

            items = [
                EvidenceItem(
                    id=r.id,
                    source_type=r.source_type,
                    source_ref=r.source_ref,
                    title=r.title,
                    excerpt=r.excerpt[:300] if r.excerpt and len(r.excerpt) > 300 else r.excerpt,
                    confidence=r.confidence,
                    verified=r.verified,
                    tags=r.tags,
                    retrieval_score=r.score,
                    trgm_score=r.trgm_score if hasattr(r, 'trgm_score') else None,
                    qdrant_score=r.qdrant_score if hasattr(r, 'qdrant_score') else None,
                )
                for r in results
            ]

            scores = [r.score for r in results]
            score_distribution = None
            if scores:
                score_distribution = {
                    "min": min(scores),
                    "max": max(scores),
                    "avg": sum(scores) / len(scores),
                    "count": len(scores),
                    "trgm_hits": sum(1 for r in results if hasattr(r, 'trgm_score') and r.trgm_score),
                    "qdrant_hits": sum(1 for r in results if hasattr(r, 'qdrant_score') and r.qdrant_score),
                }

            log.info("retrieve_evidence_hybrid_success", hit_count=len(items))

            return RetrieveEvidenceOutput(
                items=items,
                total=len(items),
                query=input.query,
                strategy_used="hybrid",
                search_method="hybrid",
                score_distribution=score_distribution,
            )

        except Exception as e:
            log.warning("retrieve_evidence_hybrid_error", error=str(e))
            return None

    async def _retrieve_evidence_trgm(
        self,
        input: RetrieveEvidenceInput,
        ctx: ToolContext,
        log,
    ) -> RetrieveEvidenceOutput:
        """使用 pg_trgm 相似度搜索"""
        from sqlalchemy import text

        # 构建原生 SQL 查询，使用 similarity() 函数
        # GREATEST 取 title 和 excerpt 相似度的最大值
        sql = text("""
            SELECT
                id,
                source_type,
                source_ref,
                title,
                excerpt,
                confidence,
                verified,
                tags,
                GREATEST(
                    COALESCE(similarity(title, :query), 0),
                    COALESCE(similarity(excerpt, :query), 0)
                ) AS retrieval_score
            FROM evidences
            WHERE tenant_id = :tenant_id
              AND site_id = :site_id
              AND deleted_at IS NULL
              AND (
                  title % :query
                  OR excerpt % :query
              )
              AND GREATEST(
                  COALESCE(similarity(title, :query), 0),
                  COALESCE(similarity(excerpt, :query), 0)
              ) >= :min_score
        """)

        # 添加 domains 过滤
        if input.domains:
            sql = text("""
                SELECT
                    id,
                    source_type,
                    source_ref,
                    title,
                    excerpt,
                    confidence,
                    verified,
                    tags,
                    GREATEST(
                        COALESCE(similarity(title, :query), 0),
                        COALESCE(similarity(excerpt, :query), 0)
                    ) AS retrieval_score
                FROM evidences
                WHERE tenant_id = :tenant_id
                  AND site_id = :site_id
                  AND deleted_at IS NULL
                  AND (
                      title % :query
                      OR excerpt % :query
                  )
                  AND GREATEST(
                      COALESCE(similarity(title, :query), 0),
                      COALESCE(similarity(excerpt, :query), 0)
                  ) >= :min_score
                  AND tags && :domains
                ORDER BY retrieval_score DESC, confidence DESC
                LIMIT :limit
            """)
            params = {
                "tenant_id": ctx.tenant_id,
                "site_id": ctx.site_id,
                "query": input.query,
                "min_score": input.min_score,
                "domains": input.domains,
                "limit": input.limit,
            }
        else:
            sql = text("""
                SELECT
                    id,
                    source_type,
                    source_ref,
                    title,
                    excerpt,
                    confidence,
                    verified,
                    tags,
                    GREATEST(
                        COALESCE(similarity(title, :query), 0),
                        COALESCE(similarity(excerpt, :query), 0)
                    ) AS retrieval_score
                FROM evidences
                WHERE tenant_id = :tenant_id
                  AND site_id = :site_id
                  AND deleted_at IS NULL
                  AND (
                      title % :query
                      OR excerpt % :query
                  )
                  AND GREATEST(
                      COALESCE(similarity(title, :query), 0),
                      COALESCE(similarity(excerpt, :query), 0)
                  ) >= :min_score
                ORDER BY retrieval_score DESC, confidence DESC
                LIMIT :limit
            """)
            params = {
                "tenant_id": ctx.tenant_id,
                "site_id": ctx.site_id,
                "query": input.query,
                "min_score": input.min_score,
                "limit": input.limit,
            }

        result = await self.session.execute(sql, params)
        rows = result.fetchall()

        items = []
        scores = []

        for row in rows:
            score = float(row.retrieval_score) if row.retrieval_score else 0.0
            scores.append(score)

            items.append(EvidenceItem(
                id=str(row.id),
                source_type=row.source_type,
                source_ref=row.source_ref,
                title=row.title,
                excerpt=row.excerpt[:300] if row.excerpt and len(row.excerpt) > 300 else row.excerpt,
                confidence=float(row.confidence) if row.confidence else 1.0,
                verified=bool(row.verified),
                tags=list(row.tags) if row.tags else [],
                retrieval_score=score,
            ))

        # 计算分数分布
        score_distribution = None
        if scores:
            score_distribution = {
                "min": min(scores),
                "max": max(scores),
                "avg": sum(scores) / len(scores),
                "count": len(scores),
            }

        log.info(
            "retrieve_evidence_trgm",
            hit_count=len(items),
            score_distribution=score_distribution,
        )

        return RetrieveEvidenceOutput(
            items=items,
            total=len(items),
            query=input.query,
            strategy_used="trgm",
            search_method="trgm",
            score_distribution=score_distribution,
        )

    async def _retrieve_evidence_like(
        self,
        input: RetrieveEvidenceInput,
        ctx: ToolContext,
        log,
    ) -> RetrieveEvidenceOutput:
        """使用传统 LIKE 搜索（回退方案）"""
        from app.database.models import Evidence

        like_pattern = f"%{input.query}%"

        stmt = select(Evidence).where(
            Evidence.tenant_id == ctx.tenant_id,
            Evidence.site_id == ctx.site_id,
            Evidence.deleted_at.is_(None),
            (Evidence.excerpt.ilike(like_pattern) | Evidence.title.ilike(like_pattern)),
        )

        if input.domains:
            stmt = stmt.where(Evidence.tags.overlap(input.domains))

        stmt = stmt.order_by(Evidence.confidence.desc()).limit(input.limit)

        result = await self.session.execute(stmt)
        evidences = result.scalars().all()

        items = [
            EvidenceItem(
                id=str(e.id),
                source_type=e.source_type.value if hasattr(e.source_type, 'value') else str(e.source_type),
                source_ref=e.source_ref,
                title=e.title,
                excerpt=e.excerpt[:300] if e.excerpt and len(e.excerpt) > 300 else e.excerpt,
                confidence=e.confidence,
                verified=e.verified,
                tags=e.tags or [],
                retrieval_score=None,  # LIKE 搜索无分数
            )
            for e in evidences
        ]

        log.info("retrieve_evidence_like", hit_count=len(items))

        return RetrieveEvidenceOutput(
            items=items,
            total=len(items),
            query=input.query,
            strategy_used="like",
            search_method="like",
            score_distribution=None,
        )


    async def _handle_submit_feedback(
        self,
        input: SubmitFeedbackInput,
        ctx: ToolContext,
    ) -> SubmitFeedbackOutput:
        """提交用户反馈"""
        from uuid import uuid4

        feedback = UserFeedback(
            id=str(uuid4()),
            trace_id=input.trace_id or ctx.trace_id,
            conversation_id=input.conversation_id,
            message_id=input.message_id,
            feedback_type=input.feedback_type,
            severity=input.severity,
            content=input.content,
            original_response=input.original_response,
            suggested_fix=input.suggested_fix,
            tags=input.tags,
            tenant_id=ctx.tenant_id,
            site_id=ctx.site_id,
            user_id=ctx.user_id,
            status=FeedbackStatus.PENDING.value,
            metadata={"source": "tool_call", "npc_id": ctx.npc_id},
        )

        self.session.add(feedback)
        await self.session.flush()

        logger.info(
            "feedback_submitted",
            feedback_id=feedback.id,
            trace_id=feedback.trace_id,
            feedback_type=input.feedback_type,
        )

        return SubmitFeedbackOutput(
            feedback_id=feedback.id,
            status=feedback.status,
            created_at=feedback.created_at,
        )

    async def _handle_list_feedback(
        self,
        input: ListFeedbackInput,
        ctx: ToolContext,
    ) -> ListFeedbackOutput:
        """查询反馈列表"""
        from sqlalchemy import func, and_

        conditions = [
            UserFeedback.tenant_id == ctx.tenant_id,
            UserFeedback.site_id == ctx.site_id,
        ]

        if input.status:
            conditions.append(UserFeedback.status == input.status)
        if input.feedback_type:
            conditions.append(UserFeedback.feedback_type == input.feedback_type)
        if input.severity:
            conditions.append(UserFeedback.severity == input.severity)

        # 查询总数
        count_query = select(func.count(UserFeedback.id)).where(and_(*conditions))
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # 查询列表
        query = (
            select(UserFeedback)
            .where(and_(*conditions))
            .order_by(UserFeedback.created_at.desc())
            .limit(input.limit)
        )
        result = await self.session.execute(query)
        feedbacks = result.scalars().all()

        items = [
            FeedbackItem(
                id=str(f.id),
                trace_id=f.trace_id,
                feedback_type=f.feedback_type,
                severity=f.severity,
                content=f.content,
                status=f.status,
                created_at=f.created_at,
            )
            for f in feedbacks
        ]

        return ListFeedbackOutput(items=items, total=total)

    def _build_system_prompt(
        self,
        profile: NPCProfile,
        identity: Dict,
        personality: Dict,
        constraints: Dict,
    ) -> str:
        """构建系统 Prompt"""
        parts = []

        # 身份
        parts.append(f"你是{profile.display_name or profile.name}。")
        if identity.get("era"):
            parts.append(f"你生活在{identity['era']}。")
        if identity.get("role"):
            parts.append(f"你的身份是{identity['role']}。")
        if identity.get("background"):
            parts.append(f"背景：{identity['background']}")

        # 性格
        if personality.get("traits"):
            parts.append(f"你的性格特点：{'、'.join(personality['traits'])}。")
        if personality.get("speaking_style"):
            parts.append(f"说话风格：{personality['speaking_style']}")

        # 知识领域
        if profile.knowledge_domains:
            parts.append(f"你擅长的领域：{'、'.join(profile.knowledge_domains)}。")

        # 约束
        if constraints.get("forbidden_topics"):
            parts.append(f"禁止讨论的话题：{'、'.join(constraints['forbidden_topics'])}。")
        if profile.must_cite_sources:
            parts.append("回答时请引用可靠来源。")
        if profile.max_response_length:
            parts.append(f"回答长度控制在{profile.max_response_length}字以内。")

        return "\n".join(parts)

    # ============================================================
    # 辅助方法
    # ============================================================

    def _hash_payload(self, payload: Dict[str, Any]) -> str:
        """计算 payload hash"""
        payload_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload_str.encode()).hexdigest()[:16]

    async def _record_audit(
        self,
        ctx: ToolContext,
        tool_name: str,
        audit: ToolAudit,
        output: Any,
        error: Optional[str] = None,
    ) -> None:
        """记录审计到 trace_ledger"""
        trace = TraceLedger(
            tenant_id=ctx.tenant_id,
            site_id=ctx.site_id,
            trace_id=ctx.trace_id,
            span_id=ctx.span_id,
            session_id=ctx.session_id,
            user_id=ctx.user_id,
            npc_id=ctx.npc_id,
            request_type="tool_call",
            request_input={"tool_name": tool_name},
            tool_calls=[{
                "name": tool_name,
                "status": audit.status,
                "latency_ms": audit.latency_ms,
                "payload_hash": audit.request_payload_hash,
            }],
            policy_mode=PolicyMode.NORMAL.value,
            latency_ms=audit.latency_ms,
            status=audit.status,
            error=error,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )

        if output:
            trace.response_output = output if isinstance(output, dict) else output.model_dump()

        self.session.add(trace)
        await self.session.flush()
