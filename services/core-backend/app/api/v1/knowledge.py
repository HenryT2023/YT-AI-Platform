"""
知识条目 API

管理知识库内容，支持证据链追溯
"""

from datetime import datetime, timezone
from typing import Annotated, Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, ReqCtx, get_db
from app.core.permissions import Permission, check_permission
from app.domain.knowledge import KnowledgeEntry, KnowledgeType

router = APIRouter()


class KnowledgeCreate(BaseModel):
    """创建知识条目请求"""

    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    summary: Optional[str] = None
    knowledge_type: str = KnowledgeType.OTHER
    domains: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    source: Optional[str] = None
    source_url: Optional[str] = None
    source_date: Optional[datetime] = None
    credibility_score: float = Field(default=1.0, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeUpdate(BaseModel):
    """更新知识条目请求"""

    title: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    knowledge_type: Optional[str] = None
    domains: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    credibility_score: Optional[float] = Field(default=None, ge=0, le=1)
    metadata: Optional[dict[str, Any]] = None
    status: Optional[str] = None


class KnowledgeVerify(BaseModel):
    """验证知识条目请求"""

    verified: bool
    notes: Optional[str] = None


class KnowledgeResponse(BaseModel):
    """知识条目响应"""

    id: UUID
    tenant_id: str
    site_id: str
    title: str
    content: str
    summary: Optional[str]
    knowledge_type: str
    domains: List[str]
    tags: List[str]
    source: Optional[str]
    source_url: Optional[str]
    credibility_score: float
    verified: bool
    verified_by: Optional[str]
    verified_at: Optional[datetime]
    citation_count: int
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeSearchResult(BaseModel):
    """知识搜索结果"""

    id: UUID
    title: str
    content_snippet: str
    score: float
    source: Optional[str]
    verified: bool
    knowledge_type: str


@router.get("", response_model=List[KnowledgeResponse])
async def list_knowledge(
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: ReqCtx,
    knowledge_type: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
    verified_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> List[KnowledgeEntry]:
    """获取知识条目列表"""
    check_permission(ctx.user, Permission.KNOWLEDGE_READ)

    query = select(KnowledgeEntry).where(
        KnowledgeEntry.tenant_id == ctx.tenant_id,
        KnowledgeEntry.site_id == ctx.site_id,
        KnowledgeEntry.status == "active",
    )

    if knowledge_type:
        query = query.where(KnowledgeEntry.knowledge_type == knowledge_type)

    if domain:
        query = query.where(KnowledgeEntry.domains.contains([domain]))

    if verified_only:
        query = query.where(KnowledgeEntry.verified == True)

    query = query.order_by(KnowledgeEntry.created_at.desc())
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/search", response_model=List[KnowledgeSearchResult])
async def search_knowledge(
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: ReqCtx,
    q: str = Query(..., min_length=1, description="搜索关键词"),
    domains: Optional[str] = Query(None, description="逗号分隔的领域列表"),
    top_k: int = Query(10, ge=1, le=50),
) -> List[dict]:
    """
    搜索知识条目

    返回匹配的知识条目，可用于证据链
    """
    check_permission(ctx.user, Permission.KNOWLEDGE_READ)

    domain_list = domains.split(",") if domains else []

    query = select(KnowledgeEntry).where(
        KnowledgeEntry.tenant_id == ctx.tenant_id,
        KnowledgeEntry.site_id == ctx.site_id,
        KnowledgeEntry.status == "active",
    )

    if domain_list:
        query = query.where(KnowledgeEntry.domains.overlap(domain_list))

    # 简单文本匹配（生产环境应使用向量检索）
    query = query.where(
        KnowledgeEntry.content.ilike(f"%{q}%")
        | KnowledgeEntry.title.ilike(f"%{q}%")
    )

    query = query.limit(top_k)

    result = await db.execute(query)
    entries = result.scalars().all()

    return [
        {
            "id": entry.id,
            "title": entry.title,
            "content_snippet": entry.content[:300] if entry.content else "",
            "score": 0.8,  # 占位，实际应从向量检索获取
            "source": entry.source,
            "verified": entry.verified,
            "knowledge_type": entry.knowledge_type,
        }
        for entry in entries
    ]


@router.get("/{knowledge_id}", response_model=KnowledgeResponse)
async def get_knowledge(
    knowledge_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: ReqCtx,
) -> KnowledgeEntry:
    """获取单个知识条目"""
    check_permission(ctx.user, Permission.KNOWLEDGE_READ)

    result = await db.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.id == knowledge_id,
            KnowledgeEntry.tenant_id == ctx.tenant_id,
            KnowledgeEntry.site_id == ctx.site_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge entry not found",
        )
    return entry


@router.post("", response_model=KnowledgeResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge(
    data: KnowledgeCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: ReqCtx,
) -> KnowledgeEntry:
    """创建知识条目"""
    check_permission(ctx.user, Permission.KNOWLEDGE_WRITE)

    entry = KnowledgeEntry(
        tenant_id=ctx.tenant_id,
        site_id=ctx.site_id,
        title=data.title,
        content=data.content,
        summary=data.summary,
        knowledge_type=data.knowledge_type,
        domains=data.domains,
        tags=data.tags,
        source=data.source,
        source_url=data.source_url,
        source_date=data.source_date,
        credibility_score=data.credibility_score,
        metadata=data.metadata,
        created_by=ctx.user.username,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.patch("/{knowledge_id}", response_model=KnowledgeResponse)
async def update_knowledge(
    knowledge_id: UUID,
    data: KnowledgeUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: ReqCtx,
) -> KnowledgeEntry:
    """更新知识条目"""
    check_permission(ctx.user, Permission.KNOWLEDGE_WRITE)

    result = await db.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.id == knowledge_id,
            KnowledgeEntry.tenant_id == ctx.tenant_id,
            KnowledgeEntry.site_id == ctx.site_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge entry not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entry, field, value)

    # 更新后需要重新验证
    if any(k in update_data for k in ["title", "content"]):
        entry.verified = False
        entry.verified_by = None
        entry.verified_at = None

    await db.flush()
    await db.refresh(entry)
    return entry


@router.post("/{knowledge_id}/verify", response_model=KnowledgeResponse)
async def verify_knowledge(
    knowledge_id: UUID,
    data: KnowledgeVerify,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: ReqCtx,
) -> KnowledgeEntry:
    """验证知识条目（标记为已人工审核）"""
    check_permission(ctx.user, Permission.KNOWLEDGE_VERIFY)

    result = await db.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.id == knowledge_id,
            KnowledgeEntry.tenant_id == ctx.tenant_id,
            KnowledgeEntry.site_id == ctx.site_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge entry not found",
        )

    entry.verified = data.verified
    entry.verified_by = ctx.user.username
    entry.verified_at = datetime.now(timezone.utc)

    if data.notes:
        entry.metadata = entry.metadata or {}
        entry.metadata["verification_notes"] = data.notes

    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/{knowledge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge(
    knowledge_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: ReqCtx,
) -> None:
    """删除知识条目（软删除）"""
    check_permission(ctx.user, Permission.KNOWLEDGE_WRITE)

    result = await db.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.id == knowledge_id,
            KnowledgeEntry.tenant_id == ctx.tenant_id,
            KnowledgeEntry.site_id == ctx.site_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge entry not found",
        )

    entry.deleted_at = datetime.now(timezone.utc)
    await db.flush()
