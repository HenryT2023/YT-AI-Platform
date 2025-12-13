"""
站点模型

Site 是多租户架构的核心实体，所有其他实体都通过 site_id 关联
"""

from typing import Any, Optional

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import AuditMixin, Base


class Site(Base, AuditMixin):
    """站点实体"""

    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)

    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    theme: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    location_lat: Mapped[Optional[float]] = mapped_column()
    location_lng: Mapped[Optional[float]] = mapped_column()
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Shanghai")

    status: Mapped[str] = mapped_column(String(20), default="active")

    scenes: Mapped[list["Scene"]] = relationship(back_populates="site", lazy="selectin")
    npcs: Mapped[list["NPC"]] = relationship(back_populates="site", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Site(id={self.id}, name={self.name})>"


from app.domain.scene import Scene
from app.domain.npc import NPC
