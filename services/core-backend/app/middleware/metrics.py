"""
Prometheus 指标中间件

采集 HTTP 请求、数据库查询、LLM 调用等核心指标
"""

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

from app.core.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# HTTP 请求指标
# ============================================================

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "Number of HTTP requests in progress",
    ["method", "path"],
)


# ============================================================
# 数据库指标
# ============================================================

DB_QUERY_DURATION_SECONDS = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

DB_CONNECTIONS_ACTIVE = Gauge(
    "db_connections_active",
    "Number of active database connections",
)


# ============================================================
# LLM 调用指标
# ============================================================

LLM_REQUEST_DURATION_SECONDS = Histogram(
    "llm_request_duration_seconds",
    "LLM API request duration in seconds",
    ["provider", "model"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

LLM_TOKEN_USAGE_TOTAL = Counter(
    "llm_token_usage_total",
    "Total LLM tokens used",
    ["provider", "model", "type"],  # type: prompt | completion
)

LLM_REQUESTS_TOTAL = Counter(
    "llm_requests_total",
    "Total LLM API requests",
    ["provider", "model", "status"],  # status: success | error
)


# ============================================================
# 缓存指标
# ============================================================

CACHE_HITS_TOTAL = Counter(
    "cache_hits_total",
    "Total cache hits",
    ["level"],  # L1 | L2
)

CACHE_MISSES_TOTAL = Counter(
    "cache_misses_total",
    "Total cache misses",
)


# ============================================================
# 向量检索指标
# ============================================================

VECTOR_SEARCH_DURATION_SECONDS = Histogram(
    "vector_search_duration_seconds",
    "Vector search duration in seconds",
    ["collection"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

VECTOR_SEARCH_RESULTS = Histogram(
    "vector_search_results",
    "Number of vector search results",
    ["collection"],
    buckets=[0, 1, 2, 5, 10, 20, 50],
)


# ============================================================
# 业务指标
# ============================================================

ACTIVE_CONVERSATIONS = Gauge(
    "active_conversations",
    "Number of active conversations",
    ["tenant_id", "site_id"],
)

QUEST_COMPLETIONS_TOTAL = Counter(
    "quest_completions_total",
    "Total quest completions",
    ["tenant_id", "site_id", "quest_type"],
)

VISITOR_CHECKINS_TOTAL = Counter(
    "visitor_checkins_total",
    "Total visitor check-ins",
    ["tenant_id", "site_id"],
)


# ============================================================
# 中间件
# ============================================================

class MetricsMiddleware(BaseHTTPMiddleware):
    """Prometheus 指标采集中间件"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 跳过 metrics 端点自身
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        path = self._normalize_path(request.url.path)

        # 记录进行中的请求
        HTTP_REQUESTS_IN_PROGRESS.labels(method=method, path=path).inc()

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            status_code = 500
            raise
        finally:
            # 记录请求完成
            duration = time.perf_counter() - start_time

            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                path=path,
                status_code=status_code,
            ).inc()

            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method,
                path=path,
            ).observe(duration)

            HTTP_REQUESTS_IN_PROGRESS.labels(method=method, path=path).dec()

        return response

    def _normalize_path(self, path: str) -> str:
        """
        规范化路径，将动态参数替换为占位符

        例如: /api/v1/npcs/123 -> /api/v1/npcs/{id}
        """
        parts = path.split("/")
        normalized = []

        for part in parts:
            if not part:
                continue
            # UUID 格式
            if len(part) == 36 and part.count("-") == 4:
                normalized.append("{id}")
            # 纯数字
            elif part.isdigit():
                normalized.append("{id}")
            # 短 ID（如 npc_xxx）
            elif "_" in part and len(part) > 20:
                normalized.append("{id}")
            else:
                normalized.append(part)

        return "/" + "/".join(normalized)


# ============================================================
# Metrics 端点
# ============================================================

async def metrics_endpoint(request: Request) -> Response:
    """Prometheus metrics 端点"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# ============================================================
# 辅助函数
# ============================================================

def record_db_query(operation: str, duration: float):
    """记录数据库查询"""
    DB_QUERY_DURATION_SECONDS.labels(operation=operation).observe(duration)


def record_llm_request(
    provider: str,
    model: str,
    duration: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    success: bool = True,
):
    """记录 LLM 请求"""
    LLM_REQUEST_DURATION_SECONDS.labels(provider=provider, model=model).observe(duration)
    LLM_REQUESTS_TOTAL.labels(
        provider=provider,
        model=model,
        status="success" if success else "error",
    ).inc()

    if prompt_tokens > 0:
        LLM_TOKEN_USAGE_TOTAL.labels(
            provider=provider,
            model=model,
            type="prompt",
        ).inc(prompt_tokens)

    if completion_tokens > 0:
        LLM_TOKEN_USAGE_TOTAL.labels(
            provider=provider,
            model=model,
            type="completion",
        ).inc(completion_tokens)


def record_cache_hit(level: str):
    """记录缓存命中"""
    CACHE_HITS_TOTAL.labels(level=level).inc()


def record_cache_miss():
    """记录缓存未命中"""
    CACHE_MISSES_TOTAL.inc()


def record_vector_search(collection: str, duration: float, results_count: int):
    """记录向量检索"""
    VECTOR_SEARCH_DURATION_SECONDS.labels(collection=collection).observe(duration)
    VECTOR_SEARCH_RESULTS.labels(collection=collection).observe(results_count)
