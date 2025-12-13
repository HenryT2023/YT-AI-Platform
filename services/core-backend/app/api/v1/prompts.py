"""
Prompt Registry API

提供 NPC Prompt 的 CRUD、版本管理、激活控制
"""

import structlog
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB
from app.database.models import NPCPrompt

router = APIRouter()
logger = structlog.get_logger(__name__)


# ============================================================
# Schema 定义
# ============================================================

class PromptPolicy(BaseModel):
    """Prompt 策略配置"""

    require_citations: bool = True
    min_confidence: float = 0.5
    must_cite_verified: bool = False
    forbidden_topics: List[str] = Field(default_factory=list)
    max_response_length: int = 500
    language: str = "zh-CN"
    tone: str = "formal"
    conservative_threshold: int = 1
    conservative_template: Optional[str] = None


class PromptMeta(BaseModel):
    """Prompt 元数据"""

    name: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None
    created_at: Optional[str] = None


class PromptCreate(BaseModel):
    """创建 Prompt"""

    npc_id: str = Field(..., description="NPC ID")
    content: str = Field(..., description="Prompt 正文")
    meta: PromptMeta = Field(default_factory=PromptMeta)
    policy: PromptPolicy = Field(default_factory=PromptPolicy)
    description: Optional[str] = Field(None, description="版本描述")
    set_active: bool = Field(False, description="是否设为激活版本")


class PromptUpdate(BaseModel):
    """更新 Prompt（创建新版本）"""

    content: str = Field(..., description="Prompt 正文")
    meta: Optional[PromptMeta] = None
    policy: Optional[PromptPolicy] = None
    description: Optional[str] = None
    set_active: bool = Field(False, description="是否设为激活版本")


class PromptResponse(BaseModel):
    """Prompt 响应"""

    id: str
    npc_id: str
    version: int
    active: bool
    content: str
    meta: dict
    policy: dict
    author: Optional[str]
    description: Optional[str]
    created_at: datetime
    updated_at: datetime


class PromptVersionItem(BaseModel):
    """版本列表项"""

    id: str
    version: int
    active: bool
    author: Optional[str]
    description: Optional[str]
    created_at: datetime


class PromptVersionsResponse(BaseModel):
    """版本列表响应"""

    npc_id: str
    versions: List[PromptVersionItem]
    total: int
    active_version: Optional[int]


class SetActiveRequest(BaseModel):
    """设置激活版本请求"""

    version: int = Field(..., description="要激活的版本号")


class SetActiveResponse(BaseModel):
    """设置激活版本响应"""

    npc_id: str
    previous_version: Optional[int]
    current_version: int
    message: str


# ============================================================
# API 端点
# ============================================================

@router.post("", response_model=PromptResponse, status_code=status.HTTP_201_CREATED)
async def create_prompt(
    request: PromptCreate,
    db: DB,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_site_id: str = Header(..., alias="X-Site-ID"),
    x_operator_id: Optional[str] = Header(None, alias="X-Operator-ID"),
) -> PromptResponse:
    """
    创建新 Prompt

    如果该 NPC 已有 Prompt，则创建新版本
    """
    log = logger.bind(npc_id=request.npc_id, tenant_id=x_tenant_id)
    log.info("create_prompt")

    # 查询当前最大版本号
    stmt = select(NPCPrompt.version).where(
        NPCPrompt.tenant_id == x_tenant_id,
        NPCPrompt.site_id == x_site_id,
        NPCPrompt.npc_id == request.npc_id,
        NPCPrompt.deleted_at.is_(None),
    ).order_by(NPCPrompt.version.desc()).limit(1)

    result = await db.execute(stmt)
    max_version = result.scalar_one_or_none()
    new_version = (max_version or 0) + 1

    # 如果要设为激活，先取消当前激活版本
    if request.set_active:
        await _deactivate_all(db, x_tenant_id, x_site_id, request.npc_id)

    # 创建新 Prompt
    prompt = NPCPrompt(
        tenant_id=x_tenant_id,
        site_id=x_site_id,
        npc_id=request.npc_id,
        version=new_version,
        active=request.set_active,
        content=request.content,
        meta=request.meta.model_dump(),
        policy=request.policy.model_dump(),
        author=request.meta.author or "system",
        operator_id=x_operator_id,
        description=request.description,
    )

    db.add(prompt)
    await db.flush()
    await db.refresh(prompt)

    log.info("prompt_created", version=new_version, active=request.set_active)

    return PromptResponse(
        id=prompt.id,
        npc_id=prompt.npc_id,
        version=prompt.version,
        active=prompt.active,
        content=prompt.content,
        meta=prompt.meta,
        policy=prompt.policy,
        author=prompt.author,
        description=prompt.description,
        created_at=prompt.created_at,
        updated_at=prompt.updated_at,
    )


@router.get("/{npc_id}", response_model=PromptResponse)
async def get_prompt(
    npc_id: str,
    db: DB,
    version: Optional[int] = Query(None, description="指定版本，不填则返回激活版本"),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_site_id: str = Header(..., alias="X-Site-ID"),
) -> PromptResponse:
    """
    获取 Prompt

    - 不指定版本：返回激活版本
    - 指定版本：返回指定版本
    """
    stmt = select(NPCPrompt).where(
        NPCPrompt.tenant_id == x_tenant_id,
        NPCPrompt.site_id == x_site_id,
        NPCPrompt.npc_id == npc_id,
        NPCPrompt.deleted_at.is_(None),
    )

    if version is not None:
        stmt = stmt.where(NPCPrompt.version == version)
    else:
        stmt = stmt.where(NPCPrompt.active == True)

    result = await db.execute(stmt)
    prompt = result.scalar_one_or_none()

    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt not found: {npc_id}" + (f" version {version}" if version else " (no active version)"),
        )

    return PromptResponse(
        id=prompt.id,
        npc_id=prompt.npc_id,
        version=prompt.version,
        active=prompt.active,
        content=prompt.content,
        meta=prompt.meta,
        policy=prompt.policy,
        author=prompt.author,
        description=prompt.description,
        created_at=prompt.created_at,
        updated_at=prompt.updated_at,
    )


@router.get("/{npc_id}/versions", response_model=PromptVersionsResponse)
async def list_versions(
    npc_id: str,
    db: DB,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_site_id: str = Header(..., alias="X-Site-ID"),
) -> PromptVersionsResponse:
    """
    列出 NPC 的所有 Prompt 版本
    """
    stmt = select(NPCPrompt).where(
        NPCPrompt.tenant_id == x_tenant_id,
        NPCPrompt.site_id == x_site_id,
        NPCPrompt.npc_id == npc_id,
        NPCPrompt.deleted_at.is_(None),
    ).order_by(NPCPrompt.version.desc())

    result = await db.execute(stmt)
    prompts = result.scalars().all()

    versions = [
        PromptVersionItem(
            id=p.id,
            version=p.version,
            active=p.active,
            author=p.author,
            description=p.description,
            created_at=p.created_at,
        )
        for p in prompts
    ]

    active_version = next((v.version for v in versions if v.active), None)

    return PromptVersionsResponse(
        npc_id=npc_id,
        versions=versions,
        total=len(versions),
        active_version=active_version,
    )


@router.post("/{npc_id}/set-active", response_model=SetActiveResponse)
async def set_active(
    npc_id: str,
    request: SetActiveRequest,
    db: DB,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_site_id: str = Header(..., alias="X-Site-ID"),
    x_operator_id: Optional[str] = Header(None, alias="X-Operator-ID"),
) -> SetActiveResponse:
    """
    设置激活版本

    支持回滚到历史版本
    """
    log = logger.bind(npc_id=npc_id, version=request.version)
    log.info("set_active_prompt")

    # 查询当前激活版本
    stmt = select(NPCPrompt.version).where(
        NPCPrompt.tenant_id == x_tenant_id,
        NPCPrompt.site_id == x_site_id,
        NPCPrompt.npc_id == npc_id,
        NPCPrompt.active == True,
        NPCPrompt.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    previous_version = result.scalar_one_or_none()

    # 查询目标版本是否存在
    stmt = select(NPCPrompt).where(
        NPCPrompt.tenant_id == x_tenant_id,
        NPCPrompt.site_id == x_site_id,
        NPCPrompt.npc_id == npc_id,
        NPCPrompt.version == request.version,
        NPCPrompt.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    target = result.scalar_one_or_none()

    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt version not found: {npc_id} v{request.version}",
        )

    # 取消当前激活版本
    await _deactivate_all(db, x_tenant_id, x_site_id, npc_id)

    # 激活目标版本
    target.active = True
    target.updated_at = datetime.utcnow()
    await db.flush()

    log.info("prompt_activated", previous=previous_version, current=request.version)

    return SetActiveResponse(
        npc_id=npc_id,
        previous_version=previous_version,
        current_version=request.version,
        message=f"Successfully activated version {request.version}" +
                (f" (was v{previous_version})" if previous_version else ""),
    )


@router.delete("/{npc_id}/versions/{version}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_version(
    npc_id: str,
    version: int,
    db: DB,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_site_id: str = Header(..., alias="X-Site-ID"),
    x_operator_id: Optional[str] = Header(None, alias="X-Operator-ID"),
):
    """
    删除指定版本（软删除）

    不能删除激活版本
    """
    stmt = select(NPCPrompt).where(
        NPCPrompt.tenant_id == x_tenant_id,
        NPCPrompt.site_id == x_site_id,
        NPCPrompt.npc_id == npc_id,
        NPCPrompt.version == version,
        NPCPrompt.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    prompt = result.scalar_one_or_none()

    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt version not found: {npc_id} v{version}",
        )

    if prompt.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete active version. Please activate another version first.",
        )

    prompt.deleted_at = datetime.utcnow()
    await db.flush()

    logger.info("prompt_deleted", npc_id=npc_id, version=version)


# ============================================================
# 辅助函数
# ============================================================

async def _deactivate_all(
    db: AsyncSession,
    tenant_id: str,
    site_id: str,
    npc_id: str,
) -> None:
    """取消所有激活版本"""
    stmt = (
        update(NPCPrompt)
        .where(
            NPCPrompt.tenant_id == tenant_id,
            NPCPrompt.site_id == site_id,
            NPCPrompt.npc_id == npc_id,
            NPCPrompt.active == True,
            NPCPrompt.deleted_at.is_(None),
        )
        .values(active=False, updated_at=datetime.utcnow())
    )
    await db.execute(stmt)
