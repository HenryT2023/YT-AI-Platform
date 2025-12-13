"""
分析事件模型

记录用户行为事件
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TenantMixin


class AnalyticsEvent(Base, TenantMixin):
    """
    分析事件实体

    记录用户行为事件，用于数据分析
    带 tenant_id/site_id
    """

    __tablename__ = "analytics_events"

    # 主键
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    # 追踪信息
    trace_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)

    # 用户信息
    user_id: Mapped[Optional[str]] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # 事件信息
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event_data: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 设备信息
    device_type: Mapped[Optional[str]] = mapped_column(String(50))
    device_id: Mapped[Optional[str]] = mapped_column(String(200))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50))

    # 位置信息
    location_lat: Mapped[Optional[float]] = mapped_column()
    location_lng: Mapped[Optional[float]] = mapped_column()

    # 时间
    created_at: Mapped[datetime] = mapped_column(server_default="now()", nullable=False)

    def __repr__(self) -> str:
        return f"<AnalyticsEvent(id={self.id}, event_type={self.event_type})>"
