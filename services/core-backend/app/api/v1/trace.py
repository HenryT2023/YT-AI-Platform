"""
证据链账本 API

提供追踪记录的查询和写入
"""

from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DB, TenantCtx, CurrentUser, TenantSession
from app.database.models import TraceLedger, PolicyMode

router = APIRouter()


class TraceCreate(BaseModel):
    """创建追踪记录请求"""

    trace_id: str = Field(..., description="追踪 ID")
    session_id: Optional[str] = None
    npc_id: Optional[str] = None
    request_type: str = Field(..., description="请求类型：chat/greeting/tool_call")
    request_input: Dict[str, Any] = Field(default_factory=dict)
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    evidence_chain: Dict[str, Any] = Field(default_factory=dict)
    policy_mode: str = Field(..., description="策略模式：strict/normal/relaxed/fallback")
    policy_reason: Optional[str] = None
    started_at: datetime


class TraceUpdate(BaseModel):
    """更新追踪记录请求"""

    response_output: Optional[Dict[str, Any]] = None
    response_tokens: Optional[int] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    latency_ms: Optional[int] = None
    total_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    confidence_score: Optional[float] = None
    guardrail_passed: Optional[bool] = None
    guardrail_reason: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    status: Optional[str] = None
    completed_at: Optional[datetime] = None


class TraceResponse(BaseModel):
    """追踪记录响应"""

    id: str
    trace_id: str
    tenant_id: str
    site_id: str
    session_id: Optional[str]
    npc_id: Optional[str]
    request_type: str
    policy_mode: str
    policy_reason: Optional[str]
    evidence_ids: List[str]
    latency_ms: Optional[int]
    total_tokens: Optional[int]
    confidence_score: Optional[float]
    guardrail_passed: Optional[bool]
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class TraceDetailResponse(TraceResponse):
    """追踪记录详情响应"""

    request_input: Dict[str, Any]
    tool_calls: List[Dict[str, Any]]
    evidence_chain: Dict[str, Any]
    response_output: Optional[Dict[str, Any]]
    model_provider: Optional[str]
    model_name: Optional[str]
    error: Optional[str]
    error_code: Optional[str]


@router.get("", response_model=List[TraceResponse])
async def list_traces(
    ts: TenantSession,
    session_id: Optional[str] = Query(None),
    npc_id: Optional[str] = Query(None),
    policy_mode: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> List[TraceLedger]:
    """获取追踪记录列表"""
    stmt = select(TraceLedger)

    if session_id:
        stmt = stmt.where(TraceLedger.session_id == session_id)
    if npc_id:
        stmt = stmt.where(TraceLedger.npc_id == npc_id)
    if policy_mode:
        stmt = stmt.where(TraceLedger.policy_mode == policy_mode)
    if status:
        stmt = stmt.where(TraceLedger.status == status)

    stmt = stmt.order_by(TraceLedger.created_at.desc())
    stmt = stmt.offset(skip).limit(limit)

    result = await ts.execute(stmt)
    return list(result.scalars().all())


@router.get("/{trace_id}", response_model=TraceDetailResponse)
async def get_trace(
    trace_id: str,
    ts: TenantSession,
) -> TraceLedger:
    """获取追踪记录详情"""
    stmt = select(TraceLedger).where(TraceLedger.trace_id == trace_id)
    result = await ts.execute(stmt)
    trace = result.scalar_one_or_none()

    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trace not found",
        )
    return trace


@router.post("", response_model=TraceResponse, status_code=status.HTTP_201_CREATED)
async def create_trace(
    data: TraceCreate,
    ts: TenantSession,
    tenant_ctx: TenantCtx,
) -> TraceLedger:
    """创建追踪记录"""
    trace = TraceLedger(
        trace_id=data.trace_id,
        tenant_id=tenant_ctx.tenant_id,
        site_id=tenant_ctx.site_id,
        session_id=data.session_id,
        npc_id=data.npc_id,
        request_type=data.request_type,
        request_input=data.request_input,
        tool_calls=data.tool_calls,
        evidence_ids=data.evidence_ids,
        evidence_chain=data.evidence_chain,
        policy_mode=data.policy_mode,
        policy_reason=data.policy_reason,
        started_at=data.started_at,
    )
    ts.add(trace)
    await ts.flush()
    await ts.refresh(trace)
    return trace


@router.patch("/{trace_id}", response_model=TraceResponse)
async def update_trace(
    trace_id: str,
    data: TraceUpdate,
    ts: TenantSession,
) -> TraceLedger:
    """更新追踪记录"""
    stmt = select(TraceLedger).where(TraceLedger.trace_id == trace_id)
    result = await ts.execute(stmt)
    trace = result.scalar_one_or_none()

    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trace not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(trace, field, value)

    await ts.flush()
    await ts.refresh(trace)
    return trace


@router.get("/stats/summary")
async def get_trace_stats(
    ts: TenantSession,
    days: int = Query(7, ge=1, le=90),
) -> Dict[str, Any]:
    """获取追踪统计摘要"""
    from sqlalchemy import func
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(days=days)

    # 总数统计
    total_stmt = select(func.count(TraceLedger.id)).where(
        TraceLedger.created_at >= cutoff
    )
    total_result = await ts.execute(total_stmt)
    total_count = total_result.scalar()

    # 按策略模式统计
    policy_stmt = select(
        TraceLedger.policy_mode,
        func.count(TraceLedger.id),
    ).where(
        TraceLedger.created_at >= cutoff
    ).group_by(TraceLedger.policy_mode)
    policy_result = await ts.execute(policy_stmt)
    policy_stats = {row[0]: row[1] for row in policy_result.all()}

    # 按状态统计
    status_stmt = select(
        TraceLedger.status,
        func.count(TraceLedger.id),
    ).where(
        TraceLedger.created_at >= cutoff
    ).group_by(TraceLedger.status)
    status_result = await ts.execute(status_stmt)
    status_stats = {row[0]: row[1] for row in status_result.all()}

    # 平均延迟
    latency_stmt = select(func.avg(TraceLedger.latency_ms)).where(
        TraceLedger.created_at >= cutoff,
        TraceLedger.latency_ms.isnot(None),
    )
    latency_result = await ts.execute(latency_stmt)
    avg_latency = latency_result.scalar()

    return {
        "period_days": days,
        "total_traces": total_count,
        "by_policy_mode": policy_stats,
        "by_status": status_stats,
        "avg_latency_ms": round(avg_latency, 2) if avg_latency else None,
    }
