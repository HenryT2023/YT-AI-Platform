"""
Redis 客户端模块

提供 Redis 连接和常用操作
"""

import redis.asyncio as redis
from typing import Optional

from app.core.config import settings

# 全局 Redis 客户端
_redis_client: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    """获取 Redis 客户端单例"""
    global _redis_client
    
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    
    return _redis_client


async def close_redis():
    """关闭 Redis 连接"""
    global _redis_client
    
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


class LoginRateLimiter:
    """
    登录失败限流器
    
    使用 Redis 计数实现登录失败锁定：
    - key: login_fail:{username}:{ip}
    - 超过阈值后返回剩余锁定时间
    """
    
    KEY_PREFIX = "login_fail"
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.max_fails = settings.AUTH_MAX_LOGIN_FAILS
        self.lockout_seconds = settings.AUTH_LOCKOUT_MINUTES * 60
    
    def _get_key(self, username: str, ip: str) -> str:
        """生成 Redis key"""
        # 清理 username 中的特殊字符
        safe_username = username.replace(":", "_")
        safe_ip = ip.replace(":", "_") if ip else "unknown"
        return f"{self.KEY_PREFIX}:{safe_username}:{safe_ip}"
    
    async def check_locked(self, username: str, ip: str) -> tuple[bool, int]:
        """
        检查是否被锁定
        
        Returns:
            (is_locked, remaining_seconds)
        """
        key = self._get_key(username, ip)
        
        # 获取当前失败次数
        count = await self.redis.get(key)
        
        if count is None:
            return False, 0
        
        count = int(count)
        
        if count >= self.max_fails:
            # 获取剩余 TTL
            ttl = await self.redis.ttl(key)
            if ttl > 0:
                return True, ttl
        
        return False, 0
    
    async def record_failure(self, username: str, ip: str) -> tuple[int, int]:
        """
        记录登录失败
        
        Returns:
            (current_count, remaining_attempts)
        """
        key = self._get_key(username, ip)
        
        # 增加计数
        count = await self.redis.incr(key)
        
        # 设置过期时间（仅在第一次失败时设置）
        if count == 1:
            await self.redis.expire(key, self.lockout_seconds)
        
        remaining = max(0, self.max_fails - count)
        return count, remaining
    
    async def clear_failures(self, username: str, ip: str):
        """清除登录失败记录（登录成功时调用）"""
        key = self._get_key(username, ip)
        await self.redis.delete(key)
    
    async def get_lockout_info(self, username: str, ip: str) -> dict:
        """获取锁定信息"""
        key = self._get_key(username, ip)
        
        count = await self.redis.get(key)
        ttl = await self.redis.ttl(key)
        
        return {
            "fail_count": int(count) if count else 0,
            "max_fails": self.max_fails,
            "remaining_seconds": max(0, ttl) if ttl and ttl > 0 else 0,
            "is_locked": int(count or 0) >= self.max_fails and ttl > 0,
        }
