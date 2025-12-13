"""
工具服务 API

提供类 MCP 的 HTTP Tool Server 接口：
- POST /tools/list: 返回工具元数据
- POST /tools/call: 执行工具调用
"""

import structlog
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB
from app.core.config import settings
from app.tools import (
    ToolRegistry,
    get_tool_registry,
    ToolExecutor,
    ToolCallRequest,
    ToolCallResponse,
    ToolListResponse,
    ToolContext,
)

router = APIRouter()
logger = structlog.get_logger(__name__)


class ToolListRequest(BaseModel):
    """工具列表请求"""

    category: Optional[str] = Field(None, description="按分类过滤")
    ai_callable_only: bool = Field(True, description="仅返回可被 AI 调用的工具")


@router.post("/list", response_model=ToolListResponse)
async def list_tools(
    request: ToolListRequest,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_site_id: str = Header(..., alias="X-Site-ID"),
    x_trace_id: str = Header(..., alias="X-Trace-ID"),
    x_internal_api_key: Optional[str] = Header(None, alias="X-Internal-API-Key"),
) -> ToolListResponse:
    """
    获取可用工具列表

    返回所有注册工具的元数据，包括名称、版本、输入输出 schema
    """
    # 验证内部 API Key（可选，用于服务间调用）
    if x_internal_api_key and x_internal_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API key",
        )

    log = logger.bind(
        trace_id=x_trace_id,
        tenant_id=x_tenant_id,
        site_id=x_site_id,
    )
    log.info("tools_list_request", category=request.category)

    registry = get_tool_registry()
    tools = registry.list_metadata()

    # 按分类过滤
    if request.category:
        tools = [t for t in tools if t.category == request.category]

    # 仅返回可被 AI 调用的工具
    if request.ai_callable_only:
        tools = [t for t in tools if t.ai_callable]

    return ToolListResponse(tools=tools, total=len(tools))


@router.post("/call", response_model=ToolCallResponse)
async def call_tool(
    request: ToolCallRequest,
    db: DB,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_site_id: str = Header(..., alias="X-Site-ID"),
    x_trace_id: str = Header(..., alias="X-Trace-ID"),
    x_span_id: Optional[str] = Header(None, alias="X-Span-ID"),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    x_npc_id: Optional[str] = Header(None, alias="X-NPC-ID"),
    x_internal_api_key: Optional[str] = Header(None, alias="X-Internal-API-Key"),
) -> ToolCallResponse:
    """
    执行工具调用

    输入：
    - tool_name: 工具名称
    - input: 工具输入参数（JSON）
    - context: 调用上下文（tenant_id, site_id, trace_id 等）

    输出：
    - success: 是否成功
    - output: 工具输出（成功时）
    - error: 错误信息（失败时）
    - audit: 审计信息
    """
    # 验证内部 API Key（可选）
    if x_internal_api_key and x_internal_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API key",
        )

    # 从请求头补充 context
    if not request.context:
        request.context = ToolContext(
            tenant_id=x_tenant_id,
            site_id=x_site_id,
            trace_id=x_trace_id,
            span_id=x_span_id,
            user_id=x_user_id,
            session_id=x_session_id,
            npc_id=x_npc_id,
        )
    else:
        # 确保 context 中的值与 header 一致
        request.context.tenant_id = x_tenant_id
        request.context.site_id = x_site_id
        request.context.trace_id = x_trace_id
        if x_span_id:
            request.context.span_id = x_span_id
        if x_user_id:
            request.context.user_id = x_user_id
        if x_session_id:
            request.context.session_id = x_session_id
        if x_npc_id:
            request.context.npc_id = x_npc_id

    log = logger.bind(
        trace_id=x_trace_id,
        tool_name=request.tool_name,
        tenant_id=x_tenant_id,
        site_id=x_site_id,
    )
    log.info("tool_call_request")

    # 执行工具
    executor = ToolExecutor(session=db)
    response = await executor.execute(request)

    return response
