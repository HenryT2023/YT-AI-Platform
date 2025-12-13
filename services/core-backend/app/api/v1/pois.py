"""
兴趣点 API

POI 的 CRUD 操作
"""

from typing import Annotated, Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.db import get_db
from app.domain.poi import POI

router = APIRouter()


class POICreate(BaseModel):
    """创建 POI 请求"""

    site_id: str
    scene_id: Optional[UUID] = None
    name: str = Field(..., min_length=1, max_length=100)
    display_name: Optional[str] = None
    description: Optional[str] = None
    poi_type: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    indoor_position: Optional[dict[str, Any]] = None
    content: dict[str, Any] = Field(default_factory=dict)
    tags: Optional[List[str]] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0


class POIUpdate(BaseModel):
    """更新 POI 请求"""

    scene_id: Optional[UUID] = None
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    poi_type: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    indoor_position: Optional[dict[str, Any]] = None
    content: Optional[dict[str, Any]] = None
    tags: Optional[List[str]] = None
    metadata: Optional[dict[str, Any]] = None
    sort_order: Optional[int] = None
    status: Optional[str] = None


class POIResponse(BaseModel):
    """POI 响应"""

    id: UUID
    site_id: str
    scene_id: Optional[UUID]
    name: str
    display_name: Optional[str]
    description: Optional[str]
    poi_type: Optional[str]
    location_lat: Optional[float]
    location_lng: Optional[float]
    indoor_position: Optional[dict[str, Any]]
    content: dict[str, Any]
    tags: Optional[List[str]]
    metadata: dict[str, Any]
    sort_order: int
    status: str

    model_config = {"from_attributes": True}


@router.get("", response_model=List[POIResponse])
async def list_pois(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
    site_id: Optional[str] = Query(None),
    scene_id: Optional[UUID] = Query(None),
    poi_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> List[POI]:
    """获取 POI 列表"""
    query = select(POI).where(POI.deleted_at.is_(None))
    if site_id:
        query = query.where(POI.site_id == site_id)
    if scene_id:
        query = query.where(POI.scene_id == scene_id)
    if poi_type:
        query = query.where(POI.poi_type == poi_type)
    query = query.order_by(POI.sort_order).offset(skip).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{poi_id}", response_model=POIResponse)
async def get_poi(
    poi_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> POI:
    """获取单个 POI"""
    result = await db.execute(
        select(POI).where(POI.id == poi_id, POI.deleted_at.is_(None))
    )
    poi = result.scalar_one_or_none()
    if not poi:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="POI not found")
    return poi


@router.post("", response_model=POIResponse, status_code=status.HTTP_201_CREATED)
async def create_poi(
    data: POICreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> POI:
    """创建 POI"""
    poi = POI(
        site_id=data.site_id,
        scene_id=data.scene_id,
        name=data.name,
        display_name=data.display_name,
        description=data.description,
        poi_type=data.poi_type,
        location_lat=data.location_lat,
        location_lng=data.location_lng,
        indoor_position=data.indoor_position,
        content=data.content,
        tags=data.tags,
        metadata=data.metadata,
        sort_order=data.sort_order,
        created_by=current_user,
    )
    db.add(poi)
    await db.flush()
    await db.refresh(poi)
    return poi


@router.patch("/{poi_id}", response_model=POIResponse)
async def update_poi(
    poi_id: UUID,
    data: POIUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> POI:
    """更新 POI"""
    result = await db.execute(
        select(POI).where(POI.id == poi_id, POI.deleted_at.is_(None))
    )
    poi = result.scalar_one_or_none()
    if not poi:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="POI not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(poi, field, value)

    await db.flush()
    await db.refresh(poi)
    return poi


@router.delete("/{poi_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_poi(
    poi_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> None:
    """删除 POI（软删除）"""
    from datetime import datetime, timezone

    result = await db.execute(
        select(POI).where(POI.id == poi_id, POI.deleted_at.is_(None))
    )
    poi = result.scalar_one_or_none()
    if not poi:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="POI not found")

    poi.deleted_at = datetime.now(timezone.utc)
    await db.flush()
