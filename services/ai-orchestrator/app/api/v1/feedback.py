"""
用户反馈 API（ai-orchestrator 侧）

提供纠错入口，自动写 feedback 并关联 trace
"""

import structlog
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.feedback.client import (
    FeedbackClient,
    FeedbackSubmission,
    get_feedback_client,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


class CorrectionRequest(BaseModel):
    """纠错请求"""
    trace_id: str = Field(..., description="关联的 trace ID")
    content: str = Field(..., description="纠错内容（用户描述的问题）")
    original_response: str = Field(..., description="原始回答")
    suggested_fix: Optional[str] = Field(None, description="建议的修正")
    severity: str = Field("medium", description="严重程度: low/medium/high/critical")
    conversation_id: Optional[str] = Field(None, description="会话 ID")
    npc_id: Optional[str] = Field(None, description="NPC ID")
    tenant_id: str = Field("yantian", description="租户 ID")
    site_id: str = Field("yantian-main", description="站点 ID")


class CorrectionResponse(BaseModel):
    """纠错响应"""
    success: bool
    feedback_id: Optional[str] = None
    message: str


@router.post("/correction", response_model=CorrectionResponse)
async def submit_correction(request: CorrectionRequest):
    """
    提交纠错反馈

    用户触发纠错入口时调用，自动写 feedback 并关联 trace
    """
    log = logger.bind(
        trace_id=request.trace_id,
        npc_id=request.npc_id,
    )

    client = get_feedback_client()

    result = await client.submit_correction(
        trace_id=request.trace_id,
        content=request.content,
        original_response=request.original_response,
        suggested_fix=request.suggested_fix,
        severity=request.severity,
        tenant_id=request.tenant_id,
        site_id=request.site_id,
        npc_id=request.npc_id,
        conversation_id=request.conversation_id,
    )

    if result:
        log.info("correction_submitted", feedback_id=result.feedback_id)
        return CorrectionResponse(
            success=True,
            feedback_id=result.feedback_id,
            message="纠错反馈已提交，感谢您的反馈！",
        )
    else:
        log.error("correction_submit_failed")
        return CorrectionResponse(
            success=False,
            feedback_id=None,
            message="提交失败，请稍后重试",
        )


class RatingRequest(BaseModel):
    """评分请求"""
    trace_id: str = Field(..., description="关联的 trace ID")
    rating: int = Field(..., ge=1, le=5, description="评分 1-5")
    comment: Optional[str] = Field(None, description="评论")
    conversation_id: Optional[str] = Field(None, description="会话 ID")
    npc_id: Optional[str] = Field(None, description="NPC ID")
    tenant_id: str = Field("yantian", description="租户 ID")
    site_id: str = Field("yantian-main", description="站点 ID")


@router.post("/rating", response_model=CorrectionResponse)
async def submit_rating(request: RatingRequest):
    """
    提交评分反馈
    """
    log = logger.bind(
        trace_id=request.trace_id,
        rating=request.rating,
    )

    client = get_feedback_client()

    submission = FeedbackSubmission(
        trace_id=request.trace_id,
        conversation_id=request.conversation_id,
        feedback_type="rating",
        severity="low",
        content=f"评分: {request.rating}/5" + (f"\n评论: {request.comment}" if request.comment else ""),
        tags=[f"rating:{request.rating}", f"npc:{request.npc_id}"] if request.npc_id else [f"rating:{request.rating}"],
        tenant_id=request.tenant_id,
        site_id=request.site_id,
        metadata={"rating": request.rating, "npc_id": request.npc_id},
    )

    result = await client.submit_feedback(submission)

    if result:
        log.info("rating_submitted", feedback_id=result.feedback_id)
        return CorrectionResponse(
            success=True,
            feedback_id=result.feedback_id,
            message="感谢您的评价！",
        )
    else:
        log.error("rating_submit_failed")
        return CorrectionResponse(
            success=False,
            feedback_id=None,
            message="提交失败，请稍后重试",
        )
