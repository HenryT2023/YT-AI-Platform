"""
可观测性 API

/v1/healthz - 深度健康检查
/v1/metrics/summary - 指标聚合
"""

import time
import structlog
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel, Field

from app.core.config import settings

router = APIRouter()
logger = structlog.get_logger(__name__)


# ==================
# Schema 定义
# ==================

class ComponentHealth(BaseModel):
    """组件健康状态"""

    name: str
    status: str  # healthy, degraded, unhealthy
    latency_ms: Optional[int] = None
    message: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str  # healthy, degraded, unhealthy
    service: str = "ai-orchestrator"
    version: str = "0.2.0"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    components: List[ComponentHealth] = Field(default_factory=list)
    uptime_seconds: Optional[int] = None


class PolicyDistribution(BaseModel):
    """策略模式分布"""

    normal: int = 0
    conservative: int = 0
    refuse: int = 0


class ToolFailure(BaseModel):
    """工具失败统计"""

    tool_name: str
    failure_count: int
    last_error: Optional[str] = None


class FeedbackStats(BaseModel):
    """反馈统计"""

    total: int = 0
    correction_count: int = 0
    correction_rate: float = 0.0
    resolution_rate: float = 0.0
    top_issues: List[Dict[str, Any]] = Field(default_factory=list)


class MetricsSummary(BaseModel):
    """指标摘要"""

    time_range_minutes: int
    total_requests: int = 0
    success_count: int = 0
    error_count: int = 0
    success_rate: float = 0.0
    latency_p50_ms: Optional[int] = None
    latency_p95_ms: Optional[int] = None
    latency_p99_ms: Optional[int] = None
    cache_hit_ratio: float = 0.0
    policy_distribution: PolicyDistribution = Field(default_factory=PolicyDistribution)
    top_tool_failures: List[ToolFailure] = Field(default_factory=list)
    llm_stats: Dict[str, Any] = Field(default_factory=dict)
    feedback_stats: FeedbackStats = Field(default_factory=FeedbackStats)


# ==================
# 全局状态（简化版，生产环境应使用 Prometheus/Redis）
# ==================

_start_time = time.time()
_metrics_store: Dict[str, Any] = {
    "requests": [],
    "cache_hits": 0,
    "cache_misses": 0,
    "tool_failures": {},
    "feedbacks": [],  # 反馈记录
}


def record_request(
    latency_ms: int,
    success: bool,
    policy_mode: str,
    tool_calls: List[Dict[str, Any]] = None,
):
    """记录请求指标（供 AgentRuntime 调用）"""
    _metrics_store["requests"].append({
        "timestamp": datetime.utcnow(),
        "latency_ms": latency_ms,
        "success": success,
        "policy_mode": policy_mode,
    })

    # 只保留最近 1 小时的数据
    cutoff = datetime.utcnow() - timedelta(hours=1)
    _metrics_store["requests"] = [
        r for r in _metrics_store["requests"]
        if r["timestamp"] > cutoff
    ]

    # 记录工具失败
    if tool_calls:
        for tc in tool_calls:
            if tc.get("status") == "error":
                name = tc.get("name", "unknown")
                if name not in _metrics_store["tool_failures"]:
                    _metrics_store["tool_failures"][name] = {"count": 0, "last_error": None}
                _metrics_store["tool_failures"][name]["count"] += 1
                _metrics_store["tool_failures"][name]["last_error"] = tc.get("error")


def record_cache_hit(hit: bool):
    """记录缓存命中"""
    if hit:
        _metrics_store["cache_hits"] += 1
    else:
        _metrics_store["cache_misses"] += 1


def record_feedback(
    feedback_type: str,
    severity: str,
    resolved: bool = False,
):
    """记录反馈指标（供 FeedbackClient 调用）"""
    _metrics_store["feedbacks"].append({
        "timestamp": datetime.utcnow(),
        "type": feedback_type,
        "severity": severity,
        "resolved": resolved,
    })

    # 只保留最近 24 小时的数据
    cutoff = datetime.utcnow() - timedelta(hours=24)
    _metrics_store["feedbacks"] = [
        f for f in _metrics_store["feedbacks"]
        if f["timestamp"] > cutoff
    ]


# ==================
# 健康检查
# ==================

async def _check_redis_health() -> ComponentHealth:
    """检查 Redis 健康状态"""
    start = time.time()
    try:
        import redis.asyncio as redis
        client = redis.from_url(settings.REDIS_URL)
        await client.ping()
        await client.close()
        latency = int((time.time() - start) * 1000)
        return ComponentHealth(
            name="redis",
            status="healthy",
            latency_ms=latency,
        )
    except Exception as e:
        return ComponentHealth(
            name="redis",
            status="unhealthy",
            message=str(e),
        )


async def _check_tool_server_health() -> ComponentHealth:
    """检查 Tool Server (core-backend) 健康状态"""
    start = time.time()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.CORE_BACKEND_URL}/health")
            latency = int((time.time() - start) * 1000)
            if resp.status_code == 200:
                return ComponentHealth(
                    name="tool_server",
                    status="healthy",
                    latency_ms=latency,
                    details=resp.json(),
                )
            else:
                return ComponentHealth(
                    name="tool_server",
                    status="degraded",
                    latency_ms=latency,
                    message=f"HTTP {resp.status_code}",
                )
    except Exception as e:
        return ComponentHealth(
            name="tool_server",
            status="unhealthy",
            message=str(e),
        )


async def _check_llm_provider_health() -> ComponentHealth:
    """检查 LLM Provider 健康状态"""
    start = time.time()
    try:
        from app.providers.llm import get_llm_provider
        provider = get_llm_provider(sandbox_mode=settings.LLM_SANDBOX_MODE)
        is_healthy = await provider.health_check()
        latency = int((time.time() - start) * 1000)

        return ComponentHealth(
            name="llm_provider",
            status="healthy" if is_healthy else "degraded",
            latency_ms=latency,
            details={
                "provider": settings.LLM_PROVIDER,
                "sandbox_mode": settings.LLM_SANDBOX_MODE,
            },
        )
    except Exception as e:
        return ComponentHealth(
            name="llm_provider",
            status="unhealthy",
            message=str(e),
        )


async def _check_session_memory_health() -> ComponentHealth:
    """检查会话记忆健康状态"""
    start = time.time()
    try:
        from app.memory import get_session_memory
        memory = await get_session_memory()
        latency = int((time.time() - start) * 1000)

        return ComponentHealth(
            name="session_memory",
            status="healthy" if memory._connected else "degraded",
            latency_ms=latency,
            details={"enabled": settings.MEMORY_ENABLED},
        )
    except Exception as e:
        return ComponentHealth(
            name="session_memory",
            status="unhealthy",
            message=str(e),
        )


@router.get("/healthz", response_model=HealthResponse)
async def deep_health_check():
    """
    深度健康检查

    检查所有依赖组件：
    - Redis
    - Tool Server (core-backend)
    - LLM Provider
    - Session Memory
    """
    log = logger.bind()
    log.info("deep_health_check_start")

    components = await _gather_health_checks()

    # 计算整体状态
    statuses = [c.status for c in components]
    if all(s == "healthy" for s in statuses):
        overall_status = "healthy"
    elif any(s == "unhealthy" for s in statuses):
        overall_status = "unhealthy"
    else:
        overall_status = "degraded"

    uptime = int(time.time() - _start_time)

    log.info("deep_health_check_complete", status=overall_status)

    return HealthResponse(
        status=overall_status,
        components=components,
        uptime_seconds=uptime,
    )


async def _gather_health_checks() -> List[ComponentHealth]:
    """并行执行所有健康检查"""
    import asyncio

    results = await asyncio.gather(
        _check_redis_health(),
        _check_tool_server_health(),
        _check_llm_provider_health(),
        _check_session_memory_health(),
        return_exceptions=True,
    )

    components = []
    for r in results:
        if isinstance(r, Exception):
            components.append(ComponentHealth(
                name="unknown",
                status="unhealthy",
                message=str(r),
            ))
        else:
            components.append(r)

    return components


# ==================
# 指标聚合
# ==================

@router.get("/metrics/summary", response_model=MetricsSummary)
async def get_metrics_summary(
    minutes: int = Query(default=5, ge=1, le=60, description="时间范围（分钟）"),
):
    """
    获取指标摘要

    聚合返回最近 N 分钟的关键指标：
    - 成功率
    - P95 延迟
    - 缓存命中率
    - 策略模式分布
    - Top 工具失败
    """
    log = logger.bind(minutes=minutes)
    log.info("get_metrics_summary")

    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    recent_requests = [
        r for r in _metrics_store["requests"]
        if r["timestamp"] > cutoff
    ]

    total = len(recent_requests)
    success_count = sum(1 for r in recent_requests if r["success"])
    error_count = total - success_count

    # 计算延迟百分位
    latencies = sorted([r["latency_ms"] for r in recent_requests])
    p50 = _percentile(latencies, 50) if latencies else None
    p95 = _percentile(latencies, 95) if latencies else None
    p99 = _percentile(latencies, 99) if latencies else None

    # 缓存命中率
    cache_total = _metrics_store["cache_hits"] + _metrics_store["cache_misses"]
    cache_hit_ratio = (
        _metrics_store["cache_hits"] / cache_total
        if cache_total > 0 else 0.0
    )

    # 策略模式分布
    policy_dist = PolicyDistribution()
    for r in recent_requests:
        mode = r.get("policy_mode", "normal")
        if mode == "normal":
            policy_dist.normal += 1
        elif mode == "conservative":
            policy_dist.conservative += 1
        elif mode == "refuse":
            policy_dist.refuse += 1

    # Top 工具失败
    tool_failures = [
        ToolFailure(
            tool_name=name,
            failure_count=data["count"],
            last_error=data["last_error"],
        )
        for name, data in _metrics_store["tool_failures"].items()
    ]
    tool_failures.sort(key=lambda x: x.failure_count, reverse=True)

    # 反馈统计
    feedback_stats = _calculate_feedback_stats(minutes)

    return MetricsSummary(
        time_range_minutes=minutes,
        total_requests=total,
        success_count=success_count,
        error_count=error_count,
        success_rate=success_count / total if total > 0 else 0.0,
        latency_p50_ms=p50,
        latency_p95_ms=p95,
        latency_p99_ms=p99,
        cache_hit_ratio=cache_hit_ratio,
        policy_distribution=policy_dist,
        top_tool_failures=tool_failures[:5],
        llm_stats={
            "provider": settings.LLM_PROVIDER,
            "sandbox_mode": settings.LLM_SANDBOX_MODE,
        },
        feedback_stats=feedback_stats,
    )


def _percentile(sorted_list: List[int], percentile: int) -> int:
    """计算百分位数"""
    if not sorted_list:
        return 0
    k = (len(sorted_list) - 1) * percentile / 100
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_list) else f
    return int(sorted_list[f] + (sorted_list[c] - sorted_list[f]) * (k - f))


def _calculate_feedback_stats(minutes: int) -> FeedbackStats:
    """计算反馈统计"""
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    recent_feedbacks = [
        f for f in _metrics_store["feedbacks"]
        if f["timestamp"] > cutoff
    ]

    total = len(recent_feedbacks)
    if total == 0:
        return FeedbackStats()

    # 纠错类型统计
    correction_types = ["correction", "fact_error", "missing_info"]
    correction_count = sum(
        1 for f in recent_feedbacks
        if f["type"] in correction_types
    )

    # 解决率
    resolved_count = sum(1 for f in recent_feedbacks if f["resolved"])

    # 高频问题（按 type + severity 组合）
    issue_counts: Dict[str, int] = {}
    for f in recent_feedbacks:
        key = f"{f['type']}:{f['severity']}"
        issue_counts[key] = issue_counts.get(key, 0) + 1

    top_issues = [
        {"issue": k, "count": v}
        for k, v in sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    ]

    return FeedbackStats(
        total=total,
        correction_count=correction_count,
        correction_rate=correction_count / total if total > 0 else 0.0,
        resolution_rate=resolved_count / total if total > 0 else 0.0,
        top_issues=top_issues,
    )
