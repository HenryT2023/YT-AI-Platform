"""
站点模型

Site 是多站点架构的核心实体
一个 Tenant 可以拥有多个 Site
所有业务实体都通过 tenant_id + site_id 关联
"""

from typing import Any, Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import AuditMixin, Base


class Site(Base, AuditMixin):
    """站点实体"""

    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)

    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    theme: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    location_lat: Mapped[Optional[float]] = mapped_column()
    location_lng: Mapped[Optional[float]] = mapped_column()
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Shanghai")

    status: Mapped[str] = mapped_column(String(20), default="active")

    # 关联
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="sites")
    scenes: Mapped[list["Scene"]] = relationship(back_populates="site", lazy="selectin")
    npcs: Mapped[list["NPC"]] = relationship(back_populates="site", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Site(id={self.id}, tenant_id={self.tenant_id}, name={self.name})>"


from app.domain.tenant import Tenant
from app.domain.scene import Scene
from app.domain.npc import NPC
