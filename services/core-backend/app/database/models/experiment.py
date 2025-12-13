"""
A/B 实验模型

支持策略 A/B 测试：
- 实验定义与配置
- 稳定分桶
- 归因追踪
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TenantMixin


class ExperimentStatus(str, Enum):
    """实验状态"""
    DRAFT = "draft"       # 草稿
    ACTIVE = "active"     # 活跃
    PAUSED = "paused"     # 暂停
    COMPLETED = "completed"  # 已完成


class Experiment(Base, TenantMixin):
    """
    A/B 实验定义
    
    配置实验的 variants、流量比例、策略覆写
    """
    
    __tablename__ = "experiments"
    
    # 主键
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )
    
    # 实验名称
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # 状态
    status: Mapped[str] = mapped_column(
        String(20),
        server_default="draft",
        nullable=False,
        index=True,
    )
    
    # 配置（JSONB）
    # 结构：
    # {
    #   "variants": [
    #     {"name": "control", "weight": 50, "strategy_overrides": {"retrieval_strategy": "trgm"}},
    #     {"name": "treatment", "weight": 50, "strategy_overrides": {"retrieval_strategy": "hybrid"}}
    #   ],
    #   "subject_type": "session_id",  # user_id 或 session_id
    #   "target_metrics": ["citations_rate", "p95_latency_ms"]
    # }
    config: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    
    # 时间
    start_at: Mapped[Optional[datetime]] = mapped_column()
    end_at: Mapped[Optional[datetime]] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default="now()", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default="now()", onupdate="now()", nullable=False)
    
    def __repr__(self) -> str:
        return f"<Experiment(id={self.id}, name={self.name}, status={self.status})>"
    
    def get_variants(self) -> List[dict]:
        """获取 variants 列表"""
        return self.config.get("variants", [])
    
    def get_subject_type(self) -> str:
        """获取分桶主体类型"""
        return self.config.get("subject_type", "session_id")


class ExperimentAssignment(Base):
    """
    实验分桶记录
    
    记录每个 subject 被分配到的 variant
    """
    
    __tablename__ = "experiment_assignments"
    
    # 主键
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )
    
    # 实验关联
    experiment_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # 多租户
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    site_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # 分桶主体
    subject_type: Mapped[str] = mapped_column(String(20), nullable=False)  # user_id / session_id
    subject_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    
    # 分配结果
    variant: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    bucket_hash: Mapped[int] = mapped_column(Integer, nullable=False)  # hash 值（0-99）
    
    # 策略快照
    strategy_overrides: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    
    # 时间
    assigned_at: Mapped[datetime] = mapped_column(server_default="now()", nullable=False)
    
    def __repr__(self) -> str:
        return f"<ExperimentAssignment(experiment={self.experiment_id}, subject={self.subject_key}, variant={self.variant})>"
