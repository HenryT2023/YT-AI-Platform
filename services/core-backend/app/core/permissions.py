"""
权限检查模块

基于角色的访问控制 (RBAC)
"""

from enum import Enum
from functools import wraps
from typing import Callable, List

from fastapi import HTTPException, status

from app.domain.user import User, UserRole


class Permission(str, Enum):
    """权限枚举"""

    # 租户管理
    TENANT_READ = "tenant:read"
    TENANT_WRITE = "tenant:write"

    # 站点管理
    SITE_READ = "site:read"
    SITE_WRITE = "site:write"

    # 用户管理
    USER_READ = "user:read"
    USER_WRITE = "user:write"

    # NPC 管理
    NPC_READ = "npc:read"
    NPC_WRITE = "npc:write"

    # 知识库管理
    KNOWLEDGE_READ = "knowledge:read"
    KNOWLEDGE_WRITE = "knowledge:write"
    KNOWLEDGE_VERIFY = "knowledge:verify"

    # 研学任务管理
    QUEST_READ = "quest:read"
    QUEST_WRITE = "quest:write"

    # 场景管理
    SCENE_READ = "scene:read"
    SCENE_WRITE = "scene:write"

    # 游客数据
    VISITOR_READ = "visitor:read"
    VISITOR_WRITE = "visitor:write"

    # 审计日志
    AUDIT_READ = "audit:read"

    # MCP 工具
    TOOL_EXECUTE = "tool:execute"
    TOOL_MANAGE = "tool:manage"


# 角色权限映射
ROLE_PERMISSIONS: dict[str, List[Permission]] = {
    UserRole.SUPER_ADMIN: list(Permission),  # 超级管理员拥有所有权限

    UserRole.TENANT_ADMIN: [
        Permission.TENANT_READ,
        Permission.SITE_READ,
        Permission.SITE_WRITE,
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.NPC_READ,
        Permission.NPC_WRITE,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_WRITE,
        Permission.KNOWLEDGE_VERIFY,
        Permission.QUEST_READ,
        Permission.QUEST_WRITE,
        Permission.SCENE_READ,
        Permission.SCENE_WRITE,
        Permission.VISITOR_READ,
        Permission.AUDIT_READ,
        Permission.TOOL_EXECUTE,
        Permission.TOOL_MANAGE,
    ],

    UserRole.SITE_ADMIN: [
        Permission.SITE_READ,
        Permission.NPC_READ,
        Permission.NPC_WRITE,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_WRITE,
        Permission.QUEST_READ,
        Permission.QUEST_WRITE,
        Permission.SCENE_READ,
        Permission.SCENE_WRITE,
        Permission.VISITOR_READ,
        Permission.TOOL_EXECUTE,
    ],

    UserRole.OPERATOR: [
        Permission.SITE_READ,
        Permission.NPC_READ,
        Permission.KNOWLEDGE_READ,
        Permission.QUEST_READ,
        Permission.QUEST_WRITE,
        Permission.SCENE_READ,
        Permission.VISITOR_READ,
        Permission.TOOL_EXECUTE,
    ],

    UserRole.VIEWER: [
        Permission.SITE_READ,
        Permission.NPC_READ,
        Permission.KNOWLEDGE_READ,
        Permission.QUEST_READ,
        Permission.SCENE_READ,
    ],
}


def has_permission(user: User, permission: Permission) -> bool:
    """检查用户是否拥有指定权限"""
    # 超级管理员拥有所有权限
    if user.role == UserRole.SUPER_ADMIN:
        return True

    # 检查角色默认权限
    role_perms = ROLE_PERMISSIONS.get(user.role, [])
    if permission in role_perms:
        return True

    # 检查用户额外权限
    if user.permissions and permission.value in user.permissions:
        return True

    return False


def require_permission(*permissions: Permission):
    """
    权限检查装饰器

    用法:
    @require_permission(Permission.NPC_WRITE)
    async def create_npc(...):
        ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 从 kwargs 中获取 user 或 ctx
            user = kwargs.get("user") or kwargs.get("current_user")
            ctx = kwargs.get("ctx")

            if ctx and hasattr(ctx, "user"):
                user = ctx.user

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not authenticated",
                )

            for perm in permissions:
                if not has_permission(user, perm):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Missing permission: {perm.value}",
                    )

            return await func(*args, **kwargs)

        return wrapper
    return decorator


def check_permission(user: User, permission: Permission) -> None:
    """
    检查权限，无权限则抛出异常

    用于在函数内部手动检查权限
    """
    if not has_permission(user, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing permission: {permission.value}",
        )
