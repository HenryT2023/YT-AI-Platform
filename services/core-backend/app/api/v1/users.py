"""
用户管理 API

管理系统用户（Admin/Operator）
"""

from typing import Annotated, Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, TenantCtx, get_db
from app.core.permissions import Permission, check_permission
from app.core.security import get_password_hash
from app.domain.user import User, UserRole

router = APIRouter()


class UserCreate(BaseModel):
    """创建用户请求"""

    username: str = Field(..., min_length=3, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    display_name: Optional[str] = None
    password: str = Field(..., min_length=8)
    role: str = UserRole.VIEWER
    permissions: List[str] = Field(default_factory=list)
    allowed_site_ids: Optional[List[str]] = None


class UserUpdate(BaseModel):
    """更新用户请求"""

    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    display_name: Optional[str] = None
    role: Optional[str] = None
    permissions: Optional[List[str]] = None
    allowed_site_ids: Optional[List[str]] = None
    is_active: Optional[bool] = None
    status: Optional[str] = None


class UserPasswordChange(BaseModel):
    """修改密码请求"""

    current_password: str
    new_password: str = Field(..., min_length=8)


class UserResponse(BaseModel):
    """用户响应"""

    id: UUID
    tenant_id: Optional[str]
    username: str
    email: Optional[str]
    phone: Optional[str]
    display_name: Optional[str]
    role: str
    permissions: List[str]
    allowed_site_ids: Optional[List[str]]
    is_active: bool
    status: str

    model_config = {"from_attributes": True}


@router.get("", response_model=List[UserResponse])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    tenant_ctx: TenantCtx,
    role: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> List[User]:
    """获取用户列表"""
    check_permission(user, Permission.USER_READ)

    query = select(User).where(
        User.tenant_id == tenant_ctx.tenant_id,
        User.deleted_at.is_(None),
    )

    if role:
        query = query.where(User.role == role)

    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(user: CurrentUser) -> User:
    """获取当前用户信息"""
    return user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    tenant_ctx: TenantCtx,
) -> User:
    """获取单个用户"""
    check_permission(user, Permission.USER_READ)

    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_ctx.tenant_id,
            User.deleted_at.is_(None),
        )
    )
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return target_user


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    tenant_ctx: TenantCtx,
) -> User:
    """创建用户"""
    check_permission(user, Permission.USER_WRITE)

    # 检查用户名是否已存在
    existing = await db.execute(select(User).where(User.username == data.username))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Username '{data.username}' already exists",
        )

    # 检查邮箱是否已存在
    if data.email:
        existing_email = await db.execute(select(User).where(User.email == data.email))
        if existing_email.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email '{data.email}' already exists",
            )

    # 权限检查：不能创建比自己权限更高的用户
    role_hierarchy = [
        UserRole.VIEWER,
        UserRole.OPERATOR,
        UserRole.SITE_ADMIN,
        UserRole.TENANT_ADMIN,
        UserRole.SUPER_ADMIN,
    ]
    if role_hierarchy.index(data.role) > role_hierarchy.index(user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create user with higher role",
        )

    new_user = User(
        tenant_id=tenant_ctx.tenant_id,
        username=data.username,
        email=data.email,
        phone=data.phone,
        display_name=data.display_name,
        hashed_password=get_password_hash(data.password),
        role=data.role,
        permissions=data.permissions,
        allowed_site_ids=data.allowed_site_ids,
        created_by=user.username,
    )
    db.add(new_user)
    await db.flush()
    await db.refresh(new_user)
    return new_user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    data: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    tenant_ctx: TenantCtx,
) -> User:
    """更新用户"""
    check_permission(user, Permission.USER_WRITE)

    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_ctx.tenant_id,
            User.deleted_at.is_(None),
        )
    )
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(target_user, field, value)

    await db.flush()
    await db.refresh(target_user)
    return target_user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    tenant_ctx: TenantCtx,
) -> None:
    """删除用户（软删除）"""
    from datetime import datetime, timezone

    check_permission(user, Permission.USER_WRITE)

    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_ctx.tenant_id,
            User.deleted_at.is_(None),
        )
    )
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # 不能删除自己
    if target_user.id == user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )

    target_user.deleted_at = datetime.now(timezone.utc)
    await db.flush()
