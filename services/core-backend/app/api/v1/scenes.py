"""
场景 API

场景的 CRUD 操作
"""

from typing import Annotated, Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.tenant_scope import RequiredScope
from app.db import get_db
from app.domain.scene import Scene

router = APIRouter()


class SceneCreate(BaseModel):
    """创建场景请求"""

    site_id: str
    name: str = Field(..., min_length=1, max_length=100)
    display_name: Optional[str] = None
    description: Optional[str] = None
    scene_type: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    boundary: Optional[dict[str, Any]] = None
    config: dict[str, Any] = Field(default_factory=dict)
    parent_scene_id: Optional[UUID] = None
    sort_order: int = 0


class SceneUpdate(BaseModel):
    """更新场景请求"""

    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    scene_type: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    boundary: Optional[dict[str, Any]] = None
    config: Optional[dict[str, Any]] = None
    parent_scene_id: Optional[UUID] = None
    sort_order: Optional[int] = None
    status: Optional[str] = None


class SceneResponse(BaseModel):
    """场景响应"""

    id: UUID
    site_id: str
    name: str
    display_name: Optional[str]
    description: Optional[str]
    scene_type: Optional[str]
    location_lat: Optional[float]
    location_lng: Optional[float]
    boundary: Optional[dict[str, Any]]
    config: dict[str, Any]
    parent_scene_id: Optional[UUID]
    sort_order: int
    status: str

    model_config = {"from_attributes": True}


@router.get("", response_model=List[SceneResponse])
async def list_scenes(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
    scope: RequiredScope,
    scene_type: Optional[str] = Query(None, description="按类型筛选"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> List[Scene]:
    """获取场景列表
    
    v0.2.4: 从 Header 读取 tenant/site scope，强制过滤
    """
    query = select(Scene).where(
        Scene.deleted_at.is_(None),
        Scene.site_id == scope.site_id,
    )
    if scene_type:
        query = query.where(Scene.scene_type == scene_type)
    query = query.order_by(Scene.sort_order).offset(skip).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{scene_id}", response_model=SceneResponse)
async def get_scene(
    scene_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
    scope: RequiredScope,
) -> Scene:
    """获取单个场景
    
    v0.2.4: 验证场景属于当前 scope
    """
    result = await db.execute(
        select(Scene).where(
            Scene.id == scene_id,
            Scene.deleted_at.is_(None),
            Scene.site_id == scope.site_id,
        )
    )
    scene = result.scalar_one_or_none()
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    return scene


@router.post("", response_model=SceneResponse, status_code=status.HTTP_201_CREATED)
async def create_scene(
    data: SceneCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
    scope: RequiredScope,
) -> Scene:
    """创建场景
    
    v0.2.4: site_id 从 scope 获取
    """
    scene = Scene(
        site_id=scope.site_id,
        name=data.name,
        display_name=data.display_name,
        description=data.description,
        scene_type=data.scene_type,
        location_lat=data.location_lat,
        location_lng=data.location_lng,
        boundary=data.boundary,
        config=data.config,
        parent_scene_id=data.parent_scene_id,
        sort_order=data.sort_order,
        created_by=current_user,
    )
    db.add(scene)
    await db.flush()
    await db.refresh(scene)
    return scene


@router.patch("/{scene_id}", response_model=SceneResponse)
async def update_scene(
    scene_id: UUID,
    data: SceneUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
    scope: RequiredScope,
) -> Scene:
    """更新场景
    
    v0.2.4: 验证场景属于当前 scope
    """
    result = await db.execute(
        select(Scene).where(
            Scene.id == scene_id,
            Scene.deleted_at.is_(None),
            Scene.site_id == scope.site_id,
        )
    )
    scene = result.scalar_one_or_none()
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(scene, field, value)

    await db.flush()
    await db.refresh(scene)
    return scene


@router.delete("/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scene(
    scene_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
    scope: RequiredScope,
) -> None:
    """删除场景（软删除）
    
    v0.2.4: 验证场景属于当前 scope
    """
    from datetime import datetime, timezone

    result = await db.execute(
        select(Scene).where(
            Scene.id == scene_id,
            Scene.deleted_at.is_(None),
            Scene.site_id == scope.site_id,
        )
    )
    scene = result.scalar_one_or_none()
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")

    scene.deleted_at = datetime.now(timezone.utc)
    await db.flush()
