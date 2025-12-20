"""
站点模型

带 tenant_id，不带 site_id（自身就是站点）
"""

from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
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
    logo_url: Mapped[Optional[str]] = mapped_column(String(500))

    # 配置
    config: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    theme: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 功能开关
    features: Mapped[dict] = mapped_column(
        JSONB,
        server_default='{"quest_enabled": true, "npc_enabled": true, "iot_enabled": false}',
        nullable=False,
    )

    # 运营配置
    operating_hours: Mapped[dict] = mapped_column(
        JSONB,
        server_default='{"open": "08:00", "close": "18:00"}',
        nullable=False,
    )
    contact_info: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 地理位置
    location_lat: Mapped[Optional[float]] = mapped_column(Float)
    location_lng: Mapped[Optional[float]] = mapped_column(Float)
    address: Mapped[Optional[str]] = mapped_column(String(500))
    timezone: Mapped[str] = mapped_column(String(50), server_default="Asia/Shanghai")

    # 状态: active | maintenance | disabled
    status: Mapped[str] = mapped_column(String(20), server_default="active", nullable=False)

    # 关系
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="sites")
    contents: Mapped[List["Content"]] = relationship("Content", back_populates="site", lazy="selectin")
    npc_profiles: Mapped[List["NPCProfile"]] = relationship("NPCProfile", back_populates="site", lazy="selectin")
    stats: Mapped[List["SiteStatsDaily"]] = relationship("SiteStatsDaily", back_populates="site", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Site(id={self.id}, tenant_id={self.tenant_id}, name={self.name})>"


class SiteStatsDaily(Base):
    """
    站点每日统计

    记录站点每日的运营数据快照
    """

    __tablename__ = "site_stats_daily"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # 站点关联
    site_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 统计日期
    stat_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # 访客统计
    visitor_uv: Mapped[int] = mapped_column(Integer, default=0)  # 独立访客数
    visitor_pv: Mapped[int] = mapped_column(Integer, default=0)  # 页面访问量
    new_visitors: Mapped[int] = mapped_column(Integer, default=0)  # 新访客数

    # 任务统计
    quest_started: Mapped[int] = mapped_column(Integer, default=0)  # 开始任务数
    quest_completed: Mapped[int] = mapped_column(Integer, default=0)  # 完成任务数

    # NPC 对话统计
    npc_conversations: Mapped[int] = mapped_column(Integer, default=0)  # 对话数
    npc_messages: Mapped[int] = mapped_column(Integer, default=0)  # 消息数

    # 成就统计
    achievements_unlocked: Mapped[int] = mapped_column(Integer, default=0)  # 解锁成就数

    # 打卡统计
    check_ins: Mapped[int] = mapped_column(Integer, default=0)  # 打卡次数

    # 扩展数据
    extra_data: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # 关系
    site: Mapped["Site"] = relationship("Site", back_populates="stats")

    def __repr__(self) -> str:
        return f"<SiteStatsDaily(site_id={self.site_id}, date={self.stat_date})>"
