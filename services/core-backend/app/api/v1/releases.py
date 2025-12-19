"""
Release API

提供发布包的创建、激活、回滚等操作
"""

import structlog
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import AdminOnly, ViewerOrAbove
from app.core.scope import RequireSiteScope, ScopeContext, verify_tenant_site_access
from app.core.audit import log_audit, AuditAction, TargetType
from app.core.release_service import ReleaseService, ReleasePayload
from app.core.release_validator import validate_release, ValidationResult
from app.database.models.release import ReleaseStatus

logger = structlog.get_logger(__name__)
router = APIRouter()


# ============================================================
# Pydantic Models
# ============================================================

class ReleasePayloadSchema(BaseModel):
    """Release Payload"""
    evidence_gate_policy_version: Optional[str] = None
    feedback_routing_policy_version: Optional[str] = None
    prompts_active_map: Dict[str, str] = Field(default_factory=dict)
    experiment_id: Optional[str] = None
    retrieval_defaults: Dict[str, Any] = Field(default_factory=dict)


class ReleaseCreateRequest(BaseModel):
    """创建 Release 请求"""
    tenant_id: str
    site_id: str
    name: str
    description: Optional[str] = None
    payload: ReleasePayloadSchema


class ReleaseResponse(BaseModel):
    """Release 响应"""
    id: str
    tenant_id: str
    site_id: str
    name: str
    description: Optional[str]
    status: str
    payload: Dict[str, Any]
    created_by: str
    created_at: datetime
    activated_at: Optional[datetime]
    archived_at: Optional[datetime]


class ReleaseHistoryResponse(BaseModel):
    """Release 历史响应"""
    id: str
    release_id: str
    action: str
    previous_release_id: Optional[str]
    operator: str
    created_at: datetime


class ValidationErrorItem(BaseModel):
    """校验错误项"""
    code: str
    detail: str


class ValidationResponse(BaseModel):
    """校验结果响应"""
    ok: bool
    errors: List[ValidationErrorItem] = Field(default_factory=list)


# ============================================================
# API Endpoints
# ============================================================

@router.post("", response_model=ReleaseResponse)
async def create_release(
    request: ReleaseCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AdminOnly = None,
    scope: RequireSiteScope = None,
):
    """创建 draft release（仅管理员）"""
    # Scope 校验
    verify_tenant_site_access(scope, request.tenant_id, request.site_id)
    
    log = logger.bind(
        tenant_id=request.tenant_id,
        site_id=request.site_id,
        name=request.name,
    )
    
    service = ReleaseService(db)
    
    try:
        release = await service.create(
            tenant_id=request.tenant_id,
            site_id=request.site_id,
            name=request.name,
            payload=request.payload.model_dump(),
            created_by=current_user.username,
            description=request.description,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # 记录审计日志
    await log_audit(
        db=db,
        actor=current_user.username,
        action="release.create",
        target_type="release",
        target_id=release.id,
        payload={"name": request.name},
    )
    
    log.info("release_created", release_id=release.id)
    
    return ReleaseResponse(
        id=release.id,
        tenant_id=release.tenant_id,
        site_id=release.site_id,
        name=release.name,
        description=release.description,
        status=release.status.value,
        payload=release.payload,
        created_by=release.created_by,
        created_at=release.created_at,
        activated_at=release.activated_at,
        archived_at=release.archived_at,
    )


@router.get("/active", response_model=Optional[ReleaseResponse])
async def get_active_release(
    db: AsyncSession = Depends(get_db),
    scope: RequireSiteScope = None,
):
    """获取当前 active release
    
    v0.2.4: 从 Header 读取 tenant/site scope
    """
    service = ReleaseService(db)
    release = await service.get_active(scope.tenant_id, scope.site_id)
    
    if not release:
        return None
    
    return ReleaseResponse(
        id=release.id,
        tenant_id=release.tenant_id,
        site_id=release.site_id,
        name=release.name,
        description=release.description,
        status=release.status.value,
        payload=release.payload,
        created_by=release.created_by,
        created_at=release.created_at,
        activated_at=release.activated_at,
        archived_at=release.archived_at,
    )


@router.get("", response_model=List[ReleaseResponse])
async def list_releases(
    status_filter: Optional[str] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    scope: RequireSiteScope = None,
):
    """列出 releases
    
    v0.2.4: 从 Header 读取 tenant/site scope
    """
    service = ReleaseService(db)
    
    release_status = None
    if status_filter:
        try:
            release_status = ReleaseStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}",
            )
    
    releases = await service.list(
        tenant_id=scope.tenant_id,
        site_id=scope.site_id,
        status=release_status,
        skip=skip,
        limit=limit,
    )
    
    return [
        ReleaseResponse(
            id=r.id,
            tenant_id=r.tenant_id,
            site_id=r.site_id,
            name=r.name,
            description=r.description,
            status=r.status.value,
            payload=r.payload,
            created_by=r.created_by,
            created_at=r.created_at,
            activated_at=r.activated_at,
            archived_at=r.archived_at,
        )
        for r in releases
    ]


@router.get("/{release_id}", response_model=ReleaseResponse)
async def get_release(
    release_id: str,
    db: AsyncSession = Depends(get_db),
    scope: RequireSiteScope = None,
):
    """获取 release 详情"""
    service = ReleaseService(db)
    release = await service.get_by_id(release_id)
    
    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Release not found: {release_id}",
        )
    
    # Scope 校验
    verify_tenant_site_access(scope, release.tenant_id, release.site_id)
    
    return ReleaseResponse(
        id=release.id,
        tenant_id=release.tenant_id,
        site_id=release.site_id,
        name=release.name,
        description=release.description,
        status=release.status.value,
        payload=release.payload,
        created_by=release.created_by,
        created_at=release.created_at,
        activated_at=release.activated_at,
        archived_at=release.archived_at,
    )


@router.post("/{release_id}/activate", response_model=ReleaseResponse)
async def activate_release(
    release_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AdminOnly = None,
    scope: RequireSiteScope = None,
):
    """
    激活 release（仅管理员）
    
    激活前会进行完整性校验：
    - evidence_gate_policy_version 必须存在
    - prompts_active_map 中的每个 npc_id@version 必须存在
    - experiment_id 若非空必须存在且状态允许
    - retrieval_defaults 必须合法
    
    校验失败返回 HTTP 400 和结构化错误列表
    """
    log = logger.bind(release_id=release_id)
    
    service = ReleaseService(db)
    
    # 获取 release
    release = await service.get_by_id(release_id)
    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Release not found: {release_id}",
        )
    
    # Scope 校验
    verify_tenant_site_access(scope, release.tenant_id, release.site_id)
    
    # 完整性校验
    validation_result = await validate_release(
        db=db,
        payload=release.payload,
        tenant_id=release.tenant_id,
        site_id=release.site_id,
    )
    
    if not validation_result.ok:
        # 记录失败审计日志
        await log_audit(
            db=db,
            actor=current_user.username,
            action="release.activate_failed",
            target_type="release",
            target_id=release_id,
            payload={
                "name": release.name,
                "errors": [e.to_dict() for e in validation_result.errors],
            },
        )
        log.warning(
            "release_activate_failed",
            error_count=len(validation_result.errors),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=validation_result.to_dict(),
        )
    
    # 校验通过，执行激活
    try:
        release = await service.activate(release_id, operator=current_user.username)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    
    # 记录成功审计日志
    await log_audit(
        db=db,
        actor=current_user.username,
        action="release.activate_success",
        target_type="release",
        target_id=release_id,
        payload={"name": release.name},
    )
    
    log.info("release_activated")
    
    return ReleaseResponse(
        id=release.id,
        tenant_id=release.tenant_id,
        site_id=release.site_id,
        name=release.name,
        description=release.description,
        status=release.status.value,
        payload=release.payload,
        created_by=release.created_by,
        created_at=release.created_at,
        activated_at=release.activated_at,
        archived_at=release.archived_at,
    )


@router.post("/{release_id}/rollback", response_model=ReleaseResponse)
async def rollback_release(
    release_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AdminOnly = None,
    scope: RequireSiteScope = None,
):
    """
    回滚到指定 release（仅管理员）
    
    回滚前会进行完整性校验（与 activate 相同）
    """
    log = logger.bind(release_id=release_id)
    
    service = ReleaseService(db)
    
    # 获取 release
    release = await service.get_by_id(release_id)
    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Release not found: {release_id}",
        )
    
    # Scope 校验
    verify_tenant_site_access(scope, release.tenant_id, release.site_id)
    
    # 完整性校验
    validation_result = await validate_release(
        db=db,
        payload=release.payload,
        tenant_id=release.tenant_id,
        site_id=release.site_id,
    )
    
    if not validation_result.ok:
        # 记录失败审计日志
        await log_audit(
            db=db,
            actor=current_user.username,
            action="release.rollback_failed",
            target_type="release",
            target_id=release_id,
            payload={
                "name": release.name,
                "errors": [e.to_dict() for e in validation_result.errors],
            },
        )
        log.warning(
            "release_rollback_failed",
            error_count=len(validation_result.errors),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=validation_result.to_dict(),
        )
    
    # 校验通过，执行回滚
    try:
        release = await service.rollback(release_id, operator=current_user.username)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    
    # 记录成功审计日志
    await log_audit(
        db=db,
        actor=current_user.username,
        action="release.rollback_success",
        target_type="release",
        target_id=release_id,
        payload={"name": release.name},
    )
    
    log.info("release_rolled_back")
    
    return ReleaseResponse(
        id=release.id,
        tenant_id=release.tenant_id,
        site_id=release.site_id,
        name=release.name,
        description=release.description,
        status=release.status.value,
        payload=release.payload,
        created_by=release.created_by,
        created_at=release.created_at,
        activated_at=release.activated_at,
        archived_at=release.archived_at,
    )


@router.get("/{release_id}/validate", response_model=ValidationResponse)
async def validate_release_endpoint(
    release_id: str,
    db: AsyncSession = Depends(get_db),
    scope: RequireSiteScope = None,
):
    """
    预检 release 完整性
    
    供 Admin Console 在激活前预检，返回校验结果：
    - ok: true 表示校验通过
    - errors: 校验失败的错误列表
    
    不会修改任何数据，仅做校验
    """
    service = ReleaseService(db)
    release = await service.get_by_id(release_id)
    
    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Release not found: {release_id}",
        )
    
    # Scope 校验
    verify_tenant_site_access(scope, release.tenant_id, release.site_id)
    
    validation_result = await validate_release(
        db=db,
        payload=release.payload,
        tenant_id=release.tenant_id,
        site_id=release.site_id,
    )
    
    return ValidationResponse(
        ok=validation_result.ok,
        errors=[
            ValidationErrorItem(code=e.code, detail=e.detail)
            for e in validation_result.errors
        ],
    )


@router.get("/{release_id}/history", response_model=List[ReleaseHistoryResponse])
async def get_release_history(
    release_id: str,
    db: AsyncSession = Depends(get_db),
    scope: RequireSiteScope = None,
):
    """获取 release 相关的历史记录"""
    service = ReleaseService(db)
    release = await service.get_by_id(release_id)
    
    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Release not found: {release_id}",
        )
    
    # Scope 校验
    verify_tenant_site_access(scope, release.tenant_id, release.site_id)
    
    history = await service.get_history(
        tenant_id=release.tenant_id,
        site_id=release.site_id,
        limit=50,
    )
    
    return [
        ReleaseHistoryResponse(
            id=h.id,
            release_id=h.release_id,
            action=h.action,
            previous_release_id=h.previous_release_id,
            operator=h.operator,
            created_at=h.created_at,
        )
        for h in history
    ]
