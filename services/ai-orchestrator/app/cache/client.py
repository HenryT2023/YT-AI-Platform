"""
Redis 缓存客户端

统一的异步 Redis 缓存封装，支持：
- JSON 序列化/反序列化
- TTL 管理
- 缓存命中统计
- 连接池管理
"""

import json
import structlog
from typing import Any, Optional, TypeVar, Generic
from dataclasses import dataclass, field
from datetime import datetime

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

from app.core.config import settings
from app.cache.keys import CacheKey, CACHE_TTL

logger = structlog.get_logger(__name__)

T = TypeVar("T")


@dataclass
class CacheStats:
    """缓存统计"""

    hits: int = 0
    misses: int = 0
    errors: int = 0
    last_reset: datetime = field(default_factory=datetime.utcnow)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def reset(self) -> None:
        self.hits = 0
        self.misses = 0
        self.errors = 0
        self.last_reset = datetime.utcnow()


class RedisCache:
    """
    Redis 缓存客户端

    特性：
    - 异步操作
    - JSON 序列化
    - TTL 管理
    - 缓存命中统计
    - 优雅降级（Redis 不可用时不阻塞主流程）
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        default_ttl: int = 300,
        key_prefix: str = "yantian",
        enabled: bool = True,
    ):
        self._redis_url = redis_url or settings.REDIS_URL
        self._default_ttl = default_ttl
        self._key_prefix = key_prefix
        self._enabled = enabled

        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._connected = False

        # 统计
        self.stats = CacheStats()

    async def connect(self) -> bool:
        """连接 Redis"""
        if not self._enabled:
            logger.info("cache_disabled")
            return False

        try:
            self._pool = ConnectionPool.from_url(
                self._redis_url,
                max_connections=10,
                decode_responses=True,
            )
            self._client = redis.Redis(connection_pool=self._pool)

            # 测试连接
            await self._client.ping()
            self._connected = True

            logger.info("cache_connected", url=self._redis_url[:20] + "...")
            return True

        except Exception as e:
            logger.error("cache_connect_failed", error=str(e))
            self._connected = False
            return False

    async def close(self) -> None:
        """关闭连接"""
        if self._client:
            await self._client.close()
        if self._pool:
            await self._pool.disconnect()
        self._connected = False
        logger.info("cache_closed")

    async def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值

        Args:
            key: 缓存 Key

        Returns:
            缓存值（JSON 反序列化后），不存在返回 None
        """
        if not self._connected or not self._client:
            return None

        try:
            value = await self._client.get(key)
            if value is None:
                self.stats.misses += 1
                return None

            self.stats.hits += 1
            return json.loads(value)

        except json.JSONDecodeError:
            # 非 JSON 值，直接返回
            self.stats.hits += 1
            return value

        except Exception as e:
            logger.warning("cache_get_error", key=key, error=str(e))
            self.stats.errors += 1
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        设置缓存值

        Args:
            key: 缓存 Key
            value: 缓存值（自动 JSON 序列化）
            ttl: 过期时间（秒），默认使用 default_ttl

        Returns:
            是否成功
        """
        if not self._connected or not self._client:
            return False

        try:
            ttl = ttl or self._default_ttl
            serialized = json.dumps(value, ensure_ascii=False, default=str)
            await self._client.setex(key, ttl, serialized)
            return True

        except Exception as e:
            logger.warning("cache_set_error", key=key, error=str(e))
            self.stats.errors += 1
            return False

    async def delete(self, key: str) -> bool:
        """删除缓存"""
        if not self._connected or not self._client:
            return False

        try:
            await self._client.delete(key)
            return True
        except Exception as e:
            logger.warning("cache_delete_error", key=key, error=str(e))
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """删除匹配模式的所有 Key"""
        if not self._connected or not self._client:
            return 0

        try:
            keys = []
            async for key in self._client.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                return await self._client.delete(*keys)
            return 0

        except Exception as e:
            logger.warning("cache_delete_pattern_error", pattern=pattern, error=str(e))
            return 0

    async def get_or_set(
        self,
        key: str,
        factory,
        ttl: Optional[int] = None,
    ) -> Optional[Any]:
        """
        获取缓存，不存在则调用 factory 生成并缓存

        Args:
            key: 缓存 Key
            factory: 异步工厂函数
            ttl: 过期时间

        Returns:
            缓存值或新生成的值
        """
        # 先尝试从缓存获取
        cached = await self.get(key)
        if cached is not None:
            return cached

        # 调用工厂函数生成
        try:
            value = await factory()
            if value is not None:
                await self.set(key, value, ttl)
            return value
        except Exception as e:
            logger.error("cache_factory_error", key=key, error=str(e))
            return None

    async def invalidate_npc(self, tenant_id: str, site_id: str, npc_id: str) -> int:
        """
        失效 NPC 相关缓存

        用于 NPC Profile 或 Prompt 更新时
        """
        pattern = f"{self._key_prefix}:{tenant_id}:{site_id}:*:{npc_id}*"
        return await self.delete_pattern(pattern)

    async def invalidate_site(self, tenant_id: str, site_id: str) -> int:
        """
        失效站点相关缓存

        用于站点配置更新时
        """
        pattern = f"{self._key_prefix}:{tenant_id}:{site_id}:*"
        return await self.delete_pattern(pattern)

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "hits": self.stats.hits,
            "misses": self.stats.misses,
            "errors": self.stats.errors,
            "hit_rate": f"{self.stats.hit_rate:.2%}",
            "connected": self._connected,
            "last_reset": self.stats.last_reset.isoformat(),
        }

    @property
    def is_connected(self) -> bool:
        return self._connected


# 全局缓存实例
_cache_instance: Optional[RedisCache] = None


async def get_cache() -> RedisCache:
    """获取全局缓存实例"""
    global _cache_instance

    if _cache_instance is None:
        _cache_instance = RedisCache(
            redis_url=settings.REDIS_URL,
            default_ttl=300,
            enabled=settings.CACHE_ENABLED if hasattr(settings, 'CACHE_ENABLED') else True,
        )
        await _cache_instance.connect()

    return _cache_instance


async def close_cache() -> None:
    """关闭全局缓存"""
    global _cache_instance

    if _cache_instance:
        await _cache_instance.close()
        _cache_instance = None
