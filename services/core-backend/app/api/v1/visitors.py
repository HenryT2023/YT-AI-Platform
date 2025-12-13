"""
游客 API

游客档案和任务进度管理
"""

from typing import Annotated, Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.db import get_db
from app.domain.visitor import Visitor, VisitorQuest

router = APIRouter()


class VisitorCreate(BaseModel):
    """创建游客请求"""

    external_id: Optional[str] = None
    identity_provider: Optional[str] = None
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    profile: dict[str, Any] = Field(default_factory=dict)


class VisitorUpdate(BaseModel):
    """更新游客请求"""

    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    profile: Optional[dict[str, Any]] = None


class VisitorResponse(BaseModel):
    """游客响应"""

    id: UUID
    external_id: Optional[str]
    identity_provider: Optional[str]
    nickname: Optional[str]
    avatar_url: Optional[str]
    profile: dict[str, Any]
    stats: dict[str, Any]

    model_config = {"from_attributes": True}


class VisitorQuestResponse(BaseModel):
    """游客任务进度响应"""

    id: UUID
    visitor_id: UUID
    quest_id: UUID
    status: str
    current_step: int
    progress: dict[str, Any]
    score: int

    model_config = {"from_attributes": True}


@router.get("", response_model=List[VisitorResponse])
async def list_visitors(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> List[Visitor]:
    """获取游客列表"""
    query = select(Visitor).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{visitor_id}", response_model=VisitorResponse)
async def get_visitor(
    visitor_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> Visitor:
    """获取单个游客"""
    result = await db.execute(select(Visitor).where(Visitor.id == visitor_id))
    visitor = result.scalar_one_or_none()
    if not visitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visitor not found")
    return visitor


@router.post("", response_model=VisitorResponse, status_code=status.HTTP_201_CREATED)
async def create_visitor(
    data: VisitorCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> Visitor:
    """创建游客"""
    visitor = Visitor(
        external_id=data.external_id,
        identity_provider=data.identity_provider,
        nickname=data.nickname,
        avatar_url=data.avatar_url,
        phone=data.phone,
        profile=data.profile,
    )
    db.add(visitor)
    await db.flush()
    await db.refresh(visitor)
    return visitor


@router.patch("/{visitor_id}", response_model=VisitorResponse)
async def update_visitor(
    visitor_id: UUID,
    data: VisitorUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> Visitor:
    """更新游客"""
    result = await db.execute(select(Visitor).where(Visitor.id == visitor_id))
    visitor = result.scalar_one_or_none()
    if not visitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visitor not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(visitor, field, value)

    await db.flush()
    await db.refresh(visitor)
    return visitor


@router.get("/{visitor_id}/quests", response_model=List[VisitorQuestResponse])
async def get_visitor_quests(
    visitor_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
    quest_status: Optional[str] = Query(None, alias="status"),
) -> List[VisitorQuest]:
    """获取游客的任务进度"""
    query = select(VisitorQuest).where(VisitorQuest.visitor_id == visitor_id)
    if quest_status:
        query = query.where(VisitorQuest.status == quest_status)

    result = await db.execute(query)
    return list(result.scalars().all())
