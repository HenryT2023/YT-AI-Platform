"""
Redis 会话记忆

多轮对话记忆管理：
- 按 tenant_id/site_id/session_id/npc_id 分区（NPC 隔离）
- 短记忆：保存最近 N 条消息（默认 10 条）
- 偏好记忆：存储用户偏好（verbosity、tone、interest_tags）
- 支持字符上限裁剪
- 会话 TTL 自动过期

重要约束：
- 记忆仅作为"上下文与偏好"，不作为史实来源
- 史实必须来自 evidence
- 偏好记忆不得存储任何史实内容
"""

import json
import uuid
import structlog
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import redis.asyncio as redis

from app.core.config import settings

logger = structlog.get_logger(__name__)


class MessageRole(str, Enum):
    """消息角色"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Message:
    """会话消息"""

    role: MessageRole
    content: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    npc_id: Optional[str] = None
    trace_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role.value if isinstance(self.role, MessageRole) else self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "npc_id": self.npc_id,
            "trace_id": self.trace_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        role = data.get("role", "user")
        if isinstance(role, str):
            role = MessageRole(role)
        return cls(
            role=role,
            content=data.get("content", ""),
            timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
            npc_id=data.get("npc_id"),
            trace_id=data.get("trace_id"),
            metadata=data.get("metadata", {}),
        )

    def to_prompt_format(self) -> str:
        """转换为 Prompt 格式"""
        role_label = "用户" if self.role == MessageRole.USER else "助手"
        return f"{role_label}: {self.content}"


@dataclass
class SessionConfig:
    """会话配置"""

    max_messages: int = 10          # 最大消息条数
    max_chars: int = 4000           # 最大字符数
    ttl_seconds: int = 86400        # 会话 TTL（24 小时）
    key_prefix: str = "yantian:session"


class SessionMemory:
    """
    Redis 会话记忆管理

    短记忆 Key 格式: {prefix}:short:{tenant_id}:{site_id}:{session_id}:{npc_id}
    偏好记忆 Key 格式: {prefix}:pref:{tenant_id}:{site_id}:{session_id}

    特性：
    - NPC 隔离：同一 session 不同 NPC 的对话记忆分开存储
    - 偏好记忆：跨 NPC 共享，仅存用户偏好
    - 按条数裁剪（保留最近 N 条）
    - 按字符裁剪（超过上限时从最早消息开始删除）
    - 自动 TTL 过期
    - 优雅降级（Redis 不可用时不阻塞）
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        config: Optional[SessionConfig] = None,
    ):
        self._redis_url = redis_url or settings.REDIS_URL
        self._config = config or SessionConfig(
            max_messages=getattr(settings, 'MEMORY_MAX_MESSAGES', 10),
            max_chars=getattr(settings, 'MEMORY_MAX_CHARS', 4000),
            ttl_seconds=getattr(settings, 'MEMORY_TTL_SECONDS', 86400),
        )

        self._client: Optional[redis.Redis] = None
        self._connected = False

    async def connect(self) -> bool:
        """连接 Redis"""
        try:
            self._client = redis.from_url(
                self._redis_url,
                decode_responses=True,
            )
            await self._client.ping()
            self._connected = True
            logger.info("session_memory_connected")
            return True
        except Exception as e:
            logger.error("session_memory_connect_failed", error=str(e))
            self._connected = False
            return False

    async def close(self) -> None:
        """关闭连接"""
        if self._client:
            await self._client.close()
        self._connected = False

    def _build_short_key(
        self, tenant_id: str, site_id: str, session_id: str, npc_id: str
    ) -> str:
        """构建短记忆 Redis Key（NPC 隔离）"""
        return f"{self._config.key_prefix}:short:{tenant_id}:{site_id}:{session_id}:{npc_id}"

    def _build_pref_key(self, tenant_id: str, site_id: str, session_id: str) -> str:
        """构建偏好记忆 Redis Key（跨 NPC 共享）"""
        return f"{self._config.key_prefix}:pref:{tenant_id}:{site_id}:{session_id}"

    def _build_key(self, tenant_id: str, site_id: str, session_id: str) -> str:
        """构建 Redis Key（兼容旧接口，不推荐使用）"""
        return f"{self._config.key_prefix}:{tenant_id}:{site_id}:{session_id}"

    async def append_message(
        self,
        tenant_id: str,
        site_id: str,
        session_id: str,
        message: Message,
        npc_id: Optional[str] = None,
    ) -> bool:
        """
        追加消息到会话（NPC 隔离）

        自动执行裁剪策略
        """
        if not self._connected or not self._client:
            await self.connect()
            if not self._connected:
                return False

        # 使用 NPC 隔离的 key
        if npc_id:
            key = self._build_short_key(tenant_id, site_id, session_id, npc_id)
        else:
            key = self._build_key(tenant_id, site_id, session_id)

        log = logger.bind(session_id=session_id, npc_id=npc_id)

        try:
            # 追加消息
            await self._client.rpush(key, json.dumps(message.to_dict(), ensure_ascii=False))

            # 设置 TTL
            await self._client.expire(key, self._config.ttl_seconds)

            # 裁剪：按条数
            await self._client.ltrim(key, -self._config.max_messages, -1)

            log.debug("message_appended", role=message.role.value)
            return True

        except Exception as e:
            log.error("append_message_failed", error=str(e))
            return False

    async def get_recent_messages(
        self,
        tenant_id: str,
        site_id: str,
        session_id: str,
        npc_id: Optional[str] = None,
        limit: Optional[int] = None,
        max_chars: Optional[int] = None,
    ) -> List[Message]:
        """
        获取最近消息（NPC 隔离）

        Args:
            tenant_id: 租户 ID
            site_id: 站点 ID
            session_id: 会话 ID
            npc_id: NPC ID（用于 NPC 隔离）
            limit: 消息条数限制（默认使用配置）
            max_chars: 字符上限（默认使用配置）

        Returns:
            消息列表（按时间顺序）
        """
        if not self._connected or not self._client:
            await self.connect()
            if not self._connected:
                return []

        # 使用 NPC 隔离的 key
        if npc_id:
            key = self._build_short_key(tenant_id, site_id, session_id, npc_id)
        else:
            key = self._build_key(tenant_id, site_id, session_id)

        limit = limit or self._config.max_messages
        max_chars = max_chars or self._config.max_chars

        try:
            # 获取最近 N 条消息
            raw_messages = await self._client.lrange(key, -limit, -1)

            messages = []
            total_chars = 0

            # 从最新到最旧遍历，按字符上限裁剪
            for raw in reversed(raw_messages):
                try:
                    data = json.loads(raw)
                    msg = Message.from_dict(data)

                    # 检查字符上限
                    msg_chars = len(msg.content)
                    if total_chars + msg_chars > max_chars:
                        break

                    messages.insert(0, msg)
                    total_chars += msg_chars

                except json.JSONDecodeError:
                    continue

            return messages

        except Exception as e:
            logger.error("get_recent_messages_failed", session_id=session_id, error=str(e))
            return []

    async def clear_session(
        self,
        tenant_id: str,
        site_id: str,
        session_id: str,
        npc_id: Optional[str] = None,
    ) -> bool:
        """
        清空会话

        Args:
            npc_id: 如果指定，只清空该 NPC 的记忆；否则清空整个 session
        """
        if not self._connected or not self._client:
            return False

        try:
            if npc_id:
                # 只清空指定 NPC 的短记忆
                key = self._build_short_key(tenant_id, site_id, session_id, npc_id)
                await self._client.delete(key)
                logger.info("npc_session_cleared", session_id=session_id, npc_id=npc_id)
            else:
                # 清空整个 session（包括所有 NPC 的短记忆和偏好记忆）
                pattern = f"{self._config.key_prefix}:*:{tenant_id}:{site_id}:{session_id}*"
                keys = []
                async for key in self._client.scan_iter(match=pattern):
                    keys.append(key)
                if keys:
                    await self._client.delete(*keys)
                logger.info("session_cleared", session_id=session_id, keys_deleted=len(keys))
            return True
        except Exception as e:
            logger.error("clear_session_failed", session_id=session_id, error=str(e))
            return False

    async def get_session_summary(
        self,
        tenant_id: str,
        site_id: str,
        session_id: str,
        npc_id: Optional[str] = None,
        max_messages: int = 5,
    ) -> Dict[str, Any]:
        """
        获取会话摘要（用于 trace 回放）

        Args:
            npc_id: 如果指定，只获取该 NPC 的摘要

        Returns:
            {
                "session_id": "...",
                "npc_id": "...",
                "message_count": 10,
                "recent_messages": [...],
                "first_message_at": "...",
                "last_message_at": "...",
            }
        """
        messages = await self.get_recent_messages(
            tenant_id, site_id, session_id, npc_id=npc_id, limit=max_messages
        )

        if not messages:
            return {
                "session_id": session_id,
                "message_count": 0,
                "recent_messages": [],
            }

        # 获取总消息数
        if npc_id:
            key = self._build_short_key(tenant_id, site_id, session_id, npc_id)
        else:
            key = self._build_key(tenant_id, site_id, session_id)

        total_count = 0
        if self._client:
            try:
                total_count = await self._client.llen(key)
            except Exception:
                pass

        return {
            "session_id": session_id,
            "npc_id": npc_id,
            "message_count": total_count,
            "recent_messages": [
                {
                    "role": m.role.value,
                    "content": m.content[:100] + "..." if len(m.content) > 100 else m.content,
                    "timestamp": m.timestamp,
                }
                for m in messages
            ],
            "first_message_at": messages[0].timestamp if messages else None,
            "last_message_at": messages[-1].timestamp if messages else None,
        }

    def build_context_prompt(
        self,
        messages: List[Message],
        npc_name: str = "助手",
    ) -> str:
        """
        构建上下文 Prompt

        重要：明确标注仅供上下文，不作为事实依据
        """
        if not messages:
            return ""

        lines = [
            "【对话历史 - 仅供上下文参考，不作为事实依据】",
            "以下是与用户的近期对话，帮助你理解用户的兴趣和问题背景。",
            "注意：任何历史事实、人物、事件的信息必须从证据库中检索验证，不能仅凭对话历史回答。",
            "",
        ]

        for msg in messages:
            if msg.role == MessageRole.USER:
                lines.append(f"用户: {msg.content}")
            else:
                lines.append(f"{npc_name}: {msg.content}")

        lines.append("")
        lines.append("【对话历史结束】")

        return "\n".join(lines)


def generate_session_id() -> str:
    """生成 session_id"""
    return f"session-{uuid.uuid4().hex[:16]}"


# ==================
# 偏好记忆
# ==================

@dataclass
class UserPreference:
    """
    用户偏好（跨 NPC 共享）

    重要约束：不得存储任何史实内容
    """

    verbosity: str = "normal"  # brief, normal, detailed
    tone: str = "formal"       # casual, formal, respectful
    interest_tags: List[str] = field(default_factory=list)  # 兴趣标签
    language: str = "zh"       # 语言偏好
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verbosity": self.verbosity,
            "tone": self.tone,
            "interest_tags": self.interest_tags,
            "language": self.language,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserPreference":
        return cls(
            verbosity=data.get("verbosity", "normal"),
            tone=data.get("tone", "formal"),
            interest_tags=data.get("interest_tags", []),
            language=data.get("language", "zh"),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
        )

    def to_prompt_format(self) -> str:
        """转换为 Prompt 格式"""
        lines = ["【用户偏好 - 仅供参考】"]

        verbosity_map = {
            "brief": "用户偏好简洁回答",
            "normal": "用户偏好适中长度回答",
            "detailed": "用户偏好详细回答",
        }
        lines.append(f"- {verbosity_map.get(self.verbosity, '适中长度回答')}")

        tone_map = {
            "casual": "用户偏好轻松随意的语气",
            "formal": "用户偏好正式的语气",
            "respectful": "用户偏好恭敬的语气",
        }
        lines.append(f"- {tone_map.get(self.tone, '正式语气')}")

        if self.interest_tags:
            lines.append(f"- 用户感兴趣的话题：{', '.join(self.interest_tags[:5])}")

        lines.append("【用户偏好结束】")
        return "\n".join(lines)


class PreferenceMemory:
    """
    偏好记忆管理

    Key 格式: {prefix}:pref:{tenant_id}:{site_id}:{session_id}

    特性：
    - 跨 NPC 共享
    - 仅存用户偏好，不存史实
    - Hash 结构存储
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        key_prefix: str = "yantian:session",
        ttl_seconds: int = 86400,
    ):
        self._redis_url = redis_url or settings.REDIS_URL
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds
        self._client: Optional[redis.Redis] = None
        self._connected = False

    async def connect(self) -> bool:
        """连接 Redis"""
        try:
            self._client = redis.from_url(self._redis_url, decode_responses=True)
            await self._client.ping()
            self._connected = True
            return True
        except Exception as e:
            logger.error("preference_memory_connect_failed", error=str(e))
            self._connected = False
            return False

    def _build_key(self, tenant_id: str, site_id: str, session_id: str) -> str:
        """构建偏好记忆 Key"""
        return f"{self._key_prefix}:pref:{tenant_id}:{site_id}:{session_id}"

    async def get_preference(
        self,
        tenant_id: str,
        site_id: str,
        session_id: str,
    ) -> UserPreference:
        """获取用户偏好"""
        if not self._connected or not self._client:
            await self.connect()
            if not self._connected:
                return UserPreference()

        key = self._build_key(tenant_id, site_id, session_id)

        try:
            data = await self._client.hgetall(key)
            if not data:
                return UserPreference()

            # 解析 interest_tags
            if "interest_tags" in data:
                data["interest_tags"] = json.loads(data["interest_tags"])

            return UserPreference.from_dict(data)
        except Exception as e:
            logger.error("get_preference_failed", error=str(e))
            return UserPreference()

    async def update_preference(
        self,
        tenant_id: str,
        site_id: str,
        session_id: str,
        preference: UserPreference,
    ) -> bool:
        """更新用户偏好"""
        if not self._connected or not self._client:
            await self.connect()
            if not self._connected:
                return False

        key = self._build_key(tenant_id, site_id, session_id)

        try:
            data = preference.to_dict()
            # 序列化 interest_tags
            data["interest_tags"] = json.dumps(data["interest_tags"], ensure_ascii=False)

            await self._client.hset(key, mapping=data)
            await self._client.expire(key, self._ttl_seconds)

            logger.debug("preference_updated", session_id=session_id)
            return True
        except Exception as e:
            logger.error("update_preference_failed", error=str(e))
            return False

    async def add_interest_tag(
        self,
        tenant_id: str,
        site_id: str,
        session_id: str,
        tag: str,
    ) -> bool:
        """添加兴趣标签"""
        pref = await self.get_preference(tenant_id, site_id, session_id)

        if tag not in pref.interest_tags:
            pref.interest_tags.append(tag)
            # 限制最多 20 个标签
            pref.interest_tags = pref.interest_tags[-20:]
            pref.updated_at = datetime.utcnow().isoformat()
            return await self.update_preference(tenant_id, site_id, session_id, pref)

        return True

    async def clear_preference(
        self,
        tenant_id: str,
        site_id: str,
        session_id: str,
    ) -> bool:
        """清空用户偏好"""
        if not self._connected or not self._client:
            return False

        key = self._build_key(tenant_id, site_id, session_id)

        try:
            await self._client.delete(key)
            return True
        except Exception as e:
            logger.error("clear_preference_failed", error=str(e))
            return False


# 全局实例
_memory_instance: Optional[SessionMemory] = None
_preference_instance: Optional[PreferenceMemory] = None


async def get_session_memory() -> SessionMemory:
    """获取全局会话记忆实例"""
    global _memory_instance

    if _memory_instance is None:
        _memory_instance = SessionMemory()
        await _memory_instance.connect()

    return _memory_instance


async def get_preference_memory() -> PreferenceMemory:
    """获取全局偏好记忆实例"""
    global _preference_instance

    if _preference_instance is None:
        _preference_instance = PreferenceMemory()
        await _preference_instance.connect()

    return _preference_instance
