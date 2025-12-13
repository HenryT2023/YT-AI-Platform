"""
租户管理 API

仅超级管理员可访问
"""

from typing import Annotated, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_db
from app.core.permissions import Permission, check_permission
from app.domain.tenant import Tenant

router = APIRouter()


class TenantCreate(BaseModel):
    """创建租户请求"""

    id: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-z0-9-]+$")
    name: str = Field(..., min_length=1, max_length=100)
    display_name: Optional[str] = None
    description: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    plan: str = "free"
    config: dict[str, Any] = Field(default_factory=dict)


class TenantUpdate(BaseModel):
    """更新租户请求"""

    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    plan: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    status: Optional[str] = None


class TenantResponse(BaseModel):
    """租户响应"""

    id: str
    name: str
    display_name: Optional[str]
    description: Optional[str]
    plan: str
    contact_email: Optional[str]
    status: str

    model_config = {"from_attributes": True}


@router.get("", response_model=List[TenantResponse])
async def list_tenants(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> List[Tenant]:
    """获取租户列表（仅超级管理员）"""
    check_permission(user, Permission.TENANT_READ)

    query = select(Tenant).where(Tenant.deleted_at.is_(None))
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> Tenant:
    """获取单个租户"""
    check_permission(user, Permission.TENANT_READ)

    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None))
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    data: TenantCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> Tenant:
    """创建租户（仅超级管理员）"""
    check_permission(user, Permission.TENANT_WRITE)

    # 检查 ID 是否已存在
    existing = await db.execute(select(Tenant).where(Tenant.id == data.id))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant ID '{data.id}' already exists",
        )

    tenant = Tenant(
        id=data.id,
        name=data.name,
        display_name=data.display_name,
        description=data.description,
        contact_email=data.contact_email,
        contact_phone=data.contact_phone,
        plan=data.plan,
        config=data.config,
        created_by=user.username,
    )
    db.add(tenant)
    await db.flush()
    await db.refresh(tenant)
    return tenant


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: str,
    data: TenantUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> Tenant:
    """更新租户"""
    check_permission(user, Permission.TENANT_WRITE)

    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None))
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tenant, field, value)

    await db.flush()
    await db.refresh(tenant)
    return tenant


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> None:
    """删除租户（软删除，仅超级管理员）"""
    from datetime import datetime, timezone

    check_permission(user, Permission.TENANT_WRITE)

    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None))
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    tenant.deleted_at = datetime.now(timezone.utc)
    await db.flush()
