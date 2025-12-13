"""
用户模型

支持微信小程序 openid/unionid
"""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import AuditMixin, Base

if TYPE_CHECKING:
    from app.database.models.tenant import Tenant


class UserRole:
    """用户角色常量"""
    SUPER_ADMIN = "super_admin"      # 超级管理员（跨租户）
    TENANT_ADMIN = "tenant_admin"    # 租户管理员
    SITE_ADMIN = "site_admin"        # 站点管理员
    OPERATOR = "operator"            # 运营人员
    VIEWER = "viewer"                # 只读用户
    VISITOR = "visitor"              # 游客（小程序用户）


class User(Base, AuditMixin):
    """
    用户实体

    支持两种用户类型：
    1. 系统用户（Admin/Operator）：使用 username/password 登录
    2. 游客用户（Visitor）：使用微信小程序 openid 登录

    带 tenant_id（super_admin 可为空）
    不带 site_id（用户可访问多个站点，通过 allowed_site_ids 控制）
    """

    __tablename__ = "users"

    # 主键
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    # 租户关联（super_admin 可为空）
    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # 登录凭据
    username: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(200), unique=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(200))

    # 微信小程序字段
    wx_openid: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True)
    wx_unionid: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    wx_session_key: Mapped[Optional[str]] = mapped_column(String(200))

    # 用户信息
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    profile: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 角色与权限
    role: Mapped[str] = mapped_column(String(50), server_default="visitor", nullable=False)
    permissions: Mapped[List[str]] = mapped_column(ARRAY(String), server_default="{}", nullable=False)
    allowed_site_ids: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String(50)))

    # 状态
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default="active", nullable=False)

    # 最后登录
    last_login_at: Mapped[Optional[datetime]] = mapped_column()
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(50))

    # 关系
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant", back_populates="users")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"

    @property
    def is_system_user(self) -> bool:
        """是否为系统用户（非游客）"""
        return self.role != UserRole.VISITOR

    @property
    def is_admin(self) -> bool:
        """是否为管理员"""
        return self.role in (UserRole.SUPER_ADMIN, UserRole.TENANT_ADMIN, UserRole.SITE_ADMIN)

    def can_access_site(self, site_id: str) -> bool:
        """检查是否可以访问指定站点"""
        if self.role == UserRole.SUPER_ADMIN:
            return True
        if self.allowed_site_ids is None:
            return True  # 未限制则可访问所有
        return site_id in self.allowed_site_ids
