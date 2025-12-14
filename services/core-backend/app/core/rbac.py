"""
RBAC 权限控制模块

提供基于角色的访问控制依赖

角色层级（从高到低）：
- super_admin: 超级管理员，全部权限
- tenant_admin: 租户管理员
- site_admin: 站点管理员
- operator: 运营人员，可执行大部分操作
- viewer: 只读用户，仅查看权限
- visitor: 游客，不允许登录后台
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

# 允许登录后台的角色
ALLOWED_LOGIN_ROLES = [
    UserRole.SUPER_ADMIN,
    UserRole.TENANT_ADMIN,
    UserRole.SITE_ADMIN,
    UserRole.OPERATOR,
    UserRole.VIEWER,
]

# 管理员角色（可执行高权限操作）
ADMIN_ROLES = [
    UserRole.SUPER_ADMIN,
    UserRole.TENANT_ADMIN,
    UserRole.SITE_ADMIN,
]

# 运营角色（可执行一般操作）
OPERATOR_ROLES = ADMIN_ROLES + [UserRole.OPERATOR]

# 只读角色（仅查看）
VIEWER_ROLES = OPERATOR_ROLES + [UserRole.VIEWER]


async def get_current_user_from_jwt(
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    从 JWT token 获取当前用户
    
    支持两种认证方式：
    1. Authorization: Bearer <token> (JWT)
    2. X-Internal-API-Key (服务间通信)
    
    返回 User 对象，包含 role 等信息
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
                
                if not user:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="用户不存在或已被删除",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                
                if not user.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="账户已被禁用，请联系管理员",
                    )
                
                if user.role not in ALLOWED_LOGIN_ROLES:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"角色 {user.role} 无权访问管理后台",
                    )
                
                return user
        
        # Token 无效
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的访问令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 尝试从 X-Internal-API-Key 获取（服务间通信）
    api_key = request.headers.get("X-Internal-API-Key")
    expected_key = getattr(settings, "INTERNAL_API_KEY", None)
    
    if api_key and expected_key and api_key == expected_key:
        # 内部 API 调用，创建一个虚拟的 admin 用户
        operator = request.headers.get("X-Operator", "internal")
        
        class InternalUser:
            """内部服务调用的虚拟用户"""
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
        detail="未登录或登录已过期，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )


# 保持向后兼容的别名
get_current_admin_user = get_current_user_from_jwt


def require_roles(allowed_roles: List[str]):
    """
    角色权限检查依赖工厂
    
    用法：
        @router.post("/create")
        async def create_something(
            user: Annotated[User, Depends(require_roles(["super_admin", "tenant_admin"]))],
        ):
            ...
    
    Args:
        allowed_roles: 允许访问的角色列表
    
    Returns:
        依赖函数，返回当前用户（如果有权限）
    
    Raises:
        HTTPException 403: 如果用户角色不在允许列表中
    """
    # 将角色名转换为字符串以便比较
    role_names = [r if isinstance(r, str) else r for r in allowed_roles]
    
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user_from_jwt)],
    ) -> User:
        user_role = current_user.role
        
        if user_role not in role_names:
            # 构建可读的角色名称
            readable_roles = ", ".join(role_names)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足：当前角色 [{user_role}] 无权执行此操作，需要角色: [{readable_roles}]",
            )
        return current_user
    
    return role_checker


# ============================================================
# 预定义的角色检查依赖
# ============================================================

def _require_admin():
    """仅管理员可访问"""
    return require_roles(ADMIN_ROLES)

def _require_operator():
    """运营人员及以上可访问"""
    return require_roles(OPERATOR_ROLES)

def _require_viewer():
    """只读用户及以上可访问"""
    return require_roles(VIEWER_ROLES)


# Depends 实例
RequireAdmin = Depends(_require_admin())
RequireOperator = Depends(_require_operator())
RequireViewer = Depends(_require_viewer())


# ============================================================
# 类型别名（用于路由参数类型注解）
# ============================================================

# 任何已登录用户
CurrentUser = Annotated[User, Depends(get_current_user_from_jwt)]

# 仅管理员（super_admin, tenant_admin, site_admin）
AdminOnly = Annotated[User, RequireAdmin]

# 运营人员及以上（admin + operator）
OperatorOrAbove = Annotated[User, RequireOperator]

# 只读用户及以上（admin + operator + viewer）
ViewerOrAbove = Annotated[User, RequireViewer]

# 保持向后兼容
CurrentAdminUser = CurrentUser
