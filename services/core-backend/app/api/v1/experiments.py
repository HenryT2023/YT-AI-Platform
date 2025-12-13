"""
A/B 实验 API

提供实验管理与分桶接口：
- POST /v1/experiments - 创建实验
- GET /v1/experiments - 列表
- GET /v1/experiments/active - 获取活跃实验
- GET /v1/experiments/assign - 分桶分配
- GET /v1/experiments/{id} - 详情
- PATCH /v1/experiments/{id}/status - 更新状态
"""

import hashlib
import structlog
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.database.models.experiment import (
    Experiment,
    ExperimentAssignment,
    ExperimentStatus,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/experiments", tags=["experiments"])


# ============================================================
# Schemas
# ============================================================

class VariantConfig(BaseModel):
    """Variant 配置"""
    name: str = Field(..., description="Variant 名称")
    weight: int = Field(50, ge=0, le=100, description="流量权重（百分比）")
    strategy_overrides: Dict[str, Any] = Field(
        default_factory=dict,
        description="策略覆写，如 {retrieval_strategy: 'hybrid'}",
    )


class ExperimentCreate(BaseModel):
    """创建实验请求"""
    name: str = Field(..., description="实验名称")
    description: Optional[str] = Field(None, description="实验描述")
    variants: List[VariantConfig] = Field(..., description="Variant 配置列表")
    subject_type: str = Field("session_id", description="分桶主体类型: user_id/session_id")
    target_metrics: List[str] = Field(
        default_factory=lambda: ["citations_rate", "p95_latency_ms"],
        description="目标指标",
    )
    tenant_id: str = Field("yantian", description="租户 ID")
    site_id: str = Field("yantian-main", description="站点 ID")


class ExperimentResponse(BaseModel):
    """实验响应"""
    id: str
    name: str
    description: Optional[str]
    status: str
    config: dict
    tenant_id: str
    site_id: str
    start_at: Optional[datetime]
    end_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExperimentListResponse(BaseModel):
    """实验列表响应"""
    items: List[ExperimentResponse]
    total: int


class AssignmentRequest(BaseModel):
    """分桶请求"""
    experiment_id: str = Field(..., description="实验 ID")
    tenant_id: str = Field("yantian", description="租户 ID")
    site_id: str = Field("yantian-main", description="站点 ID")
    user_id: Optional[str] = Field(None, description="用户 ID")
    session_id: Optional[str] = Field(None, description="会话 ID")


class AssignmentResponse(BaseModel):
    """分桶响应"""
    experiment_id: str
    experiment_name: str
    variant: str
    bucket_hash: int
    strategy_overrides: Dict[str, Any]
    is_new_assignment: bool


class StatusUpdate(BaseModel):
    """状态更新请求"""
    status: str = Field(..., description="目标状态: active/paused/completed")


# ============================================================
# 分桶算法
# ============================================================

def compute_bucket_hash(subject_key: str, experiment_id: str) -> int:
    """
    计算稳定分桶 hash
    
    使用 SHA256 确保分布均匀，取模 100 得到 0-99 的桶号
    """
    hash_input = f"{subject_key}:{experiment_id}"
    hash_bytes = hashlib.sha256(hash_input.encode()).digest()
    # 取前 4 字节作为整数
    hash_int = int.from_bytes(hash_bytes[:4], byteorder='big')
    return hash_int % 100


def assign_variant(bucket_hash: int, variants: List[dict]) -> tuple[str, dict]:
    """
    根据 bucket_hash 分配 variant
    
    按 weight 累加，找到落入的区间
    """
    cumulative = 0
    for variant in variants:
        cumulative += variant.get("weight", 0)
        if bucket_hash < cumulative:
            return variant["name"], variant.get("strategy_overrides", {})
    
    # 兜底：返回最后一个
    if variants:
        last = variants[-1]
        return last["name"], last.get("strategy_overrides", {})
    
    return "control", {}


# ============================================================
# Endpoints
# ============================================================

@router.post("", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)
async def create_experiment(
    request: ExperimentCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    创建 A/B 实验
    
    配置 variants 和流量比例
    """
    log = logger.bind(name=request.name)
    
    # 验证 weights 总和
    total_weight = sum(v.weight for v in request.variants)
    if total_weight != 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Variant weights must sum to 100, got {total_weight}",
        )
    
    config = {
        "variants": [v.model_dump() for v in request.variants],
        "subject_type": request.subject_type,
        "target_metrics": request.target_metrics,
    }
    
    experiment = Experiment(
        name=request.name,
        description=request.description,
        status=ExperimentStatus.DRAFT.value,
        config=config,
        tenant_id=request.tenant_id,
        site_id=request.site_id,
    )
    
    db.add(experiment)
    await db.commit()
    await db.refresh(experiment)
    
    log.info("experiment_created", experiment_id=experiment.id)
    
    return ExperimentResponse.model_validate(experiment)


@router.get("", response_model=ExperimentListResponse)
async def list_experiments(
    tenant_id: str = Query("yantian", description="租户 ID"),
    site_id: Optional[str] = Query(None, description="站点 ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="状态过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取实验列表"""
    conditions = [Experiment.tenant_id == tenant_id]
    if site_id:
        conditions.append(Experiment.site_id == site_id)
    if status_filter:
        conditions.append(Experiment.status == status_filter)
    
    # 总数
    count_query = select(func.count(Experiment.id)).where(and_(*conditions))
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 列表
    query = (
        select(Experiment)
        .where(and_(*conditions))
        .order_by(Experiment.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    items = result.scalars().all()
    
    return ExperimentListResponse(
        items=[ExperimentResponse.model_validate(item) for item in items],
        total=total,
    )


@router.get("/active", response_model=List[ExperimentResponse])
async def get_active_experiments(
    tenant_id: str = Query("yantian", description="租户 ID"),
    site_id: str = Query("yantian-main", description="站点 ID"),
    db: AsyncSession = Depends(get_db),
):
    """获取活跃实验列表"""
    query = select(Experiment).where(
        and_(
            Experiment.tenant_id == tenant_id,
            Experiment.site_id == site_id,
            Experiment.status == ExperimentStatus.ACTIVE.value,
        )
    )
    result = await db.execute(query)
    items = result.scalars().all()
    
    return [ExperimentResponse.model_validate(item) for item in items]


@router.get("/assign", response_model=AssignmentResponse)
async def assign_to_experiment(
    experiment_id: str = Query(..., description="实验 ID"),
    tenant_id: str = Query("yantian", description="租户 ID"),
    site_id: str = Query("yantian-main", description="站点 ID"),
    user_id: Optional[str] = Query(None, description="用户 ID"),
    session_id: Optional[str] = Query(None, description="会话 ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    获取实验分桶分配
    
    稳定分桶：同一 subject_key 在同一实验中永远返回相同 variant
    """
    log = logger.bind(experiment_id=experiment_id)
    
    # 获取实验
    exp_query = select(Experiment).where(Experiment.id == experiment_id)
    exp_result = await db.execute(exp_query)
    experiment = exp_result.scalar_one_or_none()
    
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment not found: {experiment_id}",
        )
    
    if experiment.status != ExperimentStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Experiment is not active: {experiment.status}",
        )
    
    # 确定 subject_key
    subject_type = experiment.get_subject_type()
    if subject_type == "user_id":
        subject_key = user_id
    else:
        subject_key = session_id
    
    if not subject_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required field: {subject_type}",
        )
    
    # 检查是否已有分配
    existing_query = select(ExperimentAssignment).where(
        and_(
            ExperimentAssignment.experiment_id == experiment_id,
            ExperimentAssignment.subject_key == subject_key,
        )
    )
    existing_result = await db.execute(existing_query)
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        # 返回已有分配
        return AssignmentResponse(
            experiment_id=experiment_id,
            experiment_name=experiment.name,
            variant=existing.variant,
            bucket_hash=existing.bucket_hash,
            strategy_overrides=existing.strategy_overrides,
            is_new_assignment=False,
        )
    
    # 计算分桶
    bucket_hash = compute_bucket_hash(subject_key, experiment_id)
    variants = experiment.get_variants()
    variant_name, strategy_overrides = assign_variant(bucket_hash, variants)
    
    # 记录分配
    assignment = ExperimentAssignment(
        experiment_id=experiment_id,
        tenant_id=tenant_id,
        site_id=site_id,
        subject_type=subject_type,
        subject_key=subject_key,
        variant=variant_name,
        bucket_hash=bucket_hash,
        strategy_overrides=strategy_overrides,
    )
    
    db.add(assignment)
    await db.commit()
    
    log.info(
        "experiment_assigned",
        subject_key=subject_key,
        variant=variant_name,
        bucket_hash=bucket_hash,
    )
    
    return AssignmentResponse(
        experiment_id=experiment_id,
        experiment_name=experiment.name,
        variant=variant_name,
        bucket_hash=bucket_hash,
        strategy_overrides=strategy_overrides,
        is_new_assignment=True,
    )


@router.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(
    experiment_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取实验详情"""
    query = select(Experiment).where(Experiment.id == experiment_id)
    result = await db.execute(query)
    experiment = result.scalar_one_or_none()
    
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment not found: {experiment_id}",
        )
    
    return ExperimentResponse.model_validate(experiment)


# ============================================================
# A/B Summary API
# ============================================================

class VariantMetrics(BaseModel):
    """Variant 指标"""
    variant: str
    total_chats: int
    citations_rate: float  # 事实类问题 citations>=1 的比例
    conservative_rate: float  # 保守回答比例
    refuse_rate: float  # 拒绝回答比例
    correction_rate: float  # 反馈纠错比例
    avg_latency_ms: float
    p95_latency_ms: Optional[float]
    embedding_cost_estimate: float


class ABSummaryResponse(BaseModel):
    """A/B 实验指标汇总"""
    experiment_id: str
    experiment_name: str
    time_range: str
    start_time: datetime
    end_time: datetime
    total_traces: int
    variants: List[VariantMetrics]


@router.get("/ab-summary", response_model=ABSummaryResponse)
async def get_ab_summary(
    experiment_id: str = Query(..., description="实验 ID"),
    range: str = Query("24h", description="时间范围，如 24h, 7d"),
    tenant_id: str = Query("yantian", description="租户 ID"),
    site_id: Optional[str] = Query(None, description="站点 ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    获取 A/B 实验指标汇总
    
    按 variant 分组输出关键指标
    """
    from sqlalchemy import text as sql_text
    from app.database.models.trace_ledger import TraceLedger
    from app.database.models.user_feedback import UserFeedback
    from app.database.models.embedding_usage import EmbeddingUsage
    
    # 解析时间范围
    time_delta = parse_time_range(range)
    end_time = datetime.utcnow()
    start_time = end_time - time_delta
    
    # 获取实验信息
    exp_query = select(Experiment).where(Experiment.id == experiment_id)
    exp_result = await db.execute(exp_query)
    experiment = exp_result.scalar_one_or_none()
    
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment not found: {experiment_id}",
        )
    
    # 构建基础条件
    base_conditions = [
        TraceLedger.experiment_id == experiment_id,
        TraceLedger.created_at >= start_time,
        TraceLedger.tenant_id == tenant_id,
    ]
    if site_id:
        base_conditions.append(TraceLedger.site_id == site_id)
    
    # 总 trace 数
    total_query = select(func.count(TraceLedger.id)).where(and_(*base_conditions))
    total_result = await db.execute(total_query)
    total_traces = total_result.scalar() or 0
    
    # 按 variant 分组统计
    variant_stats_query = select(
        TraceLedger.experiment_variant,
        func.count(TraceLedger.id).label("total_chats"),
        func.avg(TraceLedger.latency_ms).label("avg_latency"),
        func.sum(func.cast(TraceLedger.policy_mode == "fallback", Integer)).label("conservative_count"),
        func.sum(func.cast(TraceLedger.guardrail_passed == False, Integer)).label("refuse_count"),
    ).where(
        and_(*base_conditions)
    ).group_by(TraceLedger.experiment_variant)
    
    variant_result = await db.execute(variant_stats_query)
    variant_rows = variant_result.all()
    
    variants_metrics = []
    for row in variant_rows:
        variant_name = row.experiment_variant or "unknown"
        total_chats = row.total_chats or 0
        conservative_count = row.conservative_count or 0
        refuse_count = row.refuse_count or 0
        
        # citations_rate: 有证据的比例
        citations_query = select(func.count(TraceLedger.id)).where(
            and_(
                *base_conditions,
                TraceLedger.experiment_variant == variant_name,
                func.array_length(TraceLedger.evidence_ids, 1) >= 1,
            )
        )
        citations_result = await db.execute(citations_query)
        citations_count = citations_result.scalar() or 0
        citations_rate = round(citations_count / total_chats * 100, 2) if total_chats > 0 else 0
        
        # correction_rate: 按 trace_id 关联 feedback
        correction_query = select(func.count(UserFeedback.id)).where(
            and_(
                UserFeedback.trace_id.in_(
                    select(TraceLedger.trace_id).where(
                        and_(
                            *base_conditions,
                            TraceLedger.experiment_variant == variant_name,
                        )
                    )
                ),
                UserFeedback.feedback_type.in_(["correction", "fact_error", "missing_info"]),
            )
        )
        correction_result = await db.execute(correction_query)
        correction_count = correction_result.scalar() or 0
        correction_rate = round(correction_count / total_chats * 100, 2) if total_chats > 0 else 0
        
        # p95_latency
        p95_latency_ms = None
        try:
            p95_query = sql_text("""
                SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95
                FROM trace_ledger
                WHERE experiment_id = :exp_id
                  AND experiment_variant = :variant
                  AND created_at >= :start_time
                  AND tenant_id = :tenant_id
            """)
            p95_result = await db.execute(p95_query, {
                "exp_id": experiment_id,
                "variant": variant_name,
                "start_time": start_time,
                "tenant_id": tenant_id,
            })
            p95_row = p95_result.one()
            if p95_row.p95 is not None:
                p95_latency_ms = round(float(p95_row.p95), 2)
        except Exception:
            pass
        
        # embedding_cost_estimate: 聚合 embedding_usage
        # 通过 trace_id 关联
        cost_query = select(func.sum(EmbeddingUsage.cost_estimate)).where(
            and_(
                EmbeddingUsage.trace_id.in_(
                    select(TraceLedger.trace_id).where(
                        and_(
                            *base_conditions,
                            TraceLedger.experiment_variant == variant_name,
                        )
                    )
                ),
            )
        )
        cost_result = await db.execute(cost_query)
        embedding_cost = cost_result.scalar() or 0
        
        variants_metrics.append(VariantMetrics(
            variant=variant_name,
            total_chats=total_chats,
            citations_rate=citations_rate,
            conservative_rate=round(conservative_count / total_chats * 100, 2) if total_chats > 0 else 0,
            refuse_rate=round(refuse_count / total_chats * 100, 2) if total_chats > 0 else 0,
            correction_rate=correction_rate,
            avg_latency_ms=round(row.avg_latency or 0, 2),
            p95_latency_ms=p95_latency_ms,
            embedding_cost_estimate=round(embedding_cost, 6),
        ))
    
    return ABSummaryResponse(
        experiment_id=experiment_id,
        experiment_name=experiment.name,
        time_range=range,
        start_time=start_time,
        end_time=end_time,
        total_traces=total_traces,
        variants=variants_metrics,
    )


def parse_time_range(range_str: str) -> timedelta:
    """解析时间范围字符串"""
    from datetime import timedelta
    
    if range_str.endswith("h"):
        hours = int(range_str[:-1])
        return timedelta(hours=hours)
    elif range_str.endswith("d"):
        days = int(range_str[:-1])
        return timedelta(days=days)
    else:
        return timedelta(hours=24)


@router.patch("/{experiment_id}/status", response_model=ExperimentResponse)
async def update_experiment_status(
    experiment_id: str,
    request: StatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新实验状态"""
    log = logger.bind(experiment_id=experiment_id, target_status=request.status)
    
    query = select(Experiment).where(Experiment.id == experiment_id)
    result = await db.execute(query)
    experiment = result.scalar_one_or_none()
    
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment not found: {experiment_id}",
        )
    
    valid_statuses = ["active", "paused", "completed"]
    if request.status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status: {request.status}. Valid: {valid_statuses}",
        )
    
    experiment.status = request.status
    if request.status == "active" and not experiment.start_at:
        experiment.start_at = datetime.utcnow()
    elif request.status == "completed" and not experiment.end_at:
        experiment.end_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(experiment)
    
    log.info("experiment_status_updated")
    
    return ExperimentResponse.model_validate(experiment)
