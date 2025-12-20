"""
站点管理 API

提供站点 CRUD、配置、统计等接口
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user, TenantContext, get_tenant_context
from app.database.models import User
from app.services.site_manager import SiteManager
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ============================================================
# Request/Response Models
# ============================================================

class SiteCreateRequest(BaseModel):
    """创建站点请求"""
    site_id: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-z0-9-]+$")
    name: str = Field(..., min_length=1, max_length=100)
    display_name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    config: Optional[dict] = None
    theme: Optional[dict] = None
    features: Optional[dict] = None


class SiteUpdateRequest(BaseModel):
    """更新站点请求"""
    name: Optional[str] = Field(None, max_length=100)
    display_name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    logo_url: Optional[str] = None
    config: Optional[dict] = None
    theme: Optional[dict] = None
    features: Optional[dict] = None
    operating_hours: Optional[dict] = None
    contact_info: Optional[dict] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    address: Optional[str] = None
    timezone: Optional[str] = None
    status: Optional[str] = Field(None, pattern=r"^(active|maintenance|disabled)$")


class SiteConfigUpdateRequest(BaseModel):
    """更新站点配置请求"""
    config: Optional[dict] = None
    theme: Optional[dict] = None
    features: Optional[dict] = None


class SiteInitRequest(BaseModel):
    """站点初始化请求"""
    template: str = Field(default="default", pattern=r"^(default|minimal|full)$")


class SiteResponse(BaseModel):
    """站点响应"""
    id: str
    tenant_id: str
    name: str
    display_name: Optional[str]
    description: Optional[str]
    logo_url: Optional[str]
    config: dict
    theme: dict
    features: dict
    operating_hours: dict
    contact_info: dict
    location_lat: Optional[float]
    location_lng: Optional[float]
    address: Optional[str]
    timezone: str
    status: str
    created_at: Any
    updated_at: Any


class SiteListResponse(BaseModel):
    """站点列表响应"""
    items: list[SiteResponse]
    total: int
    limit: int
    offset: int


# ============================================================
# API Endpoints
# ============================================================

@router.get("", response_model=SiteListResponse)
async def list_sites(
    status: Optional[str] = Query(None, pattern=r"^(active|maintenance|disabled)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出站点"""
    manager = SiteManager(db)
    sites, total = await manager.list_sites(
        tenant_id=tenant_ctx.tenant_id,
        status=status,
        limit=limit,
        offset=offset,
    )

    return SiteListResponse(
        items=[_site_to_response(s) for s in sites],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=SiteResponse)
async def create_site(
    request: SiteCreateRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建站点"""
    manager = SiteManager(db)

    # 检查是否已存在
    existing = await manager.get_site(request.site_id)
    if existing:
        raise HTTPException(status_code=400, detail="Site ID already exists")

    site = await manager.create_site(
        tenant_id=tenant_ctx.tenant_id,
        site_id=request.site_id,
        name=request.name,
        display_name=request.display_name,
        description=request.description,
        config=request.config,
        theme=request.theme,
        features=request.features,
    )

    return _site_to_response(site)


@router.get("/{site_id}", response_model=SiteResponse)
async def get_site(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取站点详情"""
    manager = SiteManager(db)
    site = await manager.get_site(site_id)

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    return _site_to_response(site)


@router.put("/{site_id}", response_model=SiteResponse)
async def update_site(
    site_id: str,
    request: SiteUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新站点"""
    manager = SiteManager(db)
    site = await manager.update_site(
        site_id=site_id,
        **request.model_dump(exclude_unset=True),
    )

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    return _site_to_response(site)


@router.delete("/{site_id}")
async def delete_site(
    site_id: str,
    soft: bool = Query(True, description="软删除"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除站点"""
    manager = SiteManager(db)
    success = await manager.delete_site(site_id, soft=soft)

    if not success:
        raise HTTPException(status_code=404, detail="Site not found")

    return {"success": True, "site_id": site_id}


@router.get("/{site_id}/config")
async def get_site_config(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取站点配置"""
    manager = SiteManager(db)
    config = await manager.get_site_config(site_id)

    if not config:
        raise HTTPException(status_code=404, detail="Site not found")

    return config


@router.put("/{site_id}/config")
async def update_site_config(
    site_id: str,
    request: SiteConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新站点配置"""
    manager = SiteManager(db)
    site = await manager.update_site_config(
        site_id=site_id,
        config=request.config,
        theme=request.theme,
        features=request.features,
    )

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    return {"success": True, "site_id": site_id}


@router.post("/{site_id}/init")
async def init_site(
    site_id: str,
    request: SiteInitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """初始化站点基础数据"""
    manager = SiteManager(db)
    result = await manager.init_site(site_id, template=request.template)

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Init failed"))

    return result


@router.get("/{site_id}/stats")
async def get_site_stats(
    site_id: str,
    period: str = Query("7d", pattern=r"^(1d|7d|30d)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取站点统计"""
    manager = SiteManager(db)
    stats = await manager.get_site_stats(site_id, period=period)

    if not stats:
        raise HTTPException(status_code=404, detail="Site not found")

    return stats


# ============================================================
# Helper Functions
# ============================================================

def _site_to_response(site) -> SiteResponse:
    """转换 Site 模型为响应"""
    return SiteResponse(
        id=site.id,
        tenant_id=site.tenant_id,
        name=site.name,
        display_name=site.display_name,
        description=site.description,
        logo_url=getattr(site, "logo_url", None),
        config=site.config,
        theme=site.theme,
        features=getattr(site, "features", {}),
        operating_hours=getattr(site, "operating_hours", {}),
        contact_info=getattr(site, "contact_info", {}),
        location_lat=site.location_lat,
        location_lng=site.location_lng,
        address=getattr(site, "address", None),
        timezone=site.timezone,
        status=site.status,
        created_at=site.created_at,
        updated_at=site.updated_at,
    )
