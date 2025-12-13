"""
告警事件与静默数据模型

- AlertEvent: 告警事件历史记录
- AlertSilence: 告警静默规则
"""

from datetime import datetime
from typing import Any, Dict, Optional
from enum import Enum

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Text,
    Float,
    Index,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base
from app.database.mixins import generate_prefixed_uuid


class AlertStatus(str, Enum):
    """告警状态"""
    FIRING = "firing"
    RESOLVED = "resolved"


class AlertEvent(Base):
    """
    告警事件
    
    记录告警触发和解决的历史，支持去重和复盘
    """
    __tablename__ = "alerts_events"
    
    id = Column(
        String(36),
        primary_key=True,
        default=lambda: generate_prefixed_uuid("ae"),
    )
    
    # 多租户
    tenant_id = Column(String(64), nullable=False, index=True)
    site_id = Column(String(64), nullable=True, index=True)
    
    # 告警信息
    alert_code = Column(String(128), nullable=False, index=True)
    severity = Column(String(32), nullable=False, index=True)
    status = Column(
        SQLEnum(AlertStatus, name="alert_status"),
        nullable=False,
        default=AlertStatus.FIRING,
        index=True,
    )
    
    # 评估窗口
    window = Column(String(16), nullable=False, default="15m")
    
    # 指标值
    current_value = Column(Float, nullable=True)
    threshold = Column(Float, nullable=True)
    condition = Column(String(16), nullable=True)
    unit = Column(String(32), nullable=True)
    
    # 去重键：tenant|site|code|window
    dedup_key = Column(String(256), nullable=False, index=True, unique=False)
    
    # 时间戳
    first_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    
    # 上下文（用于复盘）
    context = Column(JSONB, nullable=False, default=dict)
    # context 结构:
    # {
    #   "active_release_id": "rel-xxx",
    #   "active_release_name": "Release v1.0",
    #   "active_experiment_id": "exp-xxx",
    #   "active_experiment_name": "A/B Test",
    #   "metrics_snapshot": {...},
    #   "recommended_actions": [...]
    # }
    
    # 通知状态
    webhook_sent = Column(String(16), nullable=True)  # sent/failed/skipped
    webhook_sent_at = Column(DateTime, nullable=True)
    
    # 审计
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_alerts_events_tenant_status", "tenant_id", "status"),
        Index("ix_alerts_events_dedup_status", "dedup_key", "status"),
        Index("ix_alerts_events_first_seen", "first_seen_at"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "alert_code": self.alert_code,
            "severity": self.severity,
            "status": self.status.value if isinstance(self.status, AlertStatus) else self.status,
            "window": self.window,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "condition": self.condition,
            "unit": self.unit,
            "dedup_key": self.dedup_key,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "context": self.context,
            "webhook_sent": self.webhook_sent,
            "webhook_sent_at": self.webhook_sent_at.isoformat() if self.webhook_sent_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AlertSilence(Base):
    """
    告警静默规则
    
    在指定时间范围内静默特定告警
    """
    __tablename__ = "alerts_silences"
    
    id = Column(
        String(36),
        primary_key=True,
        default=lambda: generate_prefixed_uuid("as"),
    )
    
    # 多租户
    tenant_id = Column(String(64), nullable=False, index=True)
    site_id = Column(String(64), nullable=True, index=True)
    
    # 匹配条件（可选，为空表示匹配所有）
    alert_code = Column(String(128), nullable=True, index=True)
    severity = Column(String(32), nullable=True, index=True)
    
    # 静默时间范围
    starts_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    ends_at = Column(DateTime, nullable=False)
    
    # 原因与创建者
    reason = Column(Text, nullable=True)
    created_by = Column(String(128), nullable=False, default="admin_console")
    
    # 审计
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_alerts_silences_tenant_active", "tenant_id", "starts_at", "ends_at"),
    )
    
    def is_active(self, at: Optional[datetime] = None) -> bool:
        """检查静默是否在指定时间生效"""
        check_time = at or datetime.utcnow()
        return self.starts_at <= check_time <= self.ends_at
    
    def matches(self, alert_code: str, severity: str) -> bool:
        """检查是否匹配告警"""
        # 如果指定了 alert_code，必须匹配
        if self.alert_code and self.alert_code != alert_code:
            return False
        # 如果指定了 severity，必须匹配
        if self.severity and self.severity != severity:
            return False
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "alert_code": self.alert_code,
            "severity": self.severity,
            "starts_at": self.starts_at.isoformat() if self.starts_at else None,
            "ends_at": self.ends_at.isoformat() if self.ends_at else None,
            "reason": self.reason,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_active": self.is_active(),
        }
