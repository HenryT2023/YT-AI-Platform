"""
向量同步任务模型

记录向量同步任务的执行状态和结果
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class VectorSyncStatus(str, Enum):
    """同步任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VectorSyncJob(Base, TimestampMixin):
    """
    向量同步任务

    记录全量/增量同步任务的执行情况
    """

    __tablename__ = "vector_sync_jobs"

    # 主键
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    # 租户/站点
    tenant_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    # 任务类型
    job_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="full_sync",
    )  # full_sync / incremental / repair

    # 状态
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="pending",
        index=True,
    )

    # 时间
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # 统计
    total_items: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    skip_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)

    # 进度
    progress_percent: Mapped[float] = mapped_column(Float, server_default="0", nullable=False)
    current_batch: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    total_batches: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)

    # 错误信息
    error_summary: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 配置
    config: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 触发者
    triggered_by: Mapped[Optional[str]] = mapped_column(String(100))

    def __repr__(self) -> str:
        return f"<VectorSyncJob(id={self.id}, status={self.status}, progress={self.progress_percent}%)>"

    @property
    def duration_seconds(self) -> Optional[float]:
        """计算任务耗时"""
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "job_type": self.job_type,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "total_items": self.total_items,
            "success_count": self.success_count,
            "skip_count": self.skip_count,
            "failure_count": self.failure_count,
            "progress_percent": self.progress_percent,
            "duration_seconds": self.duration_seconds,
            "error_summary": self.error_summary,
        }
