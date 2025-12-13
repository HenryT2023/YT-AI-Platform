"""
增强 Trace 回放 API

提供 tool_calls + llm_audit + prompt_version + citations 的统一视图
"""

import structlog
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.tools import get_tool_client, ToolContext

router = APIRouter()
logger = structlog.get_logger(__name__)


class LLMAuditView(BaseModel):
    """LLM 审计视图"""

    provider: Optional[str] = None
    model: Optional[str] = None
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: int = 0
    fallback: bool = False
    error: Optional[str] = None


class ToolCallView(BaseModel):
    """工具调用视图"""

    name: str
    status: str
    latency_ms: Optional[int] = None
    cache_hit: Optional[bool] = None
    retry_count: Optional[int] = None
    error: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class CitationView(BaseModel):
    """引用视图"""

    evidence_id: str
    title: Optional[str] = None
    source_ref: Optional[str] = None
    excerpt: Optional[str] = None
    confidence: float = 1.0


class PromptView(BaseModel):
    """Prompt 视图"""

    version: Optional[int] = None
    source: Optional[str] = None
    npc_id: Optional[str] = None
    persona_version: Optional[int] = None


class SessionView(BaseModel):
    """会话视图"""

    session_id: Optional[str] = None
    message_count: int = 0
    recent_messages: List[Dict[str, Any]] = Field(default_factory=list)


class TraceUnifiedView(BaseModel):
    """Trace 统一视图"""

    trace_id: str
    tenant_id: str
    site_id: str
    request_type: str
    status: str
    created_at: Optional[str] = None

    # 请求信息
    query: Optional[str] = None
    npc_id: Optional[str] = None
    user_id: Optional[str] = None

    # 响应信息
    policy_mode: Optional[str] = None
    answer_text: Optional[str] = None
    latency_ms: Optional[int] = None

    # 详细视图
    prompt: PromptView = Field(default_factory=PromptView)
    tool_calls: List[ToolCallView] = Field(default_factory=list)
    llm_audit: LLMAuditView = Field(default_factory=LLMAuditView)
    citations: List[CitationView] = Field(default_factory=list)
    session: Optional[SessionView] = None

    # 错误信息
    error: Optional[str] = None


@router.get("/traces/{trace_id}/unified", response_model=TraceUnifiedView)
async def get_trace_unified_view(
    trace_id: str,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_site_id: str = Header(..., alias="X-Site-ID"),
    include_session: bool = Query(default=False, description="是否包含会话信息"),
):
    """
    获取 Trace 统一视图

    整合返回：
    - 基本信息（trace_id, status, latency）
    - Prompt 信息（version, source）
    - 工具调用列表（name, status, cache_hit, retry_count）
    - LLM 审计（provider, model, tokens, latency）
    - 引用列表（evidence_id, title, confidence）
    - 会话信息（可选）
    """
    log = logger.bind(trace_id=trace_id)
    log.info("get_trace_unified_view", include_session=include_session)

    ctx = ToolContext(
        tenant_id=x_tenant_id,
        site_id=x_site_id,
        trace_id=trace_id,
    )

    tool_client = get_tool_client()
    trace = await tool_client.get_trace(trace_id, ctx)

    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace not found: {trace_id}",
        )

    # 解析 request_input
    request_input = trace.get("request_input", {})
    response_output = trace.get("response_output", {})

    # 构建 Prompt 视图
    prompt_view = PromptView(
        version=request_input.get("prompt_version"),
        source=request_input.get("prompt_source"),
        npc_id=request_input.get("npc_id"),
        persona_version=request_input.get("persona_version"),
    )

    # 构建工具调用视图
    tool_calls_raw = trace.get("tool_calls", [])
    tool_calls = []
    llm_audit = LLMAuditView()

    for tc in tool_calls_raw:
        name = tc.get("name", "unknown")

        # 提取 LLM 审计信息
        if name == "llm_generate":
            llm_audit = LLMAuditView(
                provider=tc.get("provider"),
                model=tc.get("model"),
                tokens_input=tc.get("tokens_input", 0),
                tokens_output=tc.get("tokens_output", 0),
                latency_ms=tc.get("latency_ms", 0),
                fallback=tc.get("status") == "fallback",
                error=tc.get("error"),
            )
        else:
            tool_calls.append(ToolCallView(
                name=name,
                status=tc.get("status", "unknown"),
                latency_ms=tc.get("latency_ms"),
                cache_hit=tc.get("cache_hit"),
                retry_count=tc.get("retry_count"),
                error=tc.get("error"),
                details={
                    k: v for k, v in tc.items()
                    if k not in ["name", "status", "latency_ms", "cache_hit", "retry_count", "error"]
                },
            ))

    # 构建引用视图
    evidence_ids = trace.get("evidence_ids", [])
    citations = [
        CitationView(evidence_id=eid)
        for eid in evidence_ids
    ]

    # 构建会话视图（可选）
    session_view = None
    if include_session:
        session_id = trace.get("session_id") or request_input.get("session_id")
        if session_id:
            try:
                from app.memory import get_session_memory
                memory = await get_session_memory()
                summary = await memory.get_session_summary(
                    tenant_id=x_tenant_id,
                    site_id=x_site_id,
                    session_id=session_id,
                    max_messages=5,
                )
                session_view = SessionView(
                    session_id=session_id,
                    message_count=summary.get("message_count", 0),
                    recent_messages=summary.get("recent_messages", []),
                )
            except Exception as e:
                log.warning("get_session_failed", error=str(e))

    return TraceUnifiedView(
        trace_id=trace_id,
        tenant_id=x_tenant_id,
        site_id=x_site_id,
        request_type=trace.get("request_type", "unknown"),
        status=trace.get("status", "unknown"),
        created_at=trace.get("created_at"),
        query=request_input.get("query"),
        npc_id=request_input.get("npc_id"),
        user_id=trace.get("user_id"),
        policy_mode=trace.get("policy_mode"),
        answer_text=response_output.get("answer_text"),
        latency_ms=trace.get("latency_ms"),
        prompt=prompt_view,
        tool_calls=tool_calls,
        llm_audit=llm_audit,
        citations=citations,
        session=session_view,
        error=trace.get("error"),
    )


@router.get("/traces/recent")
async def list_recent_traces(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_site_id: str = Header(..., alias="X-Site-ID"),
    limit: int = Query(default=20, ge=1, le=100),
    npc_id: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
):
    """
    列出最近的 Trace

    用于调试和监控
    """
    log = logger.bind(tenant_id=x_tenant_id, site_id=x_site_id)
    log.info("list_recent_traces", limit=limit, npc_id=npc_id)

    # TODO: 实现从 core-backend 获取 trace 列表
    # 目前返回占位数据
    return {
        "traces": [],
        "total": 0,
        "limit": limit,
        "message": "Trace listing not yet implemented in core-backend",
    }
