"""
向量覆盖率与一致性统计 API

提供向量索引的健康状态检查
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.database.models import Evidence, VectorSyncJob

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


# ============================================================
# Schemas
# ============================================================

class VectorCoverageResponse(BaseModel):
    """向量覆盖率响应"""
    tenant_id: str
    site_id: Optional[str] = None
    total_evidences: int
    vectorized_evidences: int
    coverage_ratio: float
    stale_vectors: int
    never_vectorized: int
    last_sync_at: Optional[str] = None
    last_sync_status: Optional[str] = None
    last_sync_job_id: Optional[str] = None


class StaleEvidenceItem(BaseModel):
    """过期向量条目"""
    id: str
    title: Optional[str]
    updated_at: str
    vector_updated_at: Optional[str]
    reason: str  # stale / never_vectorized


class StaleEvidencesResponse(BaseModel):
    """过期向量列表响应"""
    tenant_id: str
    site_id: Optional[str] = None
    total: int
    stale_count: int
    never_vectorized_count: int
    items: List[StaleEvidenceItem]


class SyncJobResponse(BaseModel):
    """同步任务响应"""
    id: str
    tenant_id: str
    site_id: Optional[str]
    job_type: str
    status: str
    started_at: Optional[str]
    finished_at: Optional[str]
    total_items: int
    success_count: int
    skip_count: int
    failure_count: int
    progress_percent: float
    duration_seconds: Optional[float]


class SyncJobsListResponse(BaseModel):
    """同步任务列表响应"""
    items: List[SyncJobResponse]
    total: int


# ============================================================
# API Endpoints
# ============================================================

@router.get("/vector-coverage", response_model=VectorCoverageResponse)
async def get_vector_coverage(
    tenant_id: str = Query(..., description="租户 ID"),
    site_id: Optional[str] = Query(None, description="站点 ID"),
    session: AsyncSession = Depends(get_session),
) -> VectorCoverageResponse:
    """
    获取向量覆盖率统计

    返回:
    - total_evidences: 总 evidence 数
    - vectorized_evidences: 已向量化数
    - coverage_ratio: 覆盖率
    - stale_vectors: 过期向量数（evidence 更新后未重新向量化）
    - never_vectorized: 从未向量化数
    - last_sync_at: 最近同步时间
    """
    # 1. 总数
    total_stmt = select(func.count(Evidence.id)).where(
        Evidence.tenant_id == tenant_id,
        Evidence.deleted_at.is_(None),
    )
    if site_id:
        total_stmt = total_stmt.where(Evidence.site_id == site_id)

    result = await session.execute(total_stmt)
    total_evidences = result.scalar() or 0

    # 2. 已向量化数（vector_updated_at 不为空）
    vectorized_stmt = select(func.count(Evidence.id)).where(
        Evidence.tenant_id == tenant_id,
        Evidence.deleted_at.is_(None),
        Evidence.vector_updated_at.isnot(None),
    )
    if site_id:
        vectorized_stmt = vectorized_stmt.where(Evidence.site_id == site_id)

    result = await session.execute(vectorized_stmt)
    vectorized_evidences = result.scalar() or 0

    # 3. 过期向量数（updated_at > vector_updated_at）
    stale_stmt = select(func.count(Evidence.id)).where(
        Evidence.tenant_id == tenant_id,
        Evidence.deleted_at.is_(None),
        Evidence.vector_updated_at.isnot(None),
        Evidence.updated_at > Evidence.vector_updated_at,
    )
    if site_id:
        stale_stmt = stale_stmt.where(Evidence.site_id == site_id)

    result = await session.execute(stale_stmt)
    stale_vectors = result.scalar() or 0

    # 4. 从未向量化数
    never_stmt = select(func.count(Evidence.id)).where(
        Evidence.tenant_id == tenant_id,
        Evidence.deleted_at.is_(None),
        Evidence.vector_updated_at.is_(None),
    )
    if site_id:
        never_stmt = never_stmt.where(Evidence.site_id == site_id)

    result = await session.execute(never_stmt)
    never_vectorized = result.scalar() or 0

    # 5. 最近同步任务
    last_sync_stmt = (
        select(VectorSyncJob)
        .where(VectorSyncJob.tenant_id == tenant_id)
        .order_by(VectorSyncJob.created_at.desc())
        .limit(1)
    )
    if site_id:
        last_sync_stmt = last_sync_stmt.where(VectorSyncJob.site_id == site_id)

    result = await session.execute(last_sync_stmt)
    last_sync = result.scalar_one_or_none()

    # 6. 计算覆盖率
    coverage_ratio = vectorized_evidences / total_evidences if total_evidences > 0 else 0.0

    return VectorCoverageResponse(
        tenant_id=tenant_id,
        site_id=site_id,
        total_evidences=total_evidences,
        vectorized_evidences=vectorized_evidences,
        coverage_ratio=round(coverage_ratio, 4),
        stale_vectors=stale_vectors,
        never_vectorized=never_vectorized,
        last_sync_at=last_sync.finished_at.isoformat() if last_sync and last_sync.finished_at else None,
        last_sync_status=last_sync.status if last_sync else None,
        last_sync_job_id=last_sync.id if last_sync else None,
    )


@router.get("/stale-evidences", response_model=StaleEvidencesResponse)
async def get_stale_evidences(
    tenant_id: str = Query(..., description="租户 ID"),
    site_id: Optional[str] = Query(None, description="站点 ID"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量限制"),
    session: AsyncSession = Depends(get_session),
) -> StaleEvidencesResponse:
    """
    获取过期/未向量化的 evidence 列表

    用于排查和修复向量索引问题
    """
    # 1. 查询过期向量
    stale_stmt = (
        select(Evidence)
        .where(
            Evidence.tenant_id == tenant_id,
            Evidence.deleted_at.is_(None),
            Evidence.vector_updated_at.isnot(None),
            Evidence.updated_at > Evidence.vector_updated_at,
        )
        .order_by(Evidence.updated_at.desc())
        .limit(limit // 2)
    )
    if site_id:
        stale_stmt = stale_stmt.where(Evidence.site_id == site_id)

    result = await session.execute(stale_stmt)
    stale_evidences = result.scalars().all()

    # 2. 查询从未向量化
    never_stmt = (
        select(Evidence)
        .where(
            Evidence.tenant_id == tenant_id,
            Evidence.deleted_at.is_(None),
            Evidence.vector_updated_at.is_(None),
        )
        .order_by(Evidence.created_at.desc())
        .limit(limit // 2)
    )
    if site_id:
        never_stmt = never_stmt.where(Evidence.site_id == site_id)

    result = await session.execute(never_stmt)
    never_evidences = result.scalars().all()

    # 3. 构建响应
    items = []
    for e in stale_evidences:
        items.append(StaleEvidenceItem(
            id=e.id,
            title=e.title,
            updated_at=e.updated_at.isoformat(),
            vector_updated_at=e.vector_updated_at.isoformat() if e.vector_updated_at else None,
            reason="stale",
        ))

    for e in never_evidences:
        items.append(StaleEvidenceItem(
            id=e.id,
            title=e.title,
            updated_at=e.updated_at.isoformat(),
            vector_updated_at=None,
            reason="never_vectorized",
        ))

    # 4. 统计
    stale_count = len(stale_evidences)
    never_count = len(never_evidences)

    return StaleEvidencesResponse(
        tenant_id=tenant_id,
        site_id=site_id,
        total=stale_count + never_count,
        stale_count=stale_count,
        never_vectorized_count=never_count,
        items=items,
    )


@router.get("/sync-jobs", response_model=SyncJobsListResponse)
async def list_sync_jobs(
    tenant_id: str = Query(..., description="租户 ID"),
    site_id: Optional[str] = Query(None, description="站点 ID"),
    limit: int = Query(20, ge=1, le=100, description="返回数量限制"),
    session: AsyncSession = Depends(get_session),
) -> SyncJobsListResponse:
    """
    获取同步任务列表
    """
    stmt = (
        select(VectorSyncJob)
        .where(VectorSyncJob.tenant_id == tenant_id)
        .order_by(VectorSyncJob.created_at.desc())
        .limit(limit)
    )
    if site_id:
        stmt = stmt.where(VectorSyncJob.site_id == site_id)

    result = await session.execute(stmt)
    jobs = result.scalars().all()

    # 统计总数
    count_stmt = select(func.count(VectorSyncJob.id)).where(
        VectorSyncJob.tenant_id == tenant_id
    )
    if site_id:
        count_stmt = count_stmt.where(VectorSyncJob.site_id == site_id)

    result = await session.execute(count_stmt)
    total = result.scalar() or 0

    items = []
    for job in jobs:
        items.append(SyncJobResponse(
            id=job.id,
            tenant_id=job.tenant_id,
            site_id=job.site_id,
            job_type=job.job_type,
            status=job.status,
            started_at=job.started_at.isoformat() if job.started_at else None,
            finished_at=job.finished_at.isoformat() if job.finished_at else None,
            total_items=job.total_items,
            success_count=job.success_count,
            skip_count=job.skip_count,
            failure_count=job.failure_count,
            progress_percent=job.progress_percent,
            duration_seconds=job.duration_seconds,
        ))

    return SyncJobsListResponse(items=items, total=total)


@router.get("/sync-jobs/{job_id}", response_model=SyncJobResponse)
async def get_sync_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> SyncJobResponse:
    """
    获取单个同步任务详情
    """
    stmt = select(VectorSyncJob).where(VectorSyncJob.id == job_id)
    result = await session.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Sync job not found")

    return SyncJobResponse(
        id=job.id,
        tenant_id=job.tenant_id,
        site_id=job.site_id,
        job_type=job.job_type,
        status=job.status,
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        total_items=job.total_items,
        success_count=job.success_count,
        skip_count=job.skip_count,
        failure_count=job.failure_count,
        progress_percent=job.progress_percent,
        duration_seconds=job.duration_seconds,
    )
