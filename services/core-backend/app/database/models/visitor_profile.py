"""
游客画像数据模型

包括：
- VisitorProfile: 游客画像主表
- VisitorTag: 游客标签
- VisitorCheckIn: 场景打卡记录
- VisitorInteraction: NPC 交互统计
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class VisitorProfile(Base):
    """游客画像主表"""

    __tablename__ = "visitor_profiles"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    site_id: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), unique=True, index=True)

    # 基础统计
    visit_count: Mapped[int] = mapped_column(Integer, default=0, comment="访问次数")
    total_duration_minutes: Mapped[int] = mapped_column(
        Integer, default=0, comment="总停留时长（分钟）"
    )
    conversation_count: Mapped[int] = mapped_column(Integer, default=0, comment="对话次数")
    quest_completed_count: Mapped[int] = mapped_column(Integer, default=0, comment="完成任务数")
    achievement_count: Mapped[int] = mapped_column(Integer, default=0, comment="获得成就数")
    check_in_count: Mapped[int] = mapped_column(Integer, default=0, comment="打卡次数")

    # 偏好统计
    favorite_npc_id: Mapped[Optional[UUID]] = mapped_column(
        nullable=True, comment="最喜欢的 NPC"
    )
    favorite_scene_id: Mapped[Optional[UUID]] = mapped_column(
        nullable=True, comment="最喜欢的场景"
    )
    interest_tags: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="兴趣标签（自动分析）"
    )

    # 行为特征
    activity_level: Mapped[str] = mapped_column(
        String(20), default="new", comment="活跃度: new/casual/active/power"
    )
    engagement_score: Mapped[float] = mapped_column(
        Float, default=0.0, comment="参与度评分 (0-100)"
    )
    learning_style: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="学习风格: explorer/achiever/socializer"
    )

    # 时间记录
    first_visit_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="首次访问时间"
    )
    last_visit_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="最后访问时间"
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="最后活跃时间"
    )

    # 元数据
    profile_data: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="扩展画像数据"
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    user: Mapped["User"] = relationship("User", back_populates="visitor_profile")
    tags: Mapped[list["VisitorTag"]] = relationship(
        "VisitorTag", back_populates="profile", cascade="all, delete-orphan"
    )
    check_ins: Mapped[list["VisitorCheckIn"]] = relationship(
        "VisitorCheckIn", back_populates="profile", cascade="all, delete-orphan"
    )
    interactions: Mapped[list["VisitorInteraction"]] = relationship(
        "VisitorInteraction", back_populates="profile", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_visitor_profiles_tenant_site", "tenant_id", "site_id"),
        Index("ix_visitor_profiles_activity", "activity_level", "engagement_score"),
    )


class VisitorTag(Base):
    """游客标签"""

    __tablename__ = "visitor_tags"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    site_id: Mapped[str] = mapped_column(String(50), index=True)
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("visitor_profiles.id"), index=True)

    # 标签信息
    tag_type: Mapped[str] = mapped_column(
        String(50), comment="标签类型: interest/behavior/achievement/custom"
    )
    tag_key: Mapped[str] = mapped_column(String(100), comment="标签键")
    tag_value: Mapped[str] = mapped_column(String(200), comment="标签值")
    confidence: Mapped[float] = mapped_column(Float, default=1.0, comment="置信度 (0-1)")

    # 来源
    source: Mapped[str] = mapped_column(
        String(50), default="auto", comment="来源: auto/manual/ai"
    )
    source_ref: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, comment="来源引用（如对话ID、任务ID）"
    )

    # 状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否激活")
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="过期时间"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    profile: Mapped["VisitorProfile"] = relationship("VisitorProfile", back_populates="tags")

    __table_args__ = (
        Index("ix_visitor_tags_tenant_site", "tenant_id", "site_id"),
        Index("ix_visitor_tags_type_key", "tag_type", "tag_key"),
    )


class VisitorCheckIn(Base):
    """场景打卡记录"""

    __tablename__ = "visitor_check_ins"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    site_id: Mapped[str] = mapped_column(String(50), index=True)
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("visitor_profiles.id"), index=True)
    scene_id: Mapped[UUID] = mapped_column(index=True, comment="场景 ID")

    # 打卡信息
    check_in_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="打卡时间"
    )
    duration_minutes: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="停留时长（分钟）"
    )
    
    # 位置信息（可选）
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="纬度")
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="经度")
    accuracy: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="定位精度（米）")

    # 交互信息
    photo_count: Mapped[int] = mapped_column(Integer, default=0, comment="拍照数量")
    interaction_count: Mapped[int] = mapped_column(Integer, default=0, comment="交互次数")
    
    # 元数据
    check_in_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="扩展元数据")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # 关系
    profile: Mapped["VisitorProfile"] = relationship("VisitorProfile", back_populates="check_ins")

    __table_args__ = (
        Index("ix_visitor_check_ins_tenant_site", "tenant_id", "site_id"),
        Index("ix_visitor_check_ins_time", "check_in_at"),
    )


class VisitorInteraction(Base):
    """NPC 交互统计"""

    __tablename__ = "visitor_interactions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    site_id: Mapped[str] = mapped_column(String(50), index=True)
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("visitor_profiles.id"), index=True)
    npc_id: Mapped[UUID] = mapped_column(index=True, comment="NPC ID")

    # 交互统计
    conversation_count: Mapped[int] = mapped_column(Integer, default=0, comment="对话次数")
    message_count: Mapped[int] = mapped_column(Integer, default=0, comment="消息数量")
    total_duration_minutes: Mapped[int] = mapped_column(
        Integer, default=0, comment="总对话时长（分钟）"
    )
    
    # 情感分析
    sentiment_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="情感评分 (-1 到 1)"
    )
    satisfaction_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="满意度评分 (0-5)"
    )

    # 时间记录
    first_interaction_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="首次交互时间"
    )
    last_interaction_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="最后交互时间"
    )

    # 元数据
    interaction_data: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="交互详细数据"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    profile: Mapped["VisitorProfile"] = relationship("VisitorProfile", back_populates="interactions")

    __table_args__ = (
        Index("ix_visitor_interactions_tenant_site", "tenant_id", "site_id"),
        Index("ix_visitor_interactions_time", "last_interaction_at"),
    )
