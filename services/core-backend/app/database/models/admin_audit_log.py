"""
Admin 操作审计日志模型

记录所有高权限操作，用于审计和追溯
"""

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import Column, String, DateTime, Text, JSON
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class AdminAuditLog(Base):
    """Admin 操作审计日志"""
    
    __tablename__ = "admin_audit_log"
    
    id = Column(String(36), primary_key=True)
    actor = Column(String(255), nullable=False, index=True, comment="操作者标识")
    action = Column(String(100), nullable=False, index=True, comment="操作类型")
    target_type = Column(String(100), nullable=False, index=True, comment="目标类型")
    target_id = Column(String(255), nullable=True, comment="目标 ID")
    payload = Column(JSONB, nullable=True, comment="操作详情")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    def __repr__(self):
        return f"<AdminAuditLog {self.id}: {self.actor} {self.action} {self.target_type}>"
