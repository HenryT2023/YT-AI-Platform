"""
租户模型

Tenant 是多租户架构的顶层实体
一个 Tenant 可以拥有多个 Site
"""

from typing import Any, Optional

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import AuditMixin, Base


class Tenant(Base, AuditMixin):
    """租户实体"""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)

    # 租户级配置
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # 订阅/计费信息
    plan: Mapped[str] = mapped_column(String(50), default="free")
    quota: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # 联系信息
    contact_email: Mapped[Optional[str]] = mapped_column(String(200))
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50))

    status: Mapped[str] = mapped_column(String(20), default="active")

    # 关联
    sites: Mapped[list["Site"]] = relationship(
        "Site", back_populates="tenant", lazy="selectin"
    )
    users: Mapped[list["User"]] = relationship(
        "User", back_populates="tenant", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name={self.name})>"


# 避免循环导入
from app.domain.site import Site
from app.domain.user import User
