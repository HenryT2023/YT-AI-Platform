"""
会话记忆模块

多轮对话记忆管理，支持：
- Redis 存储
- 按 tenant_id/site_id/session_id/npc_id 分区（NPC 隔离）
- 短记忆：对话历史
- 偏好记忆：用户偏好（跨 NPC 共享）
- 消息裁剪策略
- 会话清理
"""

from app.memory.redis_memory import (
    SessionMemory,
    Message,
    MessageRole,
    get_session_memory,
    PreferenceMemory,
    UserPreference,
    get_preference_memory,
    generate_session_id,
)

__all__ = [
    "SessionMemory",
    "Message",
    "MessageRole",
    "get_session_memory",
    "PreferenceMemory",
    "UserPreference",
    "get_preference_memory",
    "generate_session_id",
]
