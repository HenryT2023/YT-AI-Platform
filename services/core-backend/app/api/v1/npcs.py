"""
NPC API

NPC 的 CRUD 操作
"""

from typing import Annotated, Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.db import get_db
from app.domain.npc import NPC

router = APIRouter()


class NPCCreate(BaseModel):
    """创建 NPC 请求"""

    site_id: str
    name: str = Field(..., min_length=1, max_length=100)
    display_name: Optional[str] = None
    npc_type: Optional[str] = Field(None, description="ancestor/craftsman/farmer/teacher")
    persona: dict[str, Any] = Field(..., description="NPC 人设配置")
    voice_id: Optional[str] = None
    scene_ids: Optional[List[UUID]] = None
    greeting_templates: Optional[List[str]] = None
    fallback_responses: Optional[List[str]] = None


class NPCUpdate(BaseModel):
    """更新 NPC 请求"""

    name: Optional[str] = None
    display_name: Optional[str] = None
    npc_type: Optional[str] = None
    persona: Optional[dict[str, Any]] = None
    voice_id: Optional[str] = None
    scene_ids: Optional[List[UUID]] = None
    greeting_templates: Optional[List[str]] = None
    fallback_responses: Optional[List[str]] = None
    status: Optional[str] = None


class NPCResponse(BaseModel):
    """NPC 响应"""

    id: UUID
    site_id: str
    name: str
    display_name: Optional[str]
    npc_type: Optional[str]
    persona: dict[str, Any]
    avatar_asset_id: Optional[UUID]
    voice_id: Optional[str]
    scene_ids: Optional[List[UUID]]
    greeting_templates: Optional[List[str]]
    fallback_responses: Optional[List[str]]
    status: str

    model_config = {"from_attributes": True}


@router.get("", response_model=List[NPCResponse])
async def list_npcs(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
    site_id: Optional[str] = Query(None),
    npc_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> List[NPC]:
    """获取 NPC 列表"""
    query = select(NPC).where(NPC.deleted_at.is_(None))
    if site_id:
        query = query.where(NPC.site_id == site_id)
    if npc_type:
        query = query.where(NPC.npc_type == npc_type)
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{npc_id}", response_model=NPCResponse)
async def get_npc(
    npc_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> NPC:
    """获取单个 NPC"""
    result = await db.execute(
        select(NPC).where(NPC.id == npc_id, NPC.deleted_at.is_(None))
    )
    npc = result.scalar_one_or_none()
    if not npc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NPC not found")
    return npc


@router.post("", response_model=NPCResponse, status_code=status.HTTP_201_CREATED)
async def create_npc(
    data: NPCCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> NPC:
    """创建 NPC"""
    npc = NPC(
        site_id=data.site_id,
        name=data.name,
        display_name=data.display_name,
        npc_type=data.npc_type,
        persona=data.persona,
        voice_id=data.voice_id,
        scene_ids=data.scene_ids,
        greeting_templates=data.greeting_templates,
        fallback_responses=data.fallback_responses,
        created_by=current_user,
    )
    db.add(npc)
    await db.flush()
    await db.refresh(npc)
    return npc


@router.patch("/{npc_id}", response_model=NPCResponse)
async def update_npc(
    npc_id: UUID,
    data: NPCUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> NPC:
    """更新 NPC"""
    result = await db.execute(
        select(NPC).where(NPC.id == npc_id, NPC.deleted_at.is_(None))
    )
    npc = result.scalar_one_or_none()
    if not npc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NPC not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(npc, field, value)

    await db.flush()
    await db.refresh(npc)
    return npc


@router.delete("/{npc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_npc(
    npc_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> None:
    """删除 NPC（软删除）"""
    from datetime import datetime, timezone

    result = await db.execute(
        select(NPC).where(NPC.id == npc_id, NPC.deleted_at.is_(None))
    )
    npc = result.scalar_one_or_none()
    if not npc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NPC not found")

    npc.deleted_at = datetime.now(timezone.utc)
    await db.flush()
