"""
Tenant/Site Scope 校验模块

确保 API 请求只能访问用户被授权的 tenant/site 范围内的资源。

校验规则：
1. 从请求 header 读取 X-Tenant-ID 和 X-Site-ID
2. 从 JWT claims 读取 tenant_id 和 site_ids
3. 校验 header 中的值是否在 JWT 授权范围内
4. super_admin (tenant_id=None) 可访问所有 tenant/site
5. site_ids 为空列表表示可访问该 tenant 下所有 site
"""

from typing import Annotated, List, Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.security import decode_token
from app.database.models.user import UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


class ScopeContext:
    """
    Scope 上下文
    
    包含当前请求的 tenant/site 信息和用户授权范围
    """
    
    def __init__(
        self,
        user_id: str,
        username: str,
        role: str,
        # 请求的 scope（来自 header）
        request_tenant_id: Optional[str],
        request_site_id: Optional[str],
        # 用户授权的 scope（来自 JWT）
        allowed_tenant_id: Optional[str],  # None 表示 super_admin
        allowed_site_ids: List[str],  # 空列表表示可访问所有
    ):
        self.user_id = user_id
        self.username = username
        self.role = role
        self.request_tenant_id = request_tenant_id
        self.request_site_id = request_site_id
        self.allowed_tenant_id = allowed_tenant_id
        self.allowed_site_ids = allowed_site_ids
    
    @property
    def is_super_admin(self) -> bool:
        """是否为超级管理员"""
        return self.role == UserRole.SUPER_ADMIN
    
    @property
    def tenant_id(self) -> Optional[str]:
        """当前请求的 tenant_id"""
        return self.request_tenant_id
    
    @property
    def site_id(self) -> Optional[str]:
        """当前请求的 site_id"""
        return self.request_site_id


async def get_scope_context(
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
    x_tenant_id: Annotated[Optional[str], Header(alias="X-Tenant-ID")] = None,
    x_site_id: Annotated[Optional[str], Header(alias="X-Site-ID")] = None,
) -> ScopeContext:
    """
    获取 Scope 上下文
    
    从 JWT 和 header 中提取 scope 信息，并进行校验
    """
    # 1. 验证 token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供访问令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="访问令牌无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 2. 提取 JWT claims
    user_id = payload.get("sub")
    username = payload.get("username", "")
    role = payload.get("role", "")
    allowed_tenant_id = payload.get("tenant_id")  # None for super_admin
    allowed_site_ids = payload.get("site_ids", [])
    
    # 3. 校验 tenant scope
    if allowed_tenant_id is not None:
        # 非 super_admin，必须校验 tenant
        if x_tenant_id and x_tenant_id != allowed_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "无权访问该租户",
                    "error": "tenant_scope_mismatch",
                    "requested_tenant": x_tenant_id,
                    "allowed_tenant": allowed_tenant_id,
                },
            )
        # 如果 header 没有提供 tenant_id，使用 JWT 中的
        if not x_tenant_id:
            x_tenant_id = allowed_tenant_id
    
    # 4. 校验 site scope
    if allowed_site_ids and len(allowed_site_ids) > 0:
        # 有 site 限制
        if x_site_id and x_site_id not in allowed_site_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "无权访问该站点",
                    "error": "site_scope_mismatch",
                    "requested_site": x_site_id,
                    "allowed_sites": allowed_site_ids,
                },
            )
    
    return ScopeContext(
        user_id=user_id,
        username=username,
        role=role,
        request_tenant_id=x_tenant_id,
        request_site_id=x_site_id,
        allowed_tenant_id=allowed_tenant_id,
        allowed_site_ids=allowed_site_ids,
    )


def require_scope(
    require_tenant: bool = True,
    require_site: bool = False,
):
    """
    Scope 校验依赖工厂
    
    Args:
        require_tenant: 是否要求提供 X-Tenant-ID header
        require_site: 是否要求提供 X-Site-ID header
    
    Usage:
        @router.get("/releases")
        async def list_releases(
            scope: ScopeContext = Depends(require_scope(require_tenant=True))
        ):
            # scope.tenant_id 已校验
            pass
    """
    async def dependency(
        scope: Annotated[ScopeContext, Depends(get_scope_context)],
    ) -> ScopeContext:
        # 检查是否提供了必需的 header
        if require_tenant and not scope.tenant_id and not scope.is_super_admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "缺少 X-Tenant-ID header",
                    "error": "missing_tenant_id",
                },
            )
        
        if require_site and not scope.site_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "缺少 X-Site-ID header",
                    "error": "missing_site_id",
                },
            )
        
        return scope
    
    return dependency


# 常用依赖快捷方式
RequireTenantScope = Annotated[ScopeContext, Depends(require_scope(require_tenant=True, require_site=False))]
RequireSiteScope = Annotated[ScopeContext, Depends(require_scope(require_tenant=True, require_site=True))]
OptionalScope = Annotated[ScopeContext, Depends(get_scope_context)]


def verify_tenant_site_access(
    scope: ScopeContext,
    tenant_id: str,
    site_id: Optional[str] = None,
) -> None:
    """
    验证用户是否有权访问指定的 tenant/site
    
    如果无权访问，抛出 403 异常
    
    Args:
        scope: Scope 上下文
        tenant_id: 要访问的 tenant_id
        site_id: 要访问的 site_id（可选）
    """
    # super_admin 可访问所有
    if scope.is_super_admin:
        return
    
    # 校验 tenant
    if scope.allowed_tenant_id and tenant_id != scope.allowed_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "无权访问该租户的资源",
                "error": "tenant_scope_mismatch",
                "requested_tenant": tenant_id,
                "allowed_tenant": scope.allowed_tenant_id,
            },
        )
    
    # 校验 site（如果提供了 site_id 且用户有 site 限制）
    if site_id and scope.allowed_site_ids and len(scope.allowed_site_ids) > 0:
        if site_id not in scope.allowed_site_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "无权访问该站点的资源",
                    "error": "site_scope_mismatch",
                    "requested_site": site_id,
                    "allowed_sites": scope.allowed_site_ids,
                },
            )
