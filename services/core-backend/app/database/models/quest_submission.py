"""
研学任务提交记录模型

用于记录游客提交的任务 proof
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, TenantMixin


class QuestSubmission(Base, TenantMixin, TimestampMixin):
    """
    任务提交记录

    记录游客提交的任务 proof，用于进度追踪
    """

    __tablename__ = "quest_submissions"

    # 主键
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # 会话标识（游客端生成）
    session_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    # 任务标识
    quest_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    # 提交类型
    proof_type: Mapped[str] = mapped_column(
        String(50),
        server_default="text",
        nullable=False,
    )

    # 提交内容
    proof_payload: Mapped[dict] = mapped_column(
        JSONB,
        server_default="{}",
        nullable=False,
    )

    # 状态: submitted, approved, rejected (legacy, 保留兼容)
    status: Mapped[str] = mapped_column(
        String(20),
        server_default="submitted",
        nullable=False,
    )

    # ============================================================
    # 审核流程字段 (v0.2.2)
    # ============================================================
    
    # 审核状态: pending / approved / rejected
    review_status: Mapped[str] = mapped_column(
        String(20),
        server_default="pending",
        nullable=False,
        index=True,
    )
    
    # 审核备注
    review_comment: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    
    # 审核时间
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # 审核人 (user_id)
    reviewed_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # 复合索引：用于查询和防刷
    __table_args__ = (
        Index(
            "ix_quest_submissions_tenant_site_session_quest",
            "tenant_id",
            "site_id",
            "session_id",
            "quest_id",
        ),
        Index(
            "ix_quest_submissions_session_quest_created",
            "session_id",
            "quest_id",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return f"<QuestSubmission(id={self.id}, quest_id={self.quest_id}, session_id={self.session_id})>"
