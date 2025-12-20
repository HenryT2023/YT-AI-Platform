"""
API 限流中间件

基于 Redis 的滑动窗口限流
"""

import time
from typing import Optional

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# 限流配置
# ============================================================

RATE_LIMITS = {
    # 默认限流
    "default": {"requests": 100, "window": 60},  # 100 req/min

    # 特定端点限流
    "/api/v1/chat": {"requests": 20, "window": 60},  # 20 req/min
    "/api/v1/auth/login": {"requests": 10, "window": 60},  # 10 req/min
    "/api/v1/auth/register": {"requests": 5, "window": 60},  # 5 req/min
    "/api/v1/search/semantic": {"requests": 30, "window": 60},  # 30 req/min
}

# 白名单路径（不限流）
WHITELIST_PATHS = [
    "/health",
    "/api/health",
    "/metrics",
    "/docs",
    "/openapi.json",
]


class RateLimiter:
    """滑动窗口限流器"""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._redis: Optional[redis.Redis] = None

    async def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def is_allowed(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int, int]:
        """
        检查是否允许请求

        Args:
            key: 限流 key（通常是 IP 或用户 ID）
            max_requests: 窗口内最大请求数
            window_seconds: 窗口大小（秒）

        Returns:
            (是否允许, 剩余请求数, 重置时间戳)
        """
        try:
            redis_client = await self._get_redis()
            now = time.time()
            window_start = now - window_seconds

            # 使用 sorted set 实现滑动窗口
            pipe = redis_client.pipeline()

            # 移除窗口外的请求
            pipe.zremrangebyscore(key, 0, window_start)

            # 获取当前窗口内的请求数
            pipe.zcard(key)

            # 添加当前请求
            pipe.zadd(key, {str(now): now})

            # 设置过期时间
            pipe.expire(key, window_seconds)

            results = await pipe.execute()
            current_count = results[1]

            remaining = max(0, max_requests - current_count - 1)
            reset_time = int(now + window_seconds)

            if current_count >= max_requests:
                return False, 0, reset_time

            return True, remaining, reset_time

        except Exception as e:
            logger.warning("rate_limit_error", error=str(e))
            # 限流器故障时放行
            return True, max_requests, int(time.time() + window_seconds)

    async def close(self):
        if self._redis:
            await self._redis.close()
            self._redis = None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """限流中间件"""

    def __init__(self, app, redis_url: Optional[str] = None):
        super().__init__(app)
        self.limiter = RateLimiter(redis_url or settings.REDIS_URL)

    async def dispatch(self, request: Request, call_next) -> Response:
        # 检查白名单
        path = request.url.path
        if any(path.startswith(p) for p in WHITELIST_PATHS):
            return await call_next(request)

        # 获取客户端标识
        client_id = self._get_client_id(request)

        # 获取限流配置
        rate_config = self._get_rate_config(path)

        # 构建限流 key
        rate_key = f"rate_limit:{client_id}:{self._normalize_path(path)}"

        # 检查限流
        allowed, remaining, reset_time = await self.limiter.is_allowed(
            key=rate_key,
            max_requests=rate_config["requests"],
            window_seconds=rate_config["window"],
        )

        if not allowed:
            logger.warning(
                "rate_limit_exceeded",
                client_id=client_id,
                path=path,
            )
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again later.",
                headers={
                    "X-RateLimit-Limit": str(rate_config["requests"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(reset_time - int(time.time())),
                },
            )

        # 继续处理请求
        response = await call_next(request)

        # 添加限流头
        response.headers["X-RateLimit-Limit"] = str(rate_config["requests"])
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)

        return response

    def _get_client_id(self, request: Request) -> str:
        """获取客户端标识"""
        # 优先使用用户 ID
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            return f"user:{user_id}"

        # 使用 X-Forwarded-For 或客户端 IP
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return f"ip:{forwarded_for.split(',')[0].strip()}"

        client_host = request.client.host if request.client else "unknown"
        return f"ip:{client_host}"

    def _get_rate_config(self, path: str) -> dict:
        """获取路径对应的限流配置"""
        # 精确匹配
        if path in RATE_LIMITS:
            return RATE_LIMITS[path]

        # 前缀匹配
        for prefix, config in RATE_LIMITS.items():
            if prefix != "default" and path.startswith(prefix):
                return config

        return RATE_LIMITS["default"]

    def _normalize_path(self, path: str) -> str:
        """规范化路径用于限流 key"""
        # 移除动态参数
        parts = path.split("/")
        normalized = []
        for part in parts:
            if not part:
                continue
            # UUID 或长 ID
            if len(part) > 20 or (len(part) == 36 and part.count("-") == 4):
                normalized.append("*")
            else:
                normalized.append(part)
        return "/".join(normalized)


# ============================================================
# 装饰器形式的限流
# ============================================================

def rate_limit(requests: int = 10, window: int = 60):
    """
    限流装饰器

    Usage:
        @router.post("/chat")
        @rate_limit(requests=20, window=60)
        async def chat(request: Request):
            ...
    """
    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            limiter = RateLimiter(settings.REDIS_URL)

            client_id = request.headers.get("X-Forwarded-For", request.client.host)
            rate_key = f"rate_limit:{func.__name__}:{client_id}"

            allowed, remaining, reset_time = await limiter.is_allowed(
                key=rate_key,
                max_requests=requests,
                window_seconds=window,
            )

            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests",
                )

            return await func(request, *args, **kwargs)

        return wrapper
    return decorator
