"""
内容管理 API

提供内容的 CRUD 操作，支持多租户过滤
"""

from datetime import datetime, timezone
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from app.api.deps import DB, TenantCtx, CurrentUser, TenantSession
from app.database.models import Content, ContentStatus

router = APIRouter()


class ContentCreate(BaseModel):
    """创建内容请求"""

    content_type: str = Field(..., description="内容类型")
    title: str = Field(..., min_length=1, max_length=500)
    summary: Optional[str] = None
    body: str = Field(..., min_length=1)
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    domains: List[str] = Field(default_factory=list)
    source: Optional[str] = None
    source_url: Optional[str] = None
    credibility_score: float = Field(default=1.0, ge=0, le=1)


class ContentUpdate(BaseModel):
    """更新内容请求"""

    title: Optional[str] = None
    summary: Optional[str] = None
    body: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    domains: Optional[List[str]] = None
    source: Optional[str] = None
    credibility_score: Optional[float] = Field(default=None, ge=0, le=1)
    status: Optional[str] = None


class ContentResponse(BaseModel):
    """内容响应"""

    id: str
    tenant_id: str
    site_id: str
    content_type: str
    title: str
    summary: Optional[str]
    body: str
    category: Optional[str]
    tags: List[str]
    domains: List[str]
    source: Optional[str]
    credibility_score: float
    verified: bool
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=List[ContentResponse])
async def list_contents(
    ts: TenantSession,
    content_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    verified_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> List[Content]:
    """获取内容列表"""
    stmt = select(Content).where(Content.deleted_at.is_(None))

    if content_type:
        stmt = stmt.where(Content.content_type == content_type)
    if status:
        stmt = stmt.where(Content.status == status)
    if category:
        stmt = stmt.where(Content.category == category)
    if verified_only:
        stmt = stmt.where(Content.verified == True)

    stmt = stmt.order_by(Content.created_at.desc())
    stmt = stmt.offset(skip).limit(limit)

    result = await ts.execute(stmt)
    return list(result.scalars().all())


@router.get("/{content_id}", response_model=ContentResponse)
async def get_content(
    content_id: str,
    ts: TenantSession,
) -> Content:
    """获取单个内容"""
    stmt = select(Content).where(
        Content.id == content_id,
        Content.deleted_at.is_(None),
    )
    result = await ts.execute(stmt)
    content = result.scalar_one_or_none()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content not found",
        )
    return content


@router.post("", response_model=ContentResponse, status_code=status.HTTP_201_CREATED)
async def create_content(
    data: ContentCreate,
    ts: TenantSession,
    user: CurrentUser,
) -> Content:
    """创建内容"""
    content = Content(
        content_type=data.content_type,
        title=data.title,
        summary=data.summary,
        body=data.body,
        category=data.category,
        tags=data.tags,
        domains=data.domains,
        source=data.source,
        source_url=data.source_url,
        credibility_score=data.credibility_score,
        created_by=user.username,
    )
    ts.add(content)
    await ts.flush()
    await ts.refresh(content)
    return content


@router.patch("/{content_id}", response_model=ContentResponse)
async def update_content(
    content_id: str,
    data: ContentUpdate,
    ts: TenantSession,
    user: CurrentUser,
) -> Content:
    """更新内容"""
    stmt = select(Content).where(
        Content.id == content_id,
        Content.deleted_at.is_(None),
    )
    result = await ts.execute(stmt)
    content = result.scalar_one_or_none()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(content, field, value)

    content.updated_by = user.username

    await ts.flush()
    await ts.refresh(content)
    return content


@router.post("/{content_id}/publish", response_model=ContentResponse)
async def publish_content(
    content_id: str,
    ts: TenantSession,
    user: CurrentUser,
) -> Content:
    """发布内容"""
    stmt = select(Content).where(
        Content.id == content_id,
        Content.deleted_at.is_(None),
    )
    result = await ts.execute(stmt)
    content = result.scalar_one_or_none()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content not found",
        )

    content.publish(user.username)
    await ts.flush()
    await ts.refresh(content)
    return content


@router.delete("/{content_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_content(
    content_id: str,
    ts: TenantSession,
    user: CurrentUser,
) -> None:
    """删除内容（软删除）"""
    stmt = select(Content).where(
        Content.id == content_id,
        Content.deleted_at.is_(None),
    )
    result = await ts.execute(stmt)
    content = result.scalar_one_or_none()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content not found",
        )

    content.deleted_at = datetime.now(timezone.utc)
    content.updated_by = user.username
    await ts.flush()
