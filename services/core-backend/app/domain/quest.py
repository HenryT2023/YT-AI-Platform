"""
研学任务模型

Quest 代表研学任务，包含多个步骤（QuestStep）
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import AuditMixin, Base


class Quest(Base, AuditMixin):
    """研学任务实体"""

    __tablename__ = "quests"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    site_id: Mapped[str] = mapped_column(String(50), ForeignKey("sites.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    quest_type: Mapped[Optional[str]] = mapped_column(String(50))

    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    rewards: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    prerequisites: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    available_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    available_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    time_limit_minutes: Mapped[Optional[int]] = mapped_column(Integer)

    scene_ids: Mapped[Optional[list[UUID]]] = mapped_column(ARRAY(PG_UUID(as_uuid=True)))

    difficulty: Mapped[Optional[str]] = mapped_column(String(20))
    category: Mapped[Optional[str]] = mapped_column(String(50))
    tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String(50)))

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")

    steps: Mapped[list["QuestStep"]] = relationship(
        back_populates="quest", lazy="selectin", order_by="QuestStep.step_number"
    )

    def __repr__(self) -> str:
        return f"<Quest(id={self.id}, name={self.name})>"


class QuestStep(Base):
    """任务步骤实体"""

    __tablename__ = "quest_steps"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    quest_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("quests.id"), nullable=False
    )

    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    step_type: Mapped[Optional[str]] = mapped_column(String(50))

    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    poi_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("pois.id"))
    npc_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("npcs.id"))

    validation_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    hints: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))

    status: Mapped[str] = mapped_column(String(20), default="active")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", onupdate="now()", nullable=False
    )

    quest: Mapped["Quest"] = relationship(back_populates="steps")

    def __repr__(self) -> str:
        return f"<QuestStep(id={self.id}, quest_id={self.quest_id}, step={self.step_number})>"
