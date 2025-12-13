"""
Resilient Tool Client

带缓存、超时、重试、降级的 Tool Client

特性：
- Per-tool 超时配置
- 指数退避重试
- Redis 缓存（安全读工具）
- 降级策略
- 审计记录
"""

import asyncio
import time
import uuid
import httpx
import structlog
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Any, Dict, List, Optional, Callable

from app.core.config import settings
from app.cache import get_cache, CacheKeyBuilder, CacheKey
from app.cache.keys import CACHE_TTL
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


class ToolPriority(str, Enum):
    """工具优先级"""

    CRITICAL = "critical"    # 关键工具，失败则整体失败
    IMPORTANT = "important"  # 重要工具，失败则降级
    OPTIONAL = "optional"    # 可选工具，失败则跳过


@dataclass
class ToolConfig:
    """工具配置"""

    timeout_ms: int = 300          # 超时时间（毫秒）
    max_retries: int = 2           # 最大重试次数
    retry_delay_ms: int = 100      # 重试延迟（毫秒）
    priority: ToolPriority = ToolPriority.IMPORTANT
    cacheable: bool = False        # 是否可缓存
    cache_ttl: int = 300           # 缓存 TTL（秒）
    async_fallback: bool = False   # 是否异步降级（不阻塞主流程）


# Per-tool 配置
TOOL_CONFIGS: Dict[str, ToolConfig] = {
    "get_prompt_active": ToolConfig(
        timeout_ms=200,
        max_retries=2,
        priority=ToolPriority.CRITICAL,
        cacheable=True,
        cache_ttl=CACHE_TTL[CacheKey.PROMPT_ACTIVE],
    ),
    "get_npc_profile": ToolConfig(
        timeout_ms=300,
        max_retries=2,
        priority=ToolPriority.CRITICAL,
        cacheable=True,
        cache_ttl=CACHE_TTL[CacheKey.NPC_PROFILE],
    ),
    "get_site_map": ToolConfig(
        timeout_ms=300,
        max_retries=1,
        priority=ToolPriority.OPTIONAL,
        cacheable=True,
        cache_ttl=CACHE_TTL[CacheKey.SITE_MAP],
    ),
    "retrieve_evidence": ToolConfig(
        timeout_ms=800,
        max_retries=1,
        priority=ToolPriority.IMPORTANT,
        cacheable=True,
        cache_ttl=CACHE_TTL[CacheKey.EVIDENCE],
    ),
    "search_content": ToolConfig(
        timeout_ms=500,
        max_retries=1,
        priority=ToolPriority.IMPORTANT,
        cacheable=False,
    ),
    "log_user_event": ToolConfig(
        timeout_ms=150,
        max_retries=0,
        priority=ToolPriority.OPTIONAL,
        async_fallback=True,  # 异步化，不阻塞主流程
    ),
    "create_trace": ToolConfig(
        timeout_ms=300,
        max_retries=1,
        priority=ToolPriority.IMPORTANT,
        async_fallback=True,
    ),
}

DEFAULT_TOOL_CONFIG = ToolConfig(
    timeout_ms=500,
    max_retries=1,
    priority=ToolPriority.IMPORTANT,
)


@dataclass
class ToolCallAudit:
    """工具调用审计"""

    tool_name: str
    status: str  # success / error / timeout / fallback / cache_hit
    latency_ms: int
    retries: int = 0
    cache_hit: bool = False
    error: Optional[str] = None
    error_type: Optional[str] = None


class ResilientToolClient:
    """
    带缓存、超时、重试、降级的 Tool Client

    设计原则：
    1. 关键工具失败 → 整体失败
    2. 重要工具失败 → 降级处理
    3. 可选工具失败 → 跳过
    4. 安全读工具 → 缓存
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        internal_api_key: Optional[str] = None,
    ):
        self.base_url = base_url or settings.TOOLS_BASE_URL
        self.internal_api_key = internal_api_key or settings.INTERNAL_API_KEY

        self._cache = None
        self._key_builder = CacheKeyBuilder()

        # 审计记录
        self.call_audits: List[ToolCallAudit] = []

    async def _get_cache(self):
        """获取缓存实例"""
        if self._cache is None:
            self._cache = await get_cache()
        return self._cache

    def _get_config(self, tool_name: str) -> ToolConfig:
        """获取工具配置"""
        return TOOL_CONFIGS.get(tool_name, DEFAULT_TOOL_CONFIG)

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

    def _build_cache_key(
        self,
        tool_name: str,
        ctx: ToolContext,
        input_data: Dict[str, Any],
    ) -> Optional[str]:
        """构建缓存 Key"""
        if tool_name == "get_npc_profile":
            return self._key_builder.npc_profile(
                ctx.tenant_id, ctx.site_id, input_data.get("npc_id", "")
            )
        elif tool_name == "get_prompt_active":
            return self._key_builder.prompt_active(
                ctx.tenant_id, ctx.site_id, input_data.get("npc_id", "")
            )
        elif tool_name == "get_site_map":
            return self._key_builder.site_map(ctx.tenant_id, ctx.site_id)
        elif tool_name == "retrieve_evidence":
            return self._key_builder.evidence(
                ctx.tenant_id,
                ctx.site_id,
                input_data.get("query", ""),
                input_data.get("domains"),
            )
        return None

    async def call_tool(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        ctx: ToolContext,
    ) -> ToolCallResult:
        """
        调用工具（带缓存、超时、重试）

        流程：
        1. 检查缓存（如果可缓存）
        2. 调用工具（带超时和重试）
        3. 缓存结果（如果成功且可缓存）
        4. 记录审计
        """
        config = self._get_config(tool_name)
        log = logger.bind(trace_id=ctx.trace_id, tool_name=tool_name)

        start_time = time.time()
        retries = 0
        cache_hit = False

        # 1. 检查缓存
        if config.cacheable:
            cache_key = self._build_cache_key(tool_name, ctx, input_data)
            if cache_key:
                cache = await self._get_cache()
                cached = await cache.get(cache_key)
                if cached is not None:
                    latency_ms = int((time.time() - start_time) * 1000)
                    log.info("tool_cache_hit", latency_ms=latency_ms)

                    self._record_audit(
                        tool_name=tool_name,
                        status="cache_hit",
                        latency_ms=latency_ms,
                        cache_hit=True,
                    )

                    return ToolCallResult(
                        success=True,
                        output=cached,
                        audit=ToolAudit(
                            tool_name=tool_name,
                            latency_ms=latency_ms,
                            cache_hit=True,
                        ),
                    )

        # 2. 调用工具（带重试）
        last_error = None
        timeout_seconds = config.timeout_ms / 1000

        for attempt in range(config.max_retries + 1):
            try:
                result = await self._do_call(
                    tool_name, input_data, ctx, timeout_seconds
                )

                latency_ms = int((time.time() - start_time) * 1000)

                if result.success:
                    # 3. 缓存结果
                    if config.cacheable and result.output:
                        cache_key = self._build_cache_key(tool_name, ctx, input_data)
                        if cache_key:
                            cache = await self._get_cache()
                            await cache.set(cache_key, result.output, config.cache_ttl)

                    log.info("tool_call_success", latency_ms=latency_ms, retries=retries)

                    self._record_audit(
                        tool_name=tool_name,
                        status="success",
                        latency_ms=latency_ms,
                        retries=retries,
                    )

                    return result

                # 工具返回失败
                last_error = result.error
                log.warning("tool_call_failed", error=result.error, attempt=attempt + 1)

            except asyncio.TimeoutError:
                retries = attempt
                last_error = f"Timeout after {config.timeout_ms}ms"
                log.warning("tool_call_timeout", attempt=attempt + 1)

            except Exception as e:
                retries = attempt
                last_error = str(e)
                log.warning("tool_call_error", error=str(e), attempt=attempt + 1)

            # 重试延迟（指数退避）
            if attempt < config.max_retries:
                delay = config.retry_delay_ms * (2 ** attempt) / 1000
                await asyncio.sleep(delay)
                retries = attempt + 1

        # 所有重试失败
        latency_ms = int((time.time() - start_time) * 1000)

        self._record_audit(
            tool_name=tool_name,
            status="error",
            latency_ms=latency_ms,
            retries=retries,
            error=last_error,
        )

        return ToolCallResult(
            success=False,
            error=last_error,
            error_type="timeout" if "Timeout" in str(last_error) else "error",
        )

    async def _do_call(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        ctx: ToolContext,
        timeout: float,
    ) -> ToolCallResult:
        """执行单次工具调用"""
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.base_url}/call",
                headers=self._get_headers(ctx),
                json={
                    "tool_name": tool_name,
                    "input": input_data,
                    "context": ctx.model_dump(),
                },
            )
            response.raise_for_status()
            data = response.json()

            return ToolCallResult(
                success=data.get("success", False),
                output=data.get("output"),
                error=data.get("error"),
                error_type=data.get("error_type"),
                audit=ToolAudit(**data["audit"]) if data.get("audit") else None,
            )

    def _record_audit(
        self,
        tool_name: str,
        status: str,
        latency_ms: int,
        retries: int = 0,
        cache_hit: bool = False,
        error: Optional[str] = None,
    ) -> None:
        """记录审计"""
        self.call_audits.append(ToolCallAudit(
            tool_name=tool_name,
            status=status,
            latency_ms=latency_ms,
            retries=retries,
            cache_hit=cache_hit,
            error=error,
        ))

    def get_audits(self) -> List[Dict[str, Any]]:
        """获取审计记录（用于 trace_ledger）"""
        return [
            {
                "name": a.tool_name,
                "status": a.status,
                "latency_ms": a.latency_ms,
                "retries": a.retries,
                "cache_hit": a.cache_hit,
                "error": a.error,
            }
            for a in self.call_audits
        ]

    def clear_audits(self) -> None:
        """清空审计记录"""
        self.call_audits = []

    # ============================================================
    # 便捷方法：封装常用工具调用（带降级）
    # ============================================================

    async def get_npc_profile(
        self,
        npc_id: str,
        ctx: ToolContext,
        version: Optional[int] = None,
    ) -> Optional[NPCProfile]:
        """获取 NPC 人设（带缓存）"""
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
        """获取 NPC 当前激活的 Prompt（带缓存）"""
        result = await self.call_tool(
            "get_prompt_active",
            {"npc_id": npc_id, "prompt_type": prompt_type},
            ctx,
        )
        if result.success and result.output:
            return PromptInfo(**result.output)
        return None

    async def retrieve_evidence(
        self,
        query: str,
        ctx: ToolContext,
        domains: Optional[List[str]] = None,
        limit: int = 5,
    ) -> List[EvidenceItem]:
        """检索证据（带缓存）"""
        input_data = {"query": query, "limit": limit}
        if domains:
            input_data["domains"] = domains

        result = await self.call_tool("retrieve_evidence", input_data, ctx)
        if result.success and result.output:
            items = result.output.get("items", [])
            return [EvidenceItem(**item) for item in items]
        return []

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

    async def log_user_event(
        self,
        event_type: str,
        ctx: ToolContext,
        event_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        记录用户事件（异步化，不阻塞主流程）

        失败时静默处理，不影响主流程
        """
        try:
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
        except Exception as e:
            logger.warning("log_user_event_failed", error=str(e))
            return False

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
    ) -> bool:
        """创建追踪记录"""
        log = logger.bind(trace_id=ctx.trace_id)

        try:
            from datetime import datetime

            async with httpx.AsyncClient(timeout=0.3) as client:
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
                    },
                )
                response.raise_for_status()

                # 更新追踪记录
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
        async with httpx.AsyncClient(timeout=0.5) as client:
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


# 全局实例
_resilient_client: Optional[ResilientToolClient] = None


def get_resilient_tool_client() -> ResilientToolClient:
    """获取 Resilient Tool Client 单例"""
    global _resilient_client
    if _resilient_client is None:
        _resilient_client = ResilientToolClient()
    return _resilient_client
