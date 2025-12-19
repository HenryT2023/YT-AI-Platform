"""
二十四节气与农耕知识数据模型
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


class SolarTerm(Base):
    """二十四节气表（全局数据，不分租户）"""

    __tablename__ = "solar_terms"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    
    # 基本信息
    code: Mapped[str] = mapped_column(String(50), unique=True, comment="唯一标识码")
    name: Mapped[str] = mapped_column(String(50), comment="节气名称")
    order: Mapped[int] = mapped_column(Integer, comment="顺序 1-24")
    
    # 日期范围（公历）
    month: Mapped[int] = mapped_column(Integer, comment="公历月份")
    day_start: Mapped[int] = mapped_column(Integer, comment="起始日（约数）")
    day_end: Mapped[int] = mapped_column(Integer, comment="结束日（约数）")
    
    # 内容
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="节气描述")
    farming_advice: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="农耕建议")
    cultural_customs: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="文化习俗")
    poems: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="相关诗词")
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_solar_terms_order", "order"),
        Index("ix_solar_terms_month", "month"),
    )

    def __repr__(self) -> str:
        return f"<SolarTerm(code={self.code}, name={self.name})>"


class FarmingKnowledge(Base):
    """农耕知识表"""

    __tablename__ = "farming_knowledge"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    site_id: Mapped[str] = mapped_column(String(50), index=True)
    
    # 关联节气
    solar_term_code: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, index=True, comment="关联节气代码"
    )
    
    # 分类
    category: Mapped[str] = mapped_column(
        String(50), default="general", comment="分类: crop/tool/technique/custom/general"
    )
    
    # 内容
    title: Mapped[str] = mapped_column(String(200), comment="标题")
    content: Mapped[str] = mapped_column(Text, comment="内容")
    media_urls: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="图片/视频 URL")
    related_pois: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="关联兴趣点")
    
    # 状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序")
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_farming_knowledge_tenant_site", "tenant_id", "site_id"),
        Index("ix_farming_knowledge_term", "solar_term_code"),
        Index("ix_farming_knowledge_category", "category"),
    )

    def __repr__(self) -> str:
        return f"<FarmingKnowledge(id={self.id}, title={self.title})>"
