"""
会话与消息模型
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import AuditMixin, Base, TenantMixin


class Conversation(Base, TenantMixin, AuditMixin):
    """
    会话实体

    记录用户与 NPC 的对话会话
    带 tenant_id/site_id
    """

    __tablename__ = "conversations"

    # 主键
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    # 会话标识（客户端生成）
    session_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)

    # 参与者
    user_id: Mapped[Optional[str]] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    npc_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)

    # 会话信息
    title: Mapped[Optional[str]] = mapped_column(String(200))
    summary: Mapped[Optional[str]] = mapped_column(Text)

    # 上下文
    context: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 统计
    message_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)

    # 时间
    started_at: Mapped[datetime] = mapped_column(server_default="now()", nullable=False)
    last_message_at: Mapped[Optional[datetime]] = mapped_column()
    ended_at: Mapped[Optional[datetime]] = mapped_column()

    # 状态
    status: Mapped[str] = mapped_column(String(20), server_default="active", nullable=False)

    # 关系
    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        lazy="selectin",
        order_by="Message.created_at",
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, session_id={self.session_id})>"


class Message(Base, TenantMixin):
    """
    消息实体

    会话中的单条消息
    """

    __tablename__ = "messages"

    # 主键
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    # 会话关联
    conversation_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 消息信息
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user/assistant/system
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Token 统计
    tokens: Mapped[Optional[int]] = mapped_column(Integer)

    # 证据链
    evidence_ids: Mapped[list] = mapped_column(ARRAY(String), server_default="{}", nullable=False)
    trace_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)

    # 元数据
    metadata: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 时间
    created_at: Mapped[datetime] = mapped_column(server_default="now()", nullable=False)

    # 关系
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, role={self.role})>"
