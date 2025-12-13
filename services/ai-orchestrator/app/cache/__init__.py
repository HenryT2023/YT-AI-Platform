"""
Cache 模块

统一的 Redis 缓存封装，支持：
- 异步操作
- JSON 序列化
- TTL 管理
- Key 命名规范（含 tenant/site）
- 缓存命中统计
"""

from app.cache.client import (
    RedisCache,
    get_cache,
    close_cache,
)
from app.cache.keys import CacheKey, CacheKeyBuilder

__all__ = [
    "RedisCache",
    "get_cache",
    "close_cache",
    "CacheKey",
    "CacheKeyBuilder",
]
