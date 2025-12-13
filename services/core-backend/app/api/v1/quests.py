"""
研学任务 API

Quest 的 CRUD 操作
"""

from typing import Annotated, Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.db import get_db
from app.domain.quest import Quest

router = APIRouter()


class QuestCreate(BaseModel):
    """创建任务请求"""

    site_id: str
    name: str = Field(..., min_length=1, max_length=100)
    display_name: Optional[str] = None
    description: Optional[str] = None
    quest_type: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)
    rewards: dict[str, Any] = Field(default_factory=dict)
    prerequisites: dict[str, Any] = Field(default_factory=dict)
    scene_ids: Optional[List[UUID]] = None
    difficulty: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    sort_order: int = 0


class QuestUpdate(BaseModel):
    """更新任务请求"""

    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    quest_type: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    rewards: Optional[dict[str, Any]] = None
    prerequisites: Optional[dict[str, Any]] = None
    scene_ids: Optional[List[UUID]] = None
    difficulty: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    sort_order: Optional[int] = None
    status: Optional[str] = None


class QuestResponse(BaseModel):
    """任务响应"""

    id: UUID
    site_id: str
    name: str
    display_name: Optional[str]
    description: Optional[str]
    quest_type: Optional[str]
    config: dict[str, Any]
    rewards: dict[str, Any]
    prerequisites: dict[str, Any]
    scene_ids: Optional[List[UUID]]
    difficulty: Optional[str]
    category: Optional[str]
    tags: Optional[List[str]]
    sort_order: int
    status: str

    model_config = {"from_attributes": True}


@router.get("", response_model=List[QuestResponse])
async def list_quests(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
    site_id: Optional[str] = Query(None),
    quest_type: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> List[Quest]:
    """获取任务列表"""
    query = select(Quest).where(Quest.deleted_at.is_(None))
    if site_id:
        query = query.where(Quest.site_id == site_id)
    if quest_type:
        query = query.where(Quest.quest_type == quest_type)
    if difficulty:
        query = query.where(Quest.difficulty == difficulty)
    query = query.order_by(Quest.sort_order).offset(skip).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{quest_id}", response_model=QuestResponse)
async def get_quest(
    quest_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> Quest:
    """获取单个任务"""
    result = await db.execute(
        select(Quest).where(Quest.id == quest_id, Quest.deleted_at.is_(None))
    )
    quest = result.scalar_one_or_none()
    if not quest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quest not found")
    return quest


@router.post("", response_model=QuestResponse, status_code=status.HTTP_201_CREATED)
async def create_quest(
    data: QuestCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> Quest:
    """创建任务"""
    quest = Quest(
        site_id=data.site_id,
        name=data.name,
        display_name=data.display_name,
        description=data.description,
        quest_type=data.quest_type,
        config=data.config,
        rewards=data.rewards,
        prerequisites=data.prerequisites,
        scene_ids=data.scene_ids,
        difficulty=data.difficulty,
        category=data.category,
        tags=data.tags,
        sort_order=data.sort_order,
        created_by=current_user,
    )
    db.add(quest)
    await db.flush()
    await db.refresh(quest)
    return quest


@router.patch("/{quest_id}", response_model=QuestResponse)
async def update_quest(
    quest_id: UUID,
    data: QuestUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> Quest:
    """更新任务"""
    result = await db.execute(
        select(Quest).where(Quest.id == quest_id, Quest.deleted_at.is_(None))
    )
    quest = result.scalar_one_or_none()
    if not quest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quest not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(quest, field, value)

    await db.flush()
    await db.refresh(quest)
    return quest


@router.delete("/{quest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quest(
    quest_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> None:
    """删除任务（软删除）"""
    from datetime import datetime, timezone

    result = await db.execute(
        select(Quest).where(Quest.id == quest_id, Quest.deleted_at.is_(None))
    )
    quest = result.scalar_one_or_none()
    if not quest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quest not found")

    quest.deleted_at = datetime.now(timezone.utc)
    await db.flush()
