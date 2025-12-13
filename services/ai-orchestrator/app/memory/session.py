"""
会话记忆管理

使用 Redis 存储短期会话记忆
"""

import json
from typing import List, Optional

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SessionMemory:
    """会话记忆管理器"""

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._client: Optional[redis.Redis] = None

    async def _get_client(self) -> redis.Redis:
        """获取 Redis 客户端"""
        if self._client is None:
            self._client = redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    def _get_key(self, session_id: str) -> str:
        """生成 Redis key"""
        return f"yantian:session:{session_id}:history"

    async def get_history(
        self,
        session_id: str,
        limit: int = 20,
    ) -> List[dict[str, str]]:
        """
        获取会话历史

        Args:
            session_id: 会话 ID
            limit: 返回的最大消息数

        Returns:
            消息列表，每条消息包含 role 和 content
        """
        client = await self._get_client()
        key = self._get_key(session_id)

        try:
            messages = await client.lrange(key, -limit, -1)
            return [json.loads(msg) for msg in messages]
        except Exception as e:
            logger.error("get_history_error", session_id=session_id, error=str(e))
            return []

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> None:
        """
        添加消息到会话历史

        Args:
            session_id: 会话 ID
            role: 角色（user/assistant）
            content: 消息内容
        """
        client = await self._get_client()
        key = self._get_key(session_id)

        message = json.dumps({"role": role, "content": content}, ensure_ascii=False)

        try:
            await client.rpush(key, message)
            await client.expire(key, settings.MEMORY_TTL_SECONDS)
            # 保持历史记录在合理范围内
            await client.ltrim(key, -100, -1)
        except Exception as e:
            logger.error("add_message_error", session_id=session_id, error=str(e))

    async def clear_history(self, session_id: str) -> None:
        """清除会话历史"""
        client = await self._get_client()
        key = self._get_key(session_id)
        await client.delete(key)

    async def close(self) -> None:
        """关闭连接"""
        if self._client:
            await self._client.close()
            self._client = None
