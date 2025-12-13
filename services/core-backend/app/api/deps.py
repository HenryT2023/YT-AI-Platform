"""
API 依赖注入

提供多租户上下文、当前用户等依赖
"""

from dataclasses import dataclass
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_token, oauth2_scheme
from app.database.engine import get_db
from app.database.filters import TenantBoundSession, TenantFilter
from app.database.models import User


@dataclass
class TenantContext:
    """租户上下文"""

    tenant_id: str
    site_id: str


async def get_tenant_context(
    x_tenant_id: Annotated[Optional[str], Header(alias="X-Tenant-ID")] = None,
    x_site_id: Annotated[Optional[str], Header(alias="X-Site-ID")] = None,
) -> TenantContext:
    """
    从请求头获取租户上下文

    如果未提供，使用默认值
    """
    return TenantContext(
        tenant_id=x_tenant_id or settings.DEFAULT_TENANT_ID,
        site_id=x_site_id or settings.DEFAULT_SITE_ID,
    )


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    获取当前用户

    从 JWT token 中解析用户 ID，查询数据库获取用户信息
    """
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.is_active == True,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_optional(
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Optional[User]:
    """
    获取当前用户（可选）

    如果没有 token 或 token 无效，返回 None
    """
    if not token:
        return None

    try:
        return await get_current_user(token, db)
    except HTTPException:
        return None


async def get_tenant_bound_session(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
) -> TenantBoundSession:
    """
    获取租户绑定的会话

    自动为所有查询添加 tenant_id/site_id 过滤
    自动为所有新建对象设置 tenant_id/site_id
    """
    return TenantBoundSession(
        session=db,
        tenant_id=tenant_ctx.tenant_id,
        site_id=tenant_ctx.site_id,
    )


# 类型别名
DB = Annotated[AsyncSession, Depends(get_db)]
TenantCtx = Annotated[TenantContext, Depends(get_tenant_context)]
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentUserOptional = Annotated[Optional[User], Depends(get_current_user_optional)]
TenantSession = Annotated[TenantBoundSession, Depends(get_tenant_bound_session)]
