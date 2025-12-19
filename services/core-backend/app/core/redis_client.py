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


class QuestSubmitRateLimiter:
    """
    Quest 提交限流器
    
    使用 Redis 滑动窗口计数实现防刷：
    - key: quest_submit:{tenant}:{site}:{session}:{quest}
    - 每个窗口内最多 N 次提交
    """
    
    KEY_PREFIX = "quest_submit"
    
    def __init__(
        self,
        redis_client: redis.Redis,
        window_seconds: int = 60,
        max_submissions: int = 3,
    ):
        self.redis = redis_client
        self.window_seconds = window_seconds
        self.max_submissions = max_submissions
    
    def _get_key(self, tenant_id: str, site_id: str, session_id: str, quest_id: str) -> str:
        """生成 Redis key"""
        # 清理特殊字符
        safe_session = session_id.replace(":", "_")
        safe_quest = quest_id.replace(":", "_")
        return f"{self.KEY_PREFIX}:{tenant_id}:{site_id}:{safe_session}:{safe_quest}"
    
    async def check_and_increment(
        self,
        tenant_id: str,
        site_id: str,
        session_id: str,
        quest_id: str,
    ) -> tuple[bool, int, int]:
        """
        检查是否允许提交，如果允许则增加计数
        
        Returns:
            (is_allowed, current_count, remaining_seconds)
            - is_allowed: 是否允许提交
            - current_count: 当前窗口内的提交次数
            - remaining_seconds: 窗口剩余秒数（用于 429 响应）
        """
        key = self._get_key(tenant_id, site_id, session_id, quest_id)
        
        # 获取当前计数
        count = await self.redis.get(key)
        current_count = int(count) if count else 0
        
        # 获取 TTL
        ttl = await self.redis.ttl(key)
        remaining_seconds = max(0, ttl) if ttl and ttl > 0 else self.window_seconds
        
        # 检查是否超过限制
        if current_count >= self.max_submissions:
            return False, current_count, remaining_seconds
        
        # 增加计数
        new_count = await self.redis.incr(key)
        
        # 仅在第一次设置过期时间
        if new_count == 1:
            await self.redis.expire(key, self.window_seconds)
        
        return True, new_count, remaining_seconds
    
    async def get_status(
        self,
        tenant_id: str,
        site_id: str,
        session_id: str,
        quest_id: str,
    ) -> dict:
        """获取当前限流状态（用于调试）"""
        key = self._get_key(tenant_id, site_id, session_id, quest_id)
        
        count = await self.redis.get(key)
        ttl = await self.redis.ttl(key)
        
        current_count = int(count) if count else 0
        remaining_seconds = max(0, ttl) if ttl and ttl > 0 else 0
        
        return {
            "key": key,
            "current_count": current_count,
            "max_submissions": self.max_submissions,
            "remaining_attempts": max(0, self.max_submissions - current_count),
            "remaining_seconds": remaining_seconds,
            "is_limited": current_count >= self.max_submissions,
        }
