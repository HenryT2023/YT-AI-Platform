"""
通用依赖

提供租户/站点上下文、当前用户等依赖注入
"""

from typing import Annotated, Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user, oauth2_scheme
from app.core.config import settings
from app.core.security import decode_token
from app.db import get_db
from app.domain.user import User, UserRole
from app.domain.tenant import Tenant
from app.domain.site import Site


class TenantContext:
    """租户上下文"""

    def __init__(
        self,
        tenant_id: str,
        site_id: str,
        tenant: Optional[Tenant] = None,
        site: Optional[Site] = None,
    ):
        self.tenant_id = tenant_id
        self.site_id = site_id
        self.tenant = tenant
        self.site = site


class RequestContext:
    """请求上下文，包含用户、租户、站点信息"""

    def __init__(
        self,
        user: User,
        tenant_context: TenantContext,
        trace_id: str,
    ):
        self.user = user
        self.tenant_id = tenant_context.tenant_id
        self.site_id = tenant_context.site_id
        self.tenant = tenant_context.tenant
        self.site = tenant_context.site
        self.trace_id = trace_id

    @property
    def is_super_admin(self) -> bool:
        return self.user.role == UserRole.SUPER_ADMIN

    @property
    def is_tenant_admin(self) -> bool:
        return self.user.role in (UserRole.SUPER_ADMIN, UserRole.TENANT_ADMIN)


async def get_current_user_obj(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """获取当前用户对象"""
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
        )

    result = await db.execute(
        select(User).where(User.username == user_id, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


async def get_tenant_context(
    x_tenant_id: Annotated[Optional[str], Header(alias="X-Tenant-ID")] = None,
    x_site_id: Annotated[Optional[str], Header(alias="X-Site-ID")] = None,
    db: AsyncSession = Depends(get_db),
) -> TenantContext:
    """
    从请求头获取租户和站点上下文

    Headers:
    - X-Tenant-ID: 租户 ID
    - X-Site-ID: 站点 ID
    """
    tenant_id = x_tenant_id or settings.DEFAULT_TENANT_ID
    site_id = x_site_id or settings.DEFAULT_SITE_ID

    # 验证租户存在
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.status == "active")
    )
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant '{tenant_id}' not found or inactive",
        )

    # 验证站点存在且属于该租户
    site_result = await db.execute(
        select(Site).where(
            Site.id == site_id,
            Site.tenant_id == tenant_id,
            Site.status == "active",
        )
    )
    site = site_result.scalar_one_or_none()
    if not site:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Site '{site_id}' not found or not belong to tenant '{tenant_id}'",
        )

    return TenantContext(
        tenant_id=tenant_id,
        site_id=site_id,
        tenant=tenant,
        site=site,
    )


async def get_request_context(
    user: Annotated[User, Depends(get_current_user_obj)],
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    x_trace_id: Annotated[Optional[str], Header(alias="X-Trace-ID")] = None,
) -> RequestContext:
    """
    获取完整的请求上下文

    验证用户是否有权访问该租户/站点
    """
    # 验证用户权限
    if not user.can_access_tenant(tenant_ctx.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No permission to access this tenant",
        )

    if not user.can_access_site(tenant_ctx.site_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No permission to access this site",
        )

    # 生成 trace_id
    import uuid
    trace_id = x_trace_id or str(uuid.uuid4())

    return RequestContext(
        user=user,
        tenant_context=tenant_ctx,
        trace_id=trace_id,
    )


# 类型别名，方便使用
CurrentUser = Annotated[User, Depends(get_current_user_obj)]
TenantCtx = Annotated[TenantContext, Depends(get_tenant_context)]
ReqCtx = Annotated[RequestContext, Depends(get_request_context)]
