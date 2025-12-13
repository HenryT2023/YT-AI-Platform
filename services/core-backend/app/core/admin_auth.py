"""
Admin 鉴权中间件

提供 X-Internal-API-Key 校验，用于保护高权限操作
"""

from fastapi import Request, HTTPException, status, Depends
from functools import wraps
from typing import Optional

from app.core.config import settings


def get_internal_api_key(request: Request) -> Optional[str]:
    """从请求头获取 Internal API Key"""
    return request.headers.get("X-Internal-API-Key")


def get_operator(request: Request) -> str:
    """从请求头获取操作者标识"""
    return request.headers.get("X-Operator", "unknown")


async def require_internal_api_key(request: Request) -> str:
    """
    依赖注入：要求有效的 Internal API Key
    
    用于保护高权限操作（policy create/rollback, feedback triage/status）
    """
    api_key = get_internal_api_key(request)
    expected_key = getattr(settings, "INTERNAL_API_KEY", None)
    
    # 如果未配置 INTERNAL_API_KEY，则跳过校验（开发模式）
    if not expected_key:
        return "dev_mode"
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Internal-API-Key header",
        )
    
    if api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid X-Internal-API-Key",
        )
    
    return api_key


async def optional_internal_api_key(request: Request) -> Optional[str]:
    """
    依赖注入：可选的 Internal API Key
    
    用于读接口，可配置是否要求鉴权
    """
    api_key = get_internal_api_key(request)
    expected_key = getattr(settings, "INTERNAL_API_KEY", None)
    require_for_read = getattr(settings, "REQUIRE_API_KEY_FOR_READ", False)
    
    # 如果未配置 INTERNAL_API_KEY，则跳过校验
    if not expected_key:
        return None
    
    # 如果配置了要求读接口也需要鉴权
    if require_for_read:
        if not api_key or api_key != expected_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required for read operations",
            )
    
    return api_key


# 类型别名，用于依赖注入
RequireAdminAuth = Depends(require_internal_api_key)
OptionalAdminAuth = Depends(optional_internal_api_key)
