"""
任务进度 API

游客任务进度管理
"""

from typing import Annotated, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.db import get_db
from app.services.quest_service import QuestService

router = APIRouter()


class StartQuestRequest(BaseModel):
    """开始任务请求"""
    quest_id: UUID


class SubmitStepRequest(BaseModel):
    """提交步骤请求"""
    quest_id: UUID
    step_number: int
    answer: Optional[str] = None
    location: Optional[dict[str, float]] = Field(None, description="位置信息 {lat, lng}")


class QuestProgressResponse(BaseModel):
    """任务进度响应"""
    quest_id: str
    status: str
    current_step: int
    progress: dict[str, Any]


class StepResultResponse(BaseModel):
    """步骤结果响应"""
    passed: bool
    current_step: int
    status: str
    hints: Optional[list[str]] = None


@router.post("/start", response_model=QuestProgressResponse)
async def start_quest(
    request: StartQuestRequest,
    visitor_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> QuestProgressResponse:
    """开始任务"""
    service = QuestService(db)

    try:
        visitor_quest = await service.start_quest(
            visitor_id=visitor_id,
            quest_id=request.quest_id,
        )
        return QuestProgressResponse(
            quest_id=str(visitor_quest.quest_id),
            status=visitor_quest.status,
            current_step=visitor_quest.current_step,
            progress=visitor_quest.progress or {},
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/submit", response_model=StepResultResponse)
async def submit_step(
    request: SubmitStepRequest,
    visitor_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> StepResultResponse:
    """提交任务步骤"""
    service = QuestService(db)

    try:
        result = await service.submit_step(
            visitor_id=visitor_id,
            quest_id=request.quest_id,
            step_number=request.step_number,
            answer=request.answer,
            location=request.location,
        )
        return StepResultResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
