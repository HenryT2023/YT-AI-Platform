"""
RBAC 权限控制模块

提供基于角色的访问控制依赖
"""

from typing import Annotated, List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_token
from app.db import get_db
from app.database.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_admin_user(
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    获取当前管理员用户
    
    支持两种认证方式：
    1. Bearer token (JWT)
    2. X-Internal-API-Key (服务间通信)
    """
    # 尝试从 Bearer token 获取用户
    if token:
        payload = decode_token(token)
        if payload:
            user_id = payload.get("sub")
            if user_id:
                result = await db.execute(
                    select(User).where(
                        User.id == user_id,
                        User.deleted_at.is_(None),
                    )
                )
                user = result.scalar_one_or_none()
                if user and user.is_active and user.role != UserRole.VISITOR:
                    return user
    
    # 尝试从 X-Internal-API-Key 获取（服务间通信）
    api_key = request.headers.get("X-Internal-API-Key")
    expected_key = getattr(settings, "INTERNAL_API_KEY", None)
    
    if api_key and expected_key and api_key == expected_key:
        # 内部 API 调用，创建一个虚拟的 admin 用户
        operator = request.headers.get("X-Operator", "internal")
        # 返回一个模拟的管理员用户对象
        class InternalUser:
            id = "internal"
            username = operator
            display_name = f"Internal: {operator}"
            role = UserRole.SUPER_ADMIN
            is_active = True
            tenant_id = None
            allowed_site_ids = None
        return InternalUser()  # type: ignore
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未登录或登录已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_roles(allowed_roles: List[str]):
    """
    角色权限检查依赖工厂
    
    用法：
        @router.post("/create")
        async def create_something(
            user: Annotated[User, Depends(require_roles(["admin", "operator"]))],
        ):
            ...
    """
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_admin_user)],
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足，需要角色: {', '.join(allowed_roles)}",
            )
        return current_user
    
    return role_checker


# 预定义的角色检查依赖
RequireAdmin = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.TENANT_ADMIN, UserRole.SITE_ADMIN]))
RequireOperator = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.TENANT_ADMIN, UserRole.SITE_ADMIN, UserRole.OPERATOR]))
RequireViewer = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.TENANT_ADMIN, UserRole.SITE_ADMIN, UserRole.OPERATOR, UserRole.VIEWER]))


# 类型别名
CurrentAdminUser = Annotated[User, Depends(get_current_admin_user)]
AdminOnly = Annotated[User, RequireAdmin]
OperatorOrAbove = Annotated[User, RequireOperator]
ViewerOrAbove = Annotated[User, RequireViewer]
