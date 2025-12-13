"""
用户模型

User 代表系统用户（管理员、运营人员）
与 Visitor（游客）分离，Visitor 是 C 端用户
"""

from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text, Boolean
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import AuditMixin, Base


class UserRole:
    """用户角色常量"""
    SUPER_ADMIN = "super_admin"  # 超级管理员（平台级）
    TENANT_ADMIN = "tenant_admin"  # 租户管理员
    SITE_ADMIN = "site_admin"  # 站点管理员
    OPERATOR = "operator"  # 运营人员
    VIEWER = "viewer"  # 只读用户


class User(Base, AuditMixin):
    """用户实体"""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # 租户归属（super_admin 可为空）
    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("tenants.id"), nullable=True
    )

    # 基本信息
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(200), unique=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    display_name: Mapped[Optional[str]] = mapped_column(String(200))

    # 认证
    hashed_password: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # 角色与权限
    role: Mapped[str] = mapped_column(String(50), default=UserRole.VIEWER)
    permissions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # 可访问的站点列表（空表示可访问租户下所有站点）
    allowed_site_ids: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String(50)))

    # 扩展信息
    profile: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    status: Mapped[str] = mapped_column(String(20), default="active")

    # 关联
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant", back_populates="users")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"

    def has_permission(self, permission: str) -> bool:
        """检查用户是否拥有指定权限"""
        if self.role == UserRole.SUPER_ADMIN:
            return True
        return permission in (self.permissions or [])

    def can_access_site(self, site_id: str) -> bool:
        """检查用户是否可以访问指定站点"""
        if self.role == UserRole.SUPER_ADMIN:
            return True
        if not self.allowed_site_ids:
            return True  # 空列表表示可访问所有
        return site_id in self.allowed_site_ids

    def can_access_tenant(self, tenant_id: str) -> bool:
        """检查用户是否可以访问指定租户"""
        if self.role == UserRole.SUPER_ADMIN:
            return True
        return self.tenant_id == tenant_id


# 避免循环导入
from app.domain.tenant import Tenant
