"""
成就体系数据模型

包括：
- Achievement: 成就定义
- UserAchievement: 用户成就记录
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class AchievementCategory:
    """成就分类常量"""
    EXPLORATION = "exploration"  # 探索类
    SOCIAL = "social"            # 社交类
    LEARNING = "learning"        # 学习类
    SPECIAL = "special"          # 特殊类


class AchievementTier:
    """成就等级常量"""
    BRONZE = 1    # 铜
    SILVER = 2    # 银
    GOLD = 3      # 金
    DIAMOND = 4   # 钻石


class RuleType:
    """规则类型常量"""
    COUNT = "count"          # 计数型
    EVENT = "event"          # 事件型
    COMPOSITE = "composite"  # 组合型


class Achievement(Base):
    """成就定义表"""

    __tablename__ = "achievements"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    site_id: Mapped[str] = mapped_column(String(50), index=True)

    # 基本信息
    code: Mapped[str] = mapped_column(String(100), comment="唯一标识码")
    name: Mapped[str] = mapped_column(String(200), comment="显示名称")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="描述")
    icon_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="图标 URL")

    # 分类与等级
    category: Mapped[str] = mapped_column(
        String(50), default=AchievementCategory.EXPLORATION, comment="分类"
    )
    tier: Mapped[int] = mapped_column(
        Integer, default=AchievementTier.BRONZE, comment="等级: 1=铜, 2=银, 3=金, 4=钻石"
    )
    points: Mapped[int] = mapped_column(Integer, default=10, comment="积分值")

    # 规则配置
    rule_type: Mapped[str] = mapped_column(
        String(50), default=RuleType.COUNT, comment="规则类型: count/event/composite"
    )
    rule_config: Mapped[dict] = mapped_column(
        JSON, default=dict, comment="规则配置 JSON"
    )

    # 状态
    is_hidden: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否隐藏成就（解锁前不可见）"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="是否启用"
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序")

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    user_achievements: Mapped[list["UserAchievement"]] = relationship(
        "UserAchievement", back_populates="achievement", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_achievements_tenant_site", "tenant_id", "site_id"),
        Index("ix_achievements_code", "tenant_id", "site_id", "code", unique=True),
        Index("ix_achievements_category", "category"),
        Index("ix_achievements_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Achievement(id={self.id}, code={self.code}, name={self.name})>"


class UserAchievement(Base):
    """用户成就记录表"""

    __tablename__ = "user_achievements"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    site_id: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    achievement_id: Mapped[UUID] = mapped_column(ForeignKey("achievements.id"), index=True)

    # 解锁信息
    unlocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="解锁时间"
    )

    # 进度（用于计数型成就）
    progress: Mapped[int] = mapped_column(Integer, default=0, comment="当前进度")
    progress_target: Mapped[int] = mapped_column(Integer, default=0, comment="目标值")

    # 来源
    source: Mapped[str] = mapped_column(
        String(50), default="auto", comment="来源: auto/manual"
    )
    source_ref: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, comment="来源引用（如触发的事件 ID）"
    )

    # 扩展数据
    achievement_metadata: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="扩展元数据"
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    achievement: Mapped["Achievement"] = relationship("Achievement", back_populates="user_achievements")
    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        Index("ix_user_achievements_tenant_site", "tenant_id", "site_id"),
        Index("ix_user_achievements_user", "user_id"),
        Index("ix_user_achievements_unique", "user_id", "achievement_id", unique=True),
        Index("ix_user_achievements_unlocked", "unlocked_at"),
    )

    def __repr__(self) -> str:
        return f"<UserAchievement(id={self.id}, user_id={self.user_id}, achievement_id={self.achievement_id})>"
