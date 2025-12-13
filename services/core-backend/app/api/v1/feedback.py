"""
用户反馈 API

提供纠错闭环工作流：
- POST /v1/feedback - 提交反馈
- GET /v1/feedback - 查询反馈列表
- GET /v1/feedback/{id} - 获取反馈详情
- POST /v1/feedback/{id}/resolve - 解决反馈（绑定修订版本）
- POST /v1/feedback/{id}/reject - 拒绝反馈
- GET /v1/feedback/stats - 反馈统计
"""

import structlog
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.database.models.user_feedback import (
    UserFeedback,
    FeedbackType,
    FeedbackSeverity,
    FeedbackStatus,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/feedback", tags=["feedback"])


# ============================================================
# Schemas
# ============================================================

class FeedbackCreate(BaseModel):
    """创建反馈请求"""
    trace_id: Optional[str] = Field(None, description="关联的 trace ID")
    conversation_id: Optional[str] = Field(None, description="关联的会话 ID")
    message_id: Optional[str] = Field(None, description="关联的消息 ID")
    feedback_type: str = Field(..., description="反馈类型: correction/fact_error/missing_info/rating/suggestion/complaint/praise")
    severity: str = Field("medium", description="严重程度: low/medium/high/critical")
    content: Optional[str] = Field(None, description="反馈内容")
    original_response: Optional[str] = Field(None, description="原始回答")
    suggested_fix: Optional[str] = Field(None, description="建议的修正")
    tags: List[str] = Field(default_factory=list, description="标签")
    metadata: dict = Field(default_factory=dict, description="元数据")

    # 多租户
    tenant_id: str = Field("yantian", description="租户 ID")
    site_id: str = Field("yantian-main", description="站点 ID")


class FeedbackResponse(BaseModel):
    """反馈响应"""
    id: str
    trace_id: Optional[str]
    conversation_id: Optional[str]
    message_id: Optional[str]
    feedback_type: str
    severity: str
    content: Optional[str]
    original_response: Optional[str]
    suggested_fix: Optional[str]
    tags: List[str]
    status: str
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    resolved_by: Optional[str]
    resolved_at: Optional[datetime]
    resolved_by_content_id: Optional[str]
    resolved_by_evidence_id: Optional[str]
    resolution_notes: Optional[str]
    tenant_id: str
    site_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FeedbackResolve(BaseModel):
    """解决反馈请求"""
    resolver: str = Field(..., description="解决者")
    notes: Optional[str] = Field(None, description="解决备注")
    content_id: Optional[str] = Field(None, description="关联的内容修订 ID")
    evidence_id: Optional[str] = Field(None, description="关联的证据修订 ID")


class FeedbackReject(BaseModel):
    """拒绝反馈请求"""
    reviewer: str = Field(..., description="审核者")
    notes: Optional[str] = Field(None, description="拒绝原因")


class FeedbackStats(BaseModel):
    """反馈统计"""
    total: int
    by_status: dict
    by_type: dict
    by_severity: dict
    correction_rate: float  # 纠错率
    resolution_rate: float  # 解决率
    avg_resolution_time_hours: Optional[float]
    top_issues: List[dict]  # 高频问题


class FeedbackListResponse(BaseModel):
    """反馈列表响应"""
    items: List[FeedbackResponse]
    total: int
    page: int
    page_size: int


# ============================================================
# Endpoints
# ============================================================

@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def create_feedback(
    request: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    提交用户反馈

    用于收集用户对 AI 回答的纠错、评价等反馈
    """
    log = logger.bind(
        trace_id=request.trace_id,
        feedback_type=request.feedback_type,
        severity=request.severity,
    )

    # 验证枚举值
    try:
        FeedbackType(request.feedback_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid feedback_type: {request.feedback_type}",
        )

    try:
        FeedbackSeverity(request.severity)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid severity: {request.severity}",
        )

    feedback = UserFeedback(
        id=str(uuid4()),
        trace_id=request.trace_id,
        conversation_id=request.conversation_id,
        message_id=request.message_id,
        feedback_type=request.feedback_type,
        severity=request.severity,
        content=request.content,
        original_response=request.original_response,
        suggested_fix=request.suggested_fix,
        tags=request.tags,
        metadata=request.metadata,
        tenant_id=request.tenant_id,
        site_id=request.site_id,
        status=FeedbackStatus.PENDING.value,
    )

    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    log.info("feedback_created", feedback_id=feedback.id)

    return FeedbackResponse.model_validate(feedback)


@router.get("", response_model=FeedbackListResponse)
async def list_feedback(
    status: Optional[str] = Query(None, description="状态过滤"),
    feedback_type: Optional[str] = Query(None, description="类型过滤"),
    severity: Optional[str] = Query(None, description="严重程度过滤"),
    trace_id: Optional[str] = Query(None, description="trace_id 过滤"),
    tenant_id: str = Query("yantian", description="租户 ID"),
    site_id: Optional[str] = Query(None, description="站点 ID"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db),
):
    """
    查询反馈列表

    支持按状态、类型、严重程度等过滤
    """
    conditions = [UserFeedback.tenant_id == tenant_id]

    if status:
        conditions.append(UserFeedback.status == status)
    if feedback_type:
        conditions.append(UserFeedback.feedback_type == feedback_type)
    if severity:
        conditions.append(UserFeedback.severity == severity)
    if trace_id:
        conditions.append(UserFeedback.trace_id == trace_id)
    if site_id:
        conditions.append(UserFeedback.site_id == site_id)

    # 查询总数
    count_query = select(func.count(UserFeedback.id)).where(and_(*conditions))
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 查询列表
    query = (
        select(UserFeedback)
        .where(and_(*conditions))
        .order_by(UserFeedback.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    items = result.scalars().all()

    return FeedbackListResponse(
        items=[FeedbackResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=FeedbackStats)
async def get_feedback_stats(
    tenant_id: str = Query("yantian", description="租户 ID"),
    site_id: Optional[str] = Query(None, description="站点 ID"),
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    db: AsyncSession = Depends(get_db),
):
    """
    获取反馈统计

    包括纠错率、解决率、高频问题等
    """
    since = datetime.utcnow() - timedelta(days=days)
    conditions = [
        UserFeedback.tenant_id == tenant_id,
        UserFeedback.created_at >= since,
    ]
    if site_id:
        conditions.append(UserFeedback.site_id == site_id)

    # 总数
    total_query = select(func.count(UserFeedback.id)).where(and_(*conditions))
    total_result = await db.execute(total_query)
    total = total_result.scalar() or 0

    # 按状态统计
    status_query = (
        select(UserFeedback.status, func.count(UserFeedback.id))
        .where(and_(*conditions))
        .group_by(UserFeedback.status)
    )
    status_result = await db.execute(status_query)
    by_status = {row[0]: row[1] for row in status_result.all()}

    # 按类型统计
    type_query = (
        select(UserFeedback.feedback_type, func.count(UserFeedback.id))
        .where(and_(*conditions))
        .group_by(UserFeedback.feedback_type)
    )
    type_result = await db.execute(type_query)
    by_type = {row[0]: row[1] for row in type_result.all()}

    # 按严重程度统计
    severity_query = (
        select(UserFeedback.severity, func.count(UserFeedback.id))
        .where(and_(*conditions))
        .group_by(UserFeedback.severity)
    )
    severity_result = await db.execute(severity_query)
    by_severity = {row[0]: row[1] for row in severity_result.all()}

    # 纠错率（correction + fact_error + missing_info）
    correction_types = ["correction", "fact_error", "missing_info"]
    correction_count = sum(by_type.get(t, 0) for t in correction_types)
    correction_rate = correction_count / total if total > 0 else 0.0

    # 解决率
    resolved_count = by_status.get("resolved", 0)
    resolution_rate = resolved_count / total if total > 0 else 0.0

    # 平均解决时间（仅已解决的）
    avg_time_query = (
        select(
            func.avg(
                func.extract("epoch", UserFeedback.resolved_at - UserFeedback.created_at) / 3600
            )
        )
        .where(
            and_(
                *conditions,
                UserFeedback.status == "resolved",
                UserFeedback.resolved_at.isnot(None),
            )
        )
    )
    avg_time_result = await db.execute(avg_time_query)
    avg_resolution_time_hours = avg_time_result.scalar()

    # 高频问题（按 tags 统计）
    # 简化实现：按 feedback_type + severity 组合统计
    top_issues_query = (
        select(
            UserFeedback.feedback_type,
            UserFeedback.severity,
            func.count(UserFeedback.id).label("count"),
        )
        .where(and_(*conditions))
        .group_by(UserFeedback.feedback_type, UserFeedback.severity)
        .order_by(func.count(UserFeedback.id).desc())
        .limit(10)
    )
    top_issues_result = await db.execute(top_issues_query)
    top_issues = [
        {"type": row[0], "severity": row[1], "count": row[2]}
        for row in top_issues_result.all()
    ]

    return FeedbackStats(
        total=total,
        by_status=by_status,
        by_type=by_type,
        by_severity=by_severity,
        correction_rate=correction_rate,
        resolution_rate=resolution_rate,
        avg_resolution_time_hours=avg_resolution_time_hours,
        top_issues=top_issues,
    )


@router.get("/{feedback_id}", response_model=FeedbackResponse)
async def get_feedback(
    feedback_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取反馈详情"""
    query = select(UserFeedback).where(UserFeedback.id == feedback_id)
    result = await db.execute(query)
    feedback = result.scalar_one_or_none()

    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feedback not found: {feedback_id}",
        )

    return FeedbackResponse.model_validate(feedback)


@router.post("/{feedback_id}/resolve", response_model=FeedbackResponse)
async def resolve_feedback(
    feedback_id: str,
    request: FeedbackResolve,
    db: AsyncSession = Depends(get_db),
):
    """
    解决反馈

    绑定 content/evidence 修订版本
    """
    log = logger.bind(feedback_id=feedback_id, resolver=request.resolver)

    query = select(UserFeedback).where(UserFeedback.id == feedback_id)
    result = await db.execute(query)
    feedback = result.scalar_one_or_none()

    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feedback not found: {feedback_id}",
        )

    if feedback.status == FeedbackStatus.RESOLVED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feedback already resolved",
        )

    feedback.resolve(
        resolver=request.resolver,
        notes=request.notes,
        content_id=request.content_id,
        evidence_id=request.evidence_id,
    )

    await db.commit()
    await db.refresh(feedback)

    log.info(
        "feedback_resolved",
        content_id=request.content_id,
        evidence_id=request.evidence_id,
    )

    return FeedbackResponse.model_validate(feedback)


@router.post("/{feedback_id}/reject", response_model=FeedbackResponse)
async def reject_feedback(
    feedback_id: str,
    request: FeedbackReject,
    db: AsyncSession = Depends(get_db),
):
    """拒绝反馈"""
    log = logger.bind(feedback_id=feedback_id, reviewer=request.reviewer)

    query = select(UserFeedback).where(UserFeedback.id == feedback_id)
    result = await db.execute(query)
    feedback = result.scalar_one_or_none()

    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feedback not found: {feedback_id}",
        )

    feedback.reject(reviewer=request.reviewer, notes=request.notes)

    await db.commit()
    await db.refresh(feedback)

    log.info("feedback_rejected", notes=request.notes)

    return FeedbackResponse.model_validate(feedback)
