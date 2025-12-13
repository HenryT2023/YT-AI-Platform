"""
研学任务模型
"""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import AuditMixin, Base, TenantMixin


class Quest(Base, TenantMixin, AuditMixin):
    """
    研学任务实体

    带 tenant_id/site_id
    """

    __tablename__ = "quests"

    # 主键
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    # 基本信息
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)

    # 类型与分类
    quest_type: Mapped[Optional[str]] = mapped_column(String(50))
    category: Mapped[Optional[str]] = mapped_column(String(100))
    tags: Mapped[list] = mapped_column(ARRAY(String), server_default="{}", nullable=False)

    # 难度与时长
    difficulty: Mapped[Optional[str]] = mapped_column(String(20))
    estimated_duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)

    # 奖励
    rewards: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 前置条件
    prerequisites: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 关联场景
    scene_ids: Mapped[list] = mapped_column(ARRAY(String), server_default="{}", nullable=False)

    # 配置
    config: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 状态
    status: Mapped[str] = mapped_column(String(20), server_default="active", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)

    # 关系
    steps: Mapped[List["QuestStep"]] = relationship(
        "QuestStep",
        back_populates="quest",
        lazy="selectin",
        order_by="QuestStep.step_number",
    )

    def __repr__(self) -> str:
        return f"<Quest(id={self.id}, name={self.name})>"


class QuestStep(Base, TenantMixin, AuditMixin):
    """
    任务步骤实体
    """

    __tablename__ = "quest_steps"

    # 主键
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    # 任务关联
    quest_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("quests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 步骤信息
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # 步骤类型
    step_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # 目标配置
    target_config: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 验证配置
    validation_config: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 提示
    hints: Mapped[list] = mapped_column(ARRAY(String), server_default="{}", nullable=False)

    # 奖励
    rewards: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 关系
    quest: Mapped["Quest"] = relationship("Quest", back_populates="steps")

    def __repr__(self) -> str:
        return f"<QuestStep(quest_id={self.quest_id}, step_number={self.step_number})>"
