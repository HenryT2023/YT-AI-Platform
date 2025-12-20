"""
多级缓存服务 (Multi-Level Cache)

L1: 本地内存缓存（TTL: 60s）
L2: Redis 缓存（TTL: 5min）
L3: 数据库查询
"""

import asyncio
import hashlib
import json
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, Union

import redis.asyncio as redis
from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CacheConfig(BaseModel):
    """缓存配置"""
    l1_ttl: int = 60  # 本地缓存 TTL（秒）
    l2_ttl: int = 300  # Redis 缓存 TTL（秒）
    l1_max_size: int = 1000  # 本地缓存最大条目数
    prefix: str = "yantian"  # 缓存 key 前缀


class CacheEntry:
    """缓存条目"""
    def __init__(self, value: Any, expires_at: datetime):
        self.value = value
        self.expires_at = expires_at

    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at


class LocalCache:
    """本地内存缓存（L1）"""

    def __init__(self, max_size: int = 1000, default_ttl: int = 60):
        self._cache: dict[str, CacheEntry] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if entry.is_expired():
            del self._cache[key]
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        # 清理过期条目
        if len(self._cache) >= self._max_size:
            self._cleanup()

        expires_at = datetime.utcnow() + timedelta(seconds=ttl or self._default_ttl)
        self._cache[key] = CacheEntry(value, expires_at)

    def delete(self, key: str) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()

    def _cleanup(self) -> None:
        """清理过期条目"""
        now = datetime.utcnow()
        expired_keys = [k for k, v in self._cache.items() if v.expires_at < now]
        for key in expired_keys:
            del self._cache[key]

        # 如果还是太多，删除最旧的
        if len(self._cache) >= self._max_size:
            sorted_keys = sorted(
                self._cache.keys(),
                key=lambda k: self._cache[k].expires_at
            )
            for key in sorted_keys[: len(self._cache) - self._max_size + 100]:
                del self._cache[key]


class MultiLevelCache:
    """多级缓存"""

    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self._l1 = LocalCache(
            max_size=self.config.l1_max_size,
            default_ttl=self.config.l1_ttl,
        )
        self._redis: Optional[redis.Redis] = None

    async def _get_redis(self) -> redis.Redis:
        """获取 Redis 连接"""
        if self._redis is None:
            self._redis = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    def _make_key(self, key: str) -> str:
        """生成完整的缓存 key"""
        return f"{self.config.prefix}:{key}"

    async def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值

        查询顺序: L1 -> L2 -> None
        """
        full_key = self._make_key(key)

        # L1: 本地缓存
        value = self._l1.get(full_key)
        if value is not None:
            logger.debug("cache_hit", level="L1", key=key)
            return value

        # L2: Redis 缓存
        try:
            redis_client = await self._get_redis()
            raw_value = await redis_client.get(full_key)
            if raw_value is not None:
                value = json.loads(raw_value)
                # 回填 L1
                self._l1.set(full_key, value)
                logger.debug("cache_hit", level="L2", key=key)
                return value
        except Exception as e:
            logger.warning("redis_get_error", key=key, error=str(e))

        logger.debug("cache_miss", key=key)
        return None

    async def set(
        self,
        key: str,
        value: Any,
        l1_ttl: Optional[int] = None,
        l2_ttl: Optional[int] = None,
    ) -> None:
        """
        设置缓存值

        同时写入 L1 和 L2
        """
        full_key = self._make_key(key)

        # L1: 本地缓存
        self._l1.set(full_key, value, l1_ttl or self.config.l1_ttl)

        # L2: Redis 缓存
        try:
            redis_client = await self._get_redis()
            await redis_client.setex(
                full_key,
                l2_ttl or self.config.l2_ttl,
                json.dumps(value, ensure_ascii=False, default=str),
            )
        except Exception as e:
            logger.warning("redis_set_error", key=key, error=str(e))

    async def delete(self, key: str) -> None:
        """删除缓存"""
        full_key = self._make_key(key)

        # L1
        self._l1.delete(full_key)

        # L2
        try:
            redis_client = await self._get_redis()
            await redis_client.delete(full_key)
        except Exception as e:
            logger.warning("redis_delete_error", key=key, error=str(e))

    async def delete_pattern(self, pattern: str) -> int:
        """按模式删除缓存"""
        full_pattern = self._make_key(pattern)
        deleted = 0

        try:
            redis_client = await self._get_redis()
            cursor = 0
            while True:
                cursor, keys = await redis_client.scan(cursor, match=full_pattern, count=100)
                if keys:
                    await redis_client.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning("redis_delete_pattern_error", pattern=pattern, error=str(e))

        # 清理本地缓存（简单实现：全部清除）
        self._l1.clear()

        return deleted

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any],
        l1_ttl: Optional[int] = None,
        l2_ttl: Optional[int] = None,
    ) -> Any:
        """
        获取缓存，如果不存在则调用 factory 生成并缓存
        """
        value = await self.get(key)
        if value is not None:
            return value

        # 调用 factory
        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        else:
            value = factory()

        if value is not None:
            await self.set(key, value, l1_ttl, l2_ttl)

        return value

    async def close(self) -> None:
        """关闭连接"""
        if self._redis:
            await self._redis.close()
            self._redis = None


# 全局缓存实例
_cache: Optional[MultiLevelCache] = None


def get_cache() -> MultiLevelCache:
    """获取缓存单例"""
    global _cache
    if _cache is None:
        _cache = MultiLevelCache()
    return _cache


# ============================================================
# 缓存装饰器
# ============================================================

def cached(
    key_prefix: str,
    l1_ttl: int = 60,
    l2_ttl: int = 300,
    key_builder: Optional[Callable[..., str]] = None,
):
    """
    缓存装饰器

    Usage:
        @cached("solar_term:current", l1_ttl=3600, l2_ttl=7200)
        async def get_current_solar_term():
            ...

        @cached("npc:persona", key_builder=lambda npc_id: f"{npc_id}")
        async def get_npc_persona(npc_id: str):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            cache = get_cache()

            # 构建缓存 key
            if key_builder:
                key_suffix = key_builder(*args, **kwargs)
            else:
                # 默认使用参数哈希
                key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
                key_suffix = hashlib.md5(key_data.encode()).hexdigest()[:8]

            cache_key = f"{key_prefix}:{key_suffix}" if key_suffix else key_prefix

            # 尝试从缓存获取
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # 调用原函数
            result = await func(*args, **kwargs)

            # 缓存结果
            if result is not None:
                await cache.set(cache_key, result, l1_ttl, l2_ttl)

            return result

        return wrapper
    return decorator


# ============================================================
# 预定义缓存 Key
# ============================================================

class CacheKeys:
    """缓存 Key 常量"""

    # 节气
    SOLAR_TERM_CURRENT = "solar_term:current"
    SOLAR_TERM_ALL = "solar_term:all"

    # NPC
    @staticmethod
    def npc_persona(npc_id: str) -> str:
        return f"npc:persona:{npc_id}"

    @staticmethod
    def npc_list(tenant_id: str, site_id: str) -> str:
        return f"npc:list:{tenant_id}:{site_id}"

    # 推荐
    @staticmethod
    def recommendations_home(tenant_id: str, site_id: str) -> str:
        return f"recommendations:home:{tenant_id}:{site_id}"

    # 游客上下文
    @staticmethod
    def visitor_context(visitor_id: str) -> str:
        return f"context:{visitor_id}"

    # 站点配置
    @staticmethod
    def site_config(site_id: str) -> str:
        return f"site:config:{site_id}"
