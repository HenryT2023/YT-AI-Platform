"""
SQLAlchemy 基础模型与混入类

提供：
- Base: 声明式基类
- TimestampMixin: 时间戳字段
- SoftDeleteMixin: 软删除字段
- AuditMixin: 审计字段
- TenantMixin: 多租户字段
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    声明式基类

    所有模型都应继承此类
    """

    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }


class TimestampMixin:
    """
    时间戳混入类

    提供 created_at 和 updated_at 字段
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """
    软删除混入类

    提供 deleted_at 字段和 is_deleted 属性
    """

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class AuditMixin(TimestampMixin, SoftDeleteMixin):
    """
    审计混入类

    结合时间戳和软删除，并添加创建者/更新者字段
    """

    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class TenantMixin:
    """
    多租户混入类

    提供 tenant_id 和 site_id 字段
    所有业务数据表都应使用此混入
    """

    tenant_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class UUIDPrimaryKeyMixin:
    """
    UUID 主键混入类

    使用 PostgreSQL 原生 UUID 类型
    """

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
