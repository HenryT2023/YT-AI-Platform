"""
站点模型

带 tenant_id，不带 site_id（自身就是站点）
"""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import AuditMixin, Base

if TYPE_CHECKING:
    from app.database.models.tenant import Tenant
    from app.database.models.content import Content
    from app.database.models.npc_profile import NPCProfile


class Site(Base, AuditMixin):
    """
    站点实体

    属于某个租户，是业务数据的隔离单元
    带 tenant_id，不带 site_id（自身就是站点）
    """

    __tablename__ = "sites"

    # 主键：使用简短的字符串 ID（如 "yantian-main"）
    id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # 租户关联
    tenant_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 基本信息
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)

    # 配置
    config: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    theme: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 地理位置
    location_lat: Mapped[Optional[float]] = mapped_column(Float)
    location_lng: Mapped[Optional[float]] = mapped_column(Float)
    timezone: Mapped[str] = mapped_column(String(50), server_default="Asia/Shanghai")

    # 状态
    status: Mapped[str] = mapped_column(String(20), server_default="active", nullable=False)

    # 关系
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="sites")
    contents: Mapped[List["Content"]] = relationship("Content", back_populates="site", lazy="selectin")
    npc_profiles: Mapped[List["NPCProfile"]] = relationship("NPCProfile", back_populates="site", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Site(id={self.id}, tenant_id={self.tenant_id}, name={self.name})>"
