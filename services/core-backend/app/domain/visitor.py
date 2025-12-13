"""
游客模型

Visitor 代表游客档案，记录游客信息和行为数据
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Visitor(Base, TimestampMixin):
    """游客实体"""

    __tablename__ = "visitors"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    external_id: Mapped[Optional[str]] = mapped_column(String(200))
    identity_provider: Mapped[Optional[str]] = mapped_column(String(50))

    nickname: Mapped[Optional[str]] = mapped_column(String(100))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    phone: Mapped[Optional[str]] = mapped_column(String(20))

    profile: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    last_visit_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    quest_progress: Mapped[list["VisitorQuest"]] = relationship(
        back_populates="visitor", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Visitor(id={self.id}, nickname={self.nickname})>"


class VisitorQuest(Base):
    """游客任务进度"""

    __tablename__ = "visitor_quests"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    visitor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("visitors.id"), nullable=False
    )
    quest_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("quests.id"), nullable=False
    )

    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    current_step: Mapped[int] = mapped_column(Integer, default=1)
    progress: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    score: Mapped[int] = mapped_column(Integer, default=0)
    rewards_claimed: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    visitor: Mapped["Visitor"] = relationship(back_populates="quest_progress")

    def __repr__(self) -> str:
        return f"<VisitorQuest(visitor={self.visitor_id}, quest={self.quest_id}, status={self.status})>"
