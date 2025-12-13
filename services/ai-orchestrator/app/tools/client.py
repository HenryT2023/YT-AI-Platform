"""
Tool Client

与 core-backend Tool Server 通信的客户端
"""

import uuid
import httpx
import structlog
from functools import lru_cache
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.tools.schemas import (
    ToolContext,
    ToolCallResult,
    ToolMetadata,
    ToolAudit,
    NPCProfile,
    ContentItem,
    EvidenceItem,
    PromptInfo,
)

logger = structlog.get_logger(__name__)


class ToolClient:
    """Tool Server 客户端"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        internal_api_key: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.base_url = base_url or settings.TOOLS_BASE_URL
        self.internal_api_key = internal_api_key or settings.INTERNAL_API_KEY
        self.timeout = timeout or settings.TOOLS_TIMEOUT_SECONDS

    def _get_headers(self, ctx: ToolContext) -> Dict[str, str]:
        """构建请求头"""
        headers = {
            "Content-Type": "application/json",
            "X-Tenant-ID": ctx.tenant_id,
            "X-Site-ID": ctx.site_id,
            "X-Trace-ID": ctx.trace_id,
            "X-Internal-API-Key": self.internal_api_key,
        }
        if ctx.span_id:
            headers["X-Span-ID"] = ctx.span_id
        if ctx.user_id:
            headers["X-User-ID"] = ctx.user_id
        if ctx.session_id:
            headers["X-Session-ID"] = ctx.session_id
        if ctx.npc_id:
            headers["X-NPC-ID"] = ctx.npc_id
        return headers

    async def list_tools(
        self,
        ctx: ToolContext,
        category: Optional[str] = None,
        ai_callable_only: bool = True,
    ) -> List[ToolMetadata]:
        """获取可用工具列表"""
        log = logger.bind(trace_id=ctx.trace_id)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/list",
                    headers=self._get_headers(ctx),
                    json={
                        "category": category,
                        "ai_callable_only": ai_callable_only,
                    },
                )
                response.raise_for_status()
                data = response.json()

                tools = [ToolMetadata(**t) for t in data.get("tools", [])]
                log.info("tools_list_success", count=len(tools))
                return tools

            except Exception as e:
                log.error("tools_list_error", error=str(e))
                raise

    async def call_tool(
        self,
        tool_name: str,
        input: Dict[str, Any],
        ctx: ToolContext,
    ) -> ToolCallResult:
        """调用工具"""
        log = logger.bind(trace_id=ctx.trace_id, tool_name=tool_name)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/call",
                    headers=self._get_headers(ctx),
                    json={
                        "tool_name": tool_name,
                        "input": input,
                        "context": ctx.model_dump(),
                    },
                )
                response.raise_for_status()
                data = response.json()

                result = ToolCallResult(
                    success=data.get("success", False),
                    output=data.get("output"),
                    error=data.get("error"),
                    error_type=data.get("error_type"),
                    audit=ToolAudit(**data["audit"]) if data.get("audit") else None,
                )

                if result.success:
                    log.info("tool_call_success", latency_ms=result.audit.latency_ms if result.audit else None)
                else:
                    log.warning("tool_call_failed", error=result.error)

                return result

            except Exception as e:
                log.error("tool_call_error", error=str(e))
                return ToolCallResult(
                    success=False,
                    error=str(e),
                    error_type=type(e).__name__,
                )

    # ============================================================
    # 便捷方法：封装常用工具调用
    # ============================================================

    async def get_npc_profile(
        self,
        npc_id: str,
        ctx: ToolContext,
        version: Optional[int] = None,
    ) -> Optional[NPCProfile]:
        """获取 NPC 人设"""
        input_data = {"npc_id": npc_id}
        if version is not None:
            input_data["version"] = version

        result = await self.call_tool("get_npc_profile", input_data, ctx)
        if result.success and result.output:
            return NPCProfile(**result.output)
        return None

    async def get_prompt_active(
        self,
        npc_id: str,
        ctx: ToolContext,
        prompt_type: str = "system",
    ) -> Optional[PromptInfo]:
        """获取 NPC 当前激活的 Prompt"""
        result = await self.call_tool(
            "get_prompt_active",
            {"npc_id": npc_id, "prompt_type": prompt_type},
            ctx,
        )
        if result.success and result.output:
            return PromptInfo(**result.output)
        return None

    async def search_content(
        self,
        query: str,
        ctx: ToolContext,
        content_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[ContentItem]:
        """搜索内容"""
        input_data = {"query": query, "limit": limit}
        if content_type:
            input_data["content_type"] = content_type
        if tags:
            input_data["tags"] = tags

        result = await self.call_tool("search_content", input_data, ctx)
        if result.success and result.output:
            items = result.output.get("items", [])
            return [ContentItem(**item) for item in items]
        return []

    async def retrieve_evidence(
        self,
        query: str,
        ctx: ToolContext,
        domains: Optional[List[str]] = None,
        limit: int = 5,
    ) -> List[EvidenceItem]:
        """检索证据"""
        input_data = {"query": query, "limit": limit}
        if domains:
            input_data["domains"] = domains

        result = await self.call_tool("retrieve_evidence", input_data, ctx)
        if result.success and result.output:
            items = result.output.get("items", [])
            return [EvidenceItem(**item) for item in items]
        return []

    async def log_user_event(
        self,
        event_type: str,
        ctx: ToolContext,
        event_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """记录用户事件"""
        result = await self.call_tool(
            "log_user_event",
            {
                "event_type": event_type,
                "event_data": event_data or {},
                "user_id": ctx.user_id,
                "session_id": ctx.session_id,
            },
            ctx,
        )
        return result.success

    async def create_trace(
        self,
        ctx: ToolContext,
        request_type: str,
        request_input: Dict[str, Any],
        tool_calls: List[Dict[str, Any]],
        evidence_ids: List[str],
        policy_mode: str,
        response_output: Optional[Dict[str, Any]] = None,
        latency_ms: Optional[int] = None,
        status: str = "success",
        error: Optional[str] = None,
        experiment_id: Optional[str] = None,
        experiment_variant: Optional[str] = None,
        strategy_snapshot: Optional[Dict[str, Any]] = None,
        release_id: Optional[str] = None,
    ) -> bool:
        """创建追踪记录（通过 core-backend API）"""
        log = logger.bind(trace_id=ctx.trace_id)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                from datetime import datetime

                response = await client.post(
                    f"{settings.CORE_BACKEND_URL}/api/v1/trace",
                    headers=self._get_headers(ctx),
                    json={
                        "trace_id": ctx.trace_id,
                        "session_id": ctx.session_id,
                        "npc_id": ctx.npc_id,
                        "request_type": request_type,
                        "request_input": request_input,
                        "tool_calls": tool_calls,
                        "evidence_ids": evidence_ids,
                        "policy_mode": policy_mode,
                        "started_at": datetime.utcnow().isoformat(),
                        "experiment_id": experiment_id,
                        "experiment_variant": experiment_variant,
                        "strategy_snapshot": strategy_snapshot or {},
                        "release_id": release_id,
                    },
                )
                response.raise_for_status()

                # 更新追踪记录
                trace_data = response.json()
                if response_output or latency_ms or error:
                    await client.patch(
                        f"{settings.CORE_BACKEND_URL}/api/v1/trace/{ctx.trace_id}",
                        headers=self._get_headers(ctx),
                        json={
                            "response_output": response_output,
                            "latency_ms": latency_ms,
                            "status": status,
                            "error": error,
                            "completed_at": datetime.utcnow().isoformat(),
                        },
                    )

                log.info("trace_created", trace_id=ctx.trace_id)
                return True

            except Exception as e:
                log.error("trace_create_error", error=str(e))
                return False

    async def get_trace(self, trace_id: str, ctx: ToolContext) -> Optional[Dict[str, Any]]:
        """获取追踪记录"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{settings.CORE_BACKEND_URL}/api/v1/trace/{trace_id}",
                    headers=self._get_headers(ctx),
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error("trace_get_error", trace_id=trace_id, error=str(e))
                return None


def generate_trace_id() -> str:
    """生成 trace_id"""
    return f"trace-{uuid.uuid4().hex[:16]}"


@lru_cache
def get_tool_client() -> ToolClient:
    """获取 Tool Client 单例"""
    return ToolClient()
