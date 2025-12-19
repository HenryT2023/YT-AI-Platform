"""
任务提交管理 API

v0.2-3: 只读 API，用于运营查看任务提交情况
v0.2.2: 新增审核 API (approve/reject)

需要 JWT + RBAC
"""

import structlog
from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Path, HTTPException, Body
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import ViewerOrAbove, OperatorOrAbove
from app.core.tenant_scope import RequiredScope
from app.db import get_db
from app.database.models.quest_submission import QuestSubmission
from app.database.models import VisitorProfile
from app.services.achievement_service import check_achievements_for_user

logger = structlog.get_logger(__name__)

router = APIRouter()


# ============================================================
# Schemas
# ============================================================

class QuestSubmissionItem(BaseModel):
    """任务提交记录"""
    id: str
    tenant_id: str
    site_id: str
    session_id: str
    quest_id: str
    proof_type: str
    proof_payload: dict
    status: str
    # v0.2.2 审核字段
    review_status: str
    review_comment: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReviewRequest(BaseModel):
    """审核请求"""
    comment: Optional[str] = Field(None, max_length=500, description="审核备注")


class ReviewResponse(BaseModel):
    """审核响应"""
    id: str
    review_status: str
    review_comment: Optional[str] = None
    reviewed_at: datetime
    reviewed_by: str


class QuestSubmissionListResponse(BaseModel):
    """任务提交列表响应"""
    items: List[QuestSubmissionItem]
    total: int
    limit: int
    offset: int


class QuestSubmissionStats(BaseModel):
    """任务提交统计"""
    total_submissions: int
    unique_sessions: int
    unique_quests: int
    status_breakdown: dict
    # v0.2.2 审核统计
    approved_count: int = 0
    rejected_count: int = 0
    pending_count: int = 0
    completion_rate: float = 0.0  # approved / total


# ============================================================
# API Endpoints
# ============================================================

@router.get("", response_model=QuestSubmissionListResponse)
async def list_quest_submissions(
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
    quest_id: Optional[str] = Query(None, description="筛选任务 ID"),
    session_id: Optional[str] = Query(None, description="筛选会话 ID"),
    status: Optional[str] = Query(None, description="筛选状态"),
    limit: int = Query(50, ge=1, le=200, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
) -> QuestSubmissionListResponse:
    """
    获取任务提交列表（只读）
    
    需要 viewer 及以上权限
    v0.2.3: 从 Header 读取 tenant/site scope
    """
    # 构建查询（使用 Header 中的 scope）
    base_query = select(QuestSubmission).where(
        QuestSubmission.tenant_id == scope.tenant_id,
        QuestSubmission.site_id == scope.site_id,
    )
    
    # 筛选条件
    if quest_id:
        base_query = base_query.where(QuestSubmission.quest_id == quest_id)
    if session_id:
        base_query = base_query.where(QuestSubmission.session_id == session_id)
    if status:
        base_query = base_query.where(QuestSubmission.status == status)
    
    # 统计总数
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 分页查询
    query = base_query.order_by(desc(QuestSubmission.created_at)).offset(offset).limit(limit)
    result = await db.execute(query)
    submissions = result.scalars().all()
    
    items = [
        QuestSubmissionItem(
            id=str(s.id),
            tenant_id=s.tenant_id,
            site_id=s.site_id,
            session_id=s.session_id,
            quest_id=s.quest_id,
            proof_type=s.proof_type,
            proof_payload=s.proof_payload,
            status=s.status,
            review_status=s.review_status,
            review_comment=s.review_comment,
            reviewed_at=s.reviewed_at,
            reviewed_by=s.reviewed_by,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in submissions
    ]
    
    return QuestSubmissionListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", response_model=QuestSubmissionStats)
async def get_quest_submission_stats(
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> QuestSubmissionStats:
    """
    获取任务提交统计（只读）
    
    需要 viewer 及以上权限
    v0.2.3: 从 Header 读取 tenant/site scope
    """
    base_filter = [
        QuestSubmission.tenant_id == scope.tenant_id,
        QuestSubmission.site_id == scope.site_id,
    ]
    
    # 总提交数
    total_result = await db.execute(
        select(func.count(QuestSubmission.id)).where(*base_filter)
    )
    total_submissions = total_result.scalar() or 0
    
    # 唯一会话数
    sessions_result = await db.execute(
        select(func.count(func.distinct(QuestSubmission.session_id))).where(*base_filter)
    )
    unique_sessions = sessions_result.scalar() or 0
    
    # 唯一任务数
    quests_result = await db.execute(
        select(func.count(func.distinct(QuestSubmission.quest_id))).where(*base_filter)
    )
    unique_quests = quests_result.scalar() or 0
    
    # 状态分布
    status_result = await db.execute(
        select(QuestSubmission.status, func.count(QuestSubmission.id))
        .where(*base_filter)
        .group_by(QuestSubmission.status)
    )
    status_breakdown = {row[0]: row[1] for row in status_result.all()}
    
    # v0.2.2 审核状态统计
    review_result = await db.execute(
        select(QuestSubmission.review_status, func.count(QuestSubmission.id))
        .where(*base_filter)
        .group_by(QuestSubmission.review_status)
    )
    review_breakdown = {row[0]: row[1] for row in review_result.all()}
    
    approved_count = review_breakdown.get("approved", 0)
    rejected_count = review_breakdown.get("rejected", 0)
    pending_count = review_breakdown.get("pending", 0)
    completion_rate = (approved_count / total_submissions * 100) if total_submissions > 0 else 0.0
    
    return QuestSubmissionStats(
        total_submissions=total_submissions,
        unique_sessions=unique_sessions,
        unique_quests=unique_quests,
        status_breakdown=status_breakdown,
        approved_count=approved_count,
        rejected_count=rejected_count,
        pending_count=pending_count,
        completion_rate=round(completion_rate, 2),
    )


# ============================================================
# 审核 API (v0.2.2)
# ============================================================

@router.post("/{submission_id}/approve", response_model=ReviewResponse)
async def approve_submission(
    submission_id: str,
    current_user: OperatorOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
    comment: Optional[str] = Query(default=None, description="审核备注"),
) -> ReviewResponse:
    """
    审核通过任务提交
    
    需要 operator 及以上权限
    v0.2.3: 从 Header 读取 tenant/site scope，验证 submission 归属
    """
    log = logger.bind(submission_id=submission_id, user_id=current_user.id)
    
    # 查询提交记录（必须属于当前 scope）
    result = await db.execute(
        select(QuestSubmission).where(
            QuestSubmission.id == submission_id,
            QuestSubmission.tenant_id == scope.tenant_id,
            QuestSubmission.site_id == scope.site_id,
        )
    )
    submission = result.scalar_one_or_none()
    
    if not submission:
        log.warning("submission_not_found_or_scope_mismatch")
        raise HTTPException(status_code=404, detail="提交记录不存在或不属于当前站点")
    
    # 检查是否已审核
    if submission.review_status != "pending":
        log.warning("submission_already_reviewed", current_status=submission.review_status)
        raise HTTPException(
            status_code=400,
            detail=f"该提交已被审核: {submission.review_status}"
        )
    
    # 更新审核状态
    submission.review_status = "approved"
    submission.review_comment = comment
    submission.reviewed_by = str(current_user.id)
    # 使用 DB now() 确保时间一致性
    await db.execute(
        text("UPDATE quest_submissions SET reviewed_at = now(), updated_at = now() WHERE id = :id"),
        {"id": submission_id}
    )
    
    await db.commit()
    await db.refresh(submission)
    
    log.info("submission_approved", quest_id=submission.quest_id)
    
    # v0.2.0: 更新游客画像并触发成就检查
    try:
        # 从 session_id 获取 user_id（session_id 格式通常包含 user_id）
        # 或者从 proof_payload 中获取
        user_id_str = submission.proof_payload.get("user_id") if submission.proof_payload else None
        
        if user_id_str:
            user_id = UUID(user_id_str)
            
            # 更新游客画像的任务完成计数
            profile_result = await db.execute(
                select(VisitorProfile).where(
                    VisitorProfile.user_id == user_id,
                    VisitorProfile.tenant_id == scope.tenant_id,
                    VisitorProfile.site_id == scope.site_id,
                )
            )
            profile = profile_result.scalar_one_or_none()
            if profile:
                profile.quest_completed_count += 1
                await db.commit()
                log.info("visitor_profile_updated", user_id=str(user_id), quest_completed_count=profile.quest_completed_count)
            
            # 触发成就检查
            unlocked = await check_achievements_for_user(
                db=db,
                tenant_id=scope.tenant_id,
                site_id=scope.site_id,
                user_id=user_id,
                event_name="quest_completed",
                event_data={"quest_id": submission.quest_id},
            )
            if unlocked:
                log.info("achievements_unlocked", user_id=str(user_id), count=len(unlocked), achievements=[a.code for a in unlocked])
                await db.commit()
    except Exception as e:
        log.warning("failed_to_update_profile_or_achievements", error=str(e))
    
    return ReviewResponse(
        id=str(submission.id),
        review_status=submission.review_status,
        review_comment=submission.review_comment,
        reviewed_at=submission.reviewed_at,
        reviewed_by=submission.reviewed_by,
    )


@router.post("/{submission_id}/reject", response_model=ReviewResponse)
async def reject_submission(
    submission_id: str,
    current_user: OperatorOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
    comment: Optional[str] = Query(default=None, description="驳回原因"),
) -> ReviewResponse:
    """
    驳回任务提交
    
    需要 operator 及以上权限
    v0.2.3: 从 Header 读取 tenant/site scope，验证 submission 归属
    """
    log = logger.bind(submission_id=submission_id, user_id=current_user.id)
    
    # 查询提交记录（必须属于当前 scope）
    result = await db.execute(
        select(QuestSubmission).where(
            QuestSubmission.id == submission_id,
            QuestSubmission.tenant_id == scope.tenant_id,
            QuestSubmission.site_id == scope.site_id,
        )
    )
    submission = result.scalar_one_or_none()
    
    if not submission:
        log.warning("submission_not_found_or_scope_mismatch")
        raise HTTPException(status_code=404, detail="提交记录不存在或不属于当前站点")
    
    # 检查是否已审核
    if submission.review_status != "pending":
        log.warning("submission_already_reviewed", current_status=submission.review_status)
        raise HTTPException(
            status_code=400,
            detail=f"该提交已被审核: {submission.review_status}"
        )
    
    # 更新审核状态
    submission.review_status = "rejected"
    submission.review_comment = comment
    submission.reviewed_by = str(current_user.id)
    # 使用 DB now() 确保时间一致性
    await db.execute(
        text("UPDATE quest_submissions SET reviewed_at = now(), updated_at = now() WHERE id = :id"),
        {"id": submission_id}
    )
    
    await db.commit()
    await db.refresh(submission)
    
    log.info("submission_rejected", quest_id=submission.quest_id, comment=comment)
    
    return ReviewResponse(
        id=str(submission.id),
        review_status=submission.review_status,
        review_comment=submission.review_comment,
        reviewed_at=submission.reviewed_at,
        reviewed_by=submission.reviewed_by,
    )
