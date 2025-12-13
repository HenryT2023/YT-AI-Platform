"""
站点 API

站点的 CRUD 操作
"""

from typing import Annotated, Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.db import get_db
from app.domain.site import Site

router = APIRouter()


class SiteCreate(BaseModel):
    """创建站点请求"""

    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    display_name: Optional[str] = None
    description: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)
    theme: dict[str, Any] = Field(default_factory=dict)
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    timezone: str = "Asia/Shanghai"


class SiteUpdate(BaseModel):
    """更新站点请求"""

    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    theme: Optional[dict[str, Any]] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    timezone: Optional[str] = None
    status: Optional[str] = None


class SiteResponse(BaseModel):
    """站点响应"""

    id: str
    name: str
    display_name: Optional[str]
    description: Optional[str]
    config: dict[str, Any]
    theme: dict[str, Any]
    location_lat: Optional[float]
    location_lng: Optional[float]
    timezone: str
    status: str

    model_config = {"from_attributes": True}


@router.get("", response_model=List[SiteResponse])
async def list_sites(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
    status: Optional[str] = Query(None, description="按状态筛选"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> List[Site]:
    """获取站点列表"""
    query = select(Site).where(Site.deleted_at.is_(None))
    if status:
        query = query.where(Site.status == status)
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{site_id}", response_model=SiteResponse)
async def get_site(
    site_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> Site:
    """获取单个站点"""
    result = await db.execute(
        select(Site).where(Site.id == site_id, Site.deleted_at.is_(None))
    )
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    return site


@router.post("", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
async def create_site(
    data: SiteCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> Site:
    """创建站点"""
    existing = await db.execute(select(Site).where(Site.id == data.id))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Site ID already exists"
        )

    site = Site(
        id=data.id,
        name=data.name,
        display_name=data.display_name,
        description=data.description,
        config=data.config,
        theme=data.theme,
        location_lat=data.location_lat,
        location_lng=data.location_lng,
        timezone=data.timezone,
        created_by=current_user,
    )
    db.add(site)
    await db.flush()
    await db.refresh(site)
    return site


@router.patch("/{site_id}", response_model=SiteResponse)
async def update_site(
    site_id: str,
    data: SiteUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> Site:
    """更新站点"""
    result = await db.execute(
        select(Site).where(Site.id == site_id, Site.deleted_at.is_(None))
    )
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(site, field, value)

    await db.flush()
    await db.refresh(site)
    return site


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site(
    site_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> None:
    """删除站点（软删除）"""
    from datetime import datetime, timezone

    result = await db.execute(
        select(Site).where(Site.id == site_id, Site.deleted_at.is_(None))
    )
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")

    site.deleted_at = datetime.now(timezone.utc)
    await db.flush()
