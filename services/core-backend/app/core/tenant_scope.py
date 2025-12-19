"""
Tenant/Site Scope 依赖模块

v0.2.3: 管理端 API 强制按 tenant/site 过滤

从 HTTP Header 读取：
- X-Tenant-ID: 租户 ID
- X-Site-ID: 站点 ID

若 header 缺失，返回 400 错误
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status


@dataclass
class TenantSiteScope:
    """租户站点上下文"""
    tenant_id: str
    site_id: str


async def get_tenant_site_scope(
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
    x_site_id: Annotated[str | None, Header(alias="X-Site-ID")] = None,
) -> TenantSiteScope:
    """
    从 Header 获取 tenant/site scope
    
    管理端 API 必须提供这两个 Header，否则返回 400
    """
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="缺少必需的 Header: X-Tenant-ID"
        )
    
    if not x_site_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="缺少必需的 Header: X-Site-ID"
        )
    
    return TenantSiteScope(tenant_id=x_tenant_id, site_id=x_site_id)


# 类型别名，用于依赖注入
RequiredScope = Annotated[TenantSiteScope, Depends(get_tenant_site_scope)]
