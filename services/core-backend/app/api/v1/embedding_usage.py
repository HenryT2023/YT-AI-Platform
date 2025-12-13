"""
Embedding 使用统计 API

提供 embedding 调用的成本监控、去重统计和限流治理接口
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import structlog

from fastapi import APIRouter, Depends, Query

logger = structlog.get_logger(__name__)
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.database.models import EmbeddingUsage

router = APIRouter(prefix="/embedding", tags=["embedding"])


# ============================================================
# Response Models
# ============================================================

class ProviderModelStats(BaseModel):
    """按 provider/model 分组的统计"""
    provider: str
    model: str
    calls: int
    success_count: int
    failed_count: int
    rate_limited_count: int
    dedup_hit_count: int
    total_chars: int
    total_tokens: int
    total_cost: float
    avg_latency_ms: float
    p95_latency_ms: Optional[float] = None
    success_rate: float


class UsageSummaryResponse(BaseModel):
    """使用统计汇总响应"""
    time_range: str
    start_time: datetime
    end_time: datetime
    tenant_id: Optional[str] = None
    site_id: Optional[str] = None
    
    # 总计
    total_records: int  # 所有记录数
    total_embedding_calls: int  # 真实 embedding 调用数（不含 dedup_hit）
    total_success: int
    total_failed: int
    total_rate_limited: int
    total_dedup_hit: int
    total_chars: int
    total_tokens_estimate: int
    total_cost_estimate: float
    
    # 成功率指标（区分真实调用和去重）
    api_call_success_rate: float  # 真实 API 调用成功率 = success / (success + failed + rate_limited)
    dedup_hit_rate: float  # 去重命中率 = dedup_hit / total_records
    
    # 延迟指标（仅统计真实调用）
    avg_latency_ms: float
    p95_latency_ms: Optional[float] = None
    
    # 按 provider/model 分组
    by_provider_model: List[ProviderModelStats]


class RecentUsageItem(BaseModel):
    """最近使用记录"""
    id: str
    created_at: datetime
    object_type: str
    object_id: str
    provider: str
    model: str
    status: str
    input_chars: int
    estimated_tokens: int
    cost_estimate: float
    latency_ms: int
    error_type: Optional[str] = None


class RecentUsageResponse(BaseModel):
    """最近使用记录响应"""
    items: List[RecentUsageItem]
    total: int
    page: int
    page_size: int


# ============================================================
# Helper Functions
# ============================================================

def parse_time_range(range_str: str) -> timedelta:
    """解析时间范围字符串"""
    if range_str.endswith("h"):
        return timedelta(hours=int(range_str[:-1]))
    elif range_str.endswith("d"):
        return timedelta(days=int(range_str[:-1]))
    elif range_str.endswith("w"):
        return timedelta(weeks=int(range_str[:-1]))
    elif range_str.endswith("m"):
        return timedelta(days=int(range_str[:-1]) * 30)
    else:
        return timedelta(hours=24)


# ============================================================
# API Endpoints
# ============================================================

@router.get("/usage/summary", response_model=UsageSummaryResponse)
async def get_usage_summary(
    range: str = Query("24h", description="时间范围，如 24h, 7d, 30d"),
    tenant_id: Optional[str] = Query(None, description="租户 ID"),
    site_id: Optional[str] = Query(None, description="站点 ID"),
    db: AsyncSession = Depends(get_db),
) -> UsageSummaryResponse:
    """
    获取 embedding 使用统计汇总
    
    返回指定时间范围内的调用统计，包括：
    - 总记录数、真实 embedding 调用数
    - 成功/失败/限流/去重命中次数
    - 总字符数、估算 token 数、估算成本
    - API 调用成功率（不含 dedup_hit）
    - 去重命中率
    - 平均延迟和 P95 延迟（仅统计真实调用）
    - 按 provider/model 分组的详细统计
    """
    from sqlalchemy import text as sql_text
    
    time_delta = parse_time_range(range)
    end_time = datetime.utcnow()
    start_time = end_time - time_delta
    
    # 构建基础查询条件
    conditions = [EmbeddingUsage.created_at >= start_time]
    if tenant_id:
        conditions.append(EmbeddingUsage.tenant_id == tenant_id)
    if site_id:
        conditions.append(EmbeddingUsage.site_id == site_id)
    
    # 总体统计
    total_stmt = select(
        func.count(EmbeddingUsage.id).label("total_records"),
        func.sum(func.cast(EmbeddingUsage.status == "success", Integer)).label("success_count"),
        func.sum(func.cast(EmbeddingUsage.status == "failed", Integer)).label("failed_count"),
        func.sum(func.cast(EmbeddingUsage.status == "rate_limited", Integer)).label("rate_limited_count"),
        func.sum(func.cast(EmbeddingUsage.status == "dedup_hit", Integer)).label("dedup_hit_count"),
        func.sum(EmbeddingUsage.input_chars).label("total_chars"),
        func.sum(EmbeddingUsage.estimated_tokens).label("total_tokens"),
        func.sum(EmbeddingUsage.cost_estimate).label("total_cost"),
    ).where(and_(*conditions))
    
    result = await db.execute(total_stmt)
    totals = result.one()
    
    total_records = totals.total_records or 0
    success_count = totals.success_count or 0
    failed_count = totals.failed_count or 0
    rate_limited_count = totals.rate_limited_count or 0
    dedup_hit_count = totals.dedup_hit_count or 0
    
    # 真实 embedding 调用数（不含 dedup_hit）
    total_embedding_calls = success_count + failed_count + rate_limited_count
    
    # API 调用成功率（仅计算真实调用）
    api_call_success_rate = round(success_count / total_embedding_calls * 100, 2) if total_embedding_calls > 0 else 0
    
    # 去重命中率
    dedup_hit_rate = round(dedup_hit_count / total_records * 100, 2) if total_records > 0 else 0
    
    # 平均延迟（仅统计真实调用，排除 dedup_hit）
    latency_stmt = select(
        func.avg(EmbeddingUsage.latency_ms).label("avg_latency"),
    ).where(
        and_(*conditions, EmbeddingUsage.status != "dedup_hit")
    )
    latency_result = await db.execute(latency_stmt)
    latency_row = latency_result.one()
    avg_latency_ms = round(latency_row.avg_latency or 0, 2)
    
    # P95 延迟（使用 PostgreSQL percentile_cont）
    p95_latency_ms = None
    try:
        # 构建条件字符串
        where_clauses = ["created_at >= :start_time", "status != 'dedup_hit'"]
        params = {"start_time": start_time}
        if tenant_id:
            where_clauses.append("tenant_id = :tenant_id")
            params["tenant_id"] = tenant_id
        if site_id:
            where_clauses.append("site_id = :site_id")
            params["site_id"] = site_id
        
        where_sql = " AND ".join(where_clauses)
        p95_stmt = sql_text(f"""
            SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95
            FROM embedding_usage
            WHERE {where_sql}
        """)
        p95_result = await db.execute(p95_stmt, params)
        p95_row = p95_result.one()
        if p95_row.p95 is not None:
            p95_latency_ms = round(float(p95_row.p95), 2)
    except Exception as e:
        logger.warning("p95_latency_calculation_failed", error=str(e))
    
    # 按 provider/model 分组统计
    group_stmt = select(
        EmbeddingUsage.provider,
        EmbeddingUsage.model,
        func.count(EmbeddingUsage.id).label("calls"),
        func.sum(func.cast(EmbeddingUsage.status == "success", Integer)).label("success_count"),
        func.sum(func.cast(EmbeddingUsage.status == "failed", Integer)).label("failed_count"),
        func.sum(func.cast(EmbeddingUsage.status == "rate_limited", Integer)).label("rate_limited_count"),
        func.sum(func.cast(EmbeddingUsage.status == "dedup_hit", Integer)).label("dedup_hit_count"),
        func.sum(EmbeddingUsage.input_chars).label("total_chars"),
        func.sum(EmbeddingUsage.estimated_tokens).label("total_tokens"),
        func.sum(EmbeddingUsage.cost_estimate).label("total_cost"),
        func.avg(EmbeddingUsage.latency_ms).label("avg_latency"),
    ).where(
        and_(*conditions)
    ).group_by(
        EmbeddingUsage.provider,
        EmbeddingUsage.model,
    )
    
    group_result = await db.execute(group_stmt)
    groups = group_result.all()
    
    by_provider_model = []
    for g in groups:
        calls = g.calls or 0
        success = g.success_count or 0
        failed = g.failed_count or 0
        rate_limited = g.rate_limited_count or 0
        real_calls = success + failed + rate_limited
        by_provider_model.append(ProviderModelStats(
            provider=g.provider,
            model=g.model,
            calls=calls,
            success_count=success,
            failed_count=failed,
            rate_limited_count=rate_limited,
            dedup_hit_count=g.dedup_hit_count or 0,
            total_chars=g.total_chars or 0,
            total_tokens=g.total_tokens or 0,
            total_cost=round(g.total_cost or 0, 6),
            avg_latency_ms=round(g.avg_latency or 0, 2),
            success_rate=round(success / real_calls * 100, 2) if real_calls > 0 else 0,
        ))
    
    return UsageSummaryResponse(
        time_range=range,
        start_time=start_time,
        end_time=end_time,
        tenant_id=tenant_id,
        site_id=site_id,
        total_records=total_records,
        total_embedding_calls=total_embedding_calls,
        total_success=success_count,
        total_failed=failed_count,
        total_rate_limited=rate_limited_count,
        total_dedup_hit=dedup_hit_count,
        total_chars=totals.total_chars or 0,
        total_tokens_estimate=totals.total_tokens or 0,
        total_cost_estimate=round(totals.total_cost or 0, 6),
        api_call_success_rate=api_call_success_rate,
        dedup_hit_rate=dedup_hit_rate,
        avg_latency_ms=avg_latency_ms,
        p95_latency_ms=p95_latency_ms,
        by_provider_model=by_provider_model,
    )


@router.get("/usage/recent", response_model=RecentUsageResponse)
async def get_recent_usage(
    tenant_id: Optional[str] = Query(None, description="租户 ID"),
    site_id: Optional[str] = Query(None, description="站点 ID"),
    status: Optional[str] = Query(None, description="状态过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db),
) -> RecentUsageResponse:
    """
    获取最近的 embedding 使用记录
    """
    conditions = []
    if tenant_id:
        conditions.append(EmbeddingUsage.tenant_id == tenant_id)
    if site_id:
        conditions.append(EmbeddingUsage.site_id == site_id)
    if status:
        conditions.append(EmbeddingUsage.status == status)
    
    # 总数
    count_stmt = select(func.count(EmbeddingUsage.id))
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0
    
    # 分页查询
    stmt = select(EmbeddingUsage).order_by(EmbeddingUsage.created_at.desc())
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(stmt)
    records = result.scalars().all()
    
    items = [
        RecentUsageItem(
            id=r.id,
            created_at=r.created_at,
            object_type=r.object_type,
            object_id=r.object_id,
            provider=r.provider,
            model=r.model,
            status=r.status,
            input_chars=r.input_chars,
            estimated_tokens=r.estimated_tokens,
            cost_estimate=r.cost_estimate,
            latency_ms=r.latency_ms,
            error_type=r.error_type,
        )
        for r in records
    ]
    
    return RecentUsageResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


# 需要导入 Integer 用于 cast
from sqlalchemy import Integer
