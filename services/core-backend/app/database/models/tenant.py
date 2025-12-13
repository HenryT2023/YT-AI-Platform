"""
租户模型

全局表，不带 tenant_id/site_id
"""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import AuditMixin, Base

if TYPE_CHECKING:
    from app.database.models.site import Site
    from app.database.models.user import User


class Tenant(Base, AuditMixin):
    """
    租户实体

    全局表：管理多个站点的顶层组织
    不带 tenant_id（自身就是租户）
    """

    __tablename__ = "tenants"

    # 主键：使用简短的字符串 ID（如 "yantian"）
    id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # 基本信息
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)

    # 配置
    config: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 套餐与配额
    plan: Mapped[str] = mapped_column(String(50), server_default="free", nullable=False)
    quota: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 联系方式
    contact_email: Mapped[Optional[str]] = mapped_column(String(200))
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50))

    # 状态
    status: Mapped[str] = mapped_column(String(20), server_default="active", nullable=False)

    # 关系
    sites: Mapped[List["Site"]] = relationship("Site", back_populates="tenant", lazy="selectin")
    users: Mapped[List["User"]] = relationship("User", back_populates="tenant", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name={self.name})>"
