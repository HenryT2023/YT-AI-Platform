"""
MCP 工具 API

提供 MCP 工具注册、查询、执行接口
供 ai-orchestrator 调用
"""

from typing import Annotated, Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import ReqCtx, get_db
from app.core.permissions import Permission, check_permission
from app.domain.tool_call_log import ToolCallLog
from app.services.mcp_registry import get_mcp_registry, MCPToolDefinition
from app.services.tool_executor import ToolExecutor, ToolExecutionError

router = APIRouter()


class ToolExecuteRequest(BaseModel):
    """工具执行请求"""

    tool_name: str = Field(..., description="工具名称")
    params: Dict[str, Any] = Field(default_factory=dict, description="工具参数")
    session_id: Optional[str] = Field(None, description="会话 ID")


class ToolExecuteResponse(BaseModel):
    """工具执行响应"""

    success: bool
    tool_name: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    trace_id: str
    span_id: Optional[str] = None
    duration_ms: Optional[int] = None


class ToolDefinitionResponse(BaseModel):
    """工具定义响应"""

    name: str
    description: str
    version: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    category: str
    tags: List[str]
    requires_evidence: bool
    ai_callable: bool


class ToolCallLogResponse(BaseModel):
    """工具调用日志响应"""

    id: UUID
    trace_id: str
    tool_name: str
    status: str
    input_params: Dict[str, Any]
    output_result: Optional[Dict[str, Any]]
    error_message: Optional[str]
    duration_ms: Optional[int]
    created_at: Any

    model_config = {"from_attributes": True}


def verify_internal_api_key(
    x_internal_api_key: Annotated[Optional[str], Header(alias="X-Internal-API-Key")] = None,
) -> None:
    """验证内部 API Key（用于服务间通信）"""
    if x_internal_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API key",
        )


@router.get("/definitions", response_model=List[ToolDefinitionResponse])
async def list_tool_definitions(
    category: Optional[str] = Query(None, description="工具类别"),
    ai_callable_only: bool = Query(False, description="仅返回 AI 可调用的工具"),
) -> List[Dict[str, Any]]:
    """
    获取所有可用的 MCP 工具定义

    此接口供 ai-orchestrator 获取工具列表
    """
    registry = get_mcp_registry()
    tools = registry.list_tools(category=category, ai_callable_only=ai_callable_only)
    return [tool.to_dict() for tool in tools]


@router.get("/definitions/{tool_name}", response_model=ToolDefinitionResponse)
async def get_tool_definition(tool_name: str) -> Dict[str, Any]:
    """获取单个工具定义"""
    registry = get_mcp_registry()
    tool = registry.get(tool_name)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{tool_name}' not found",
        )
    return tool.to_dict()


@router.get("/openai-format")
async def get_tools_openai_format() -> List[Dict[str, Any]]:
    """
    获取 OpenAI function calling 格式的工具列表

    供 ai-orchestrator 直接传给 LLM
    """
    registry = get_mcp_registry()
    return registry.to_openai_tools()


@router.post("/execute", response_model=ToolExecuteResponse)
async def execute_tool(
    request: ToolExecuteRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: ReqCtx,
) -> ToolExecuteResponse:
    """
    执行 MCP 工具

    此接口供 ai-orchestrator 调用，执行具体的业务工具
    所有调用都会记录审计日志
    """
    check_permission(ctx.user, Permission.TOOL_EXECUTE)

    executor = ToolExecutor(db=db, ctx=ctx)

    try:
        result = await executor.execute(
            tool_name=request.tool_name,
            params=request.params,
            caller_service="ai-orchestrator",
            session_id=request.session_id,
        )

        return ToolExecuteResponse(
            success=True,
            tool_name=request.tool_name,
            result=result.get("result"),
            trace_id=result.get("trace_id", ctx.trace_id),
            span_id=result.get("span_id"),
            duration_ms=result.get("duration_ms"),
        )

    except ToolExecutionError as e:
        return ToolExecuteResponse(
            success=False,
            tool_name=request.tool_name,
            error=e.message,
            error_code=e.error_code,
            trace_id=ctx.trace_id,
        )


@router.post("/execute/internal", response_model=ToolExecuteResponse)
async def execute_tool_internal(
    request: ToolExecuteRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: ReqCtx,
    _: Annotated[None, Depends(verify_internal_api_key)],
) -> ToolExecuteResponse:
    """
    内部服务调用工具执行

    使用 X-Internal-API-Key 认证，用于服务间通信
    """
    executor = ToolExecutor(db=db, ctx=ctx)

    try:
        result = await executor.execute(
            tool_name=request.tool_name,
            params=request.params,
            caller_service="internal",
            session_id=request.session_id,
        )

        return ToolExecuteResponse(
            success=True,
            tool_name=request.tool_name,
            result=result.get("result"),
            trace_id=result.get("trace_id", ctx.trace_id),
            span_id=result.get("span_id"),
            duration_ms=result.get("duration_ms"),
        )

    except ToolExecutionError as e:
        return ToolExecuteResponse(
            success=False,
            tool_name=request.tool_name,
            error=e.message,
            error_code=e.error_code,
            trace_id=ctx.trace_id,
        )


@router.get("/logs", response_model=List[ToolCallLogResponse])
async def list_tool_call_logs(
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: ReqCtx,
    tool_name: Optional[str] = Query(None),
    trace_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> List[ToolCallLog]:
    """获取工具调用日志（用于审计）"""
    check_permission(ctx.user, Permission.AUDIT_READ)

    query = select(ToolCallLog).where(
        ToolCallLog.tenant_id == ctx.tenant_id,
        ToolCallLog.site_id == ctx.site_id,
    )

    if tool_name:
        query = query.where(ToolCallLog.tool_name == tool_name)

    if trace_id:
        query = query.where(ToolCallLog.trace_id == trace_id)

    if status:
        query = query.where(ToolCallLog.status == status)

    query = query.order_by(ToolCallLog.created_at.desc())
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/logs/{log_id}", response_model=ToolCallLogResponse)
async def get_tool_call_log(
    log_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: ReqCtx,
) -> ToolCallLog:
    """获取单条工具调用日志"""
    check_permission(ctx.user, Permission.AUDIT_READ)

    result = await db.execute(
        select(ToolCallLog).where(
            ToolCallLog.id == log_id,
            ToolCallLog.tenant_id == ctx.tenant_id,
        )
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool call log not found",
        )
    return log
