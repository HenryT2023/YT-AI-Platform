"""
Policy 数据库模型

Evidence Gate Policy 的数据库存储，作为真源（Source of Truth）
"""

from datetime import datetime
from typing import Any, Dict

from sqlalchemy import Column, String, DateTime, Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class Policy(Base):
    """策略配置表"""
    
    __tablename__ = "policies"
    
    id = Column(String(36), primary_key=True)
    name = Column(String(100), nullable=False, index=True, comment="策略名称")
    version = Column(String(50), nullable=False, index=True, comment="版本号")
    description = Column(Text, nullable=True, comment="策略描述")
    content = Column(JSONB, nullable=False, comment="策略内容 JSON")
    is_active = Column(Boolean, default=False, nullable=False, index=True, comment="是否为活跃版本")
    operator = Column(String(255), nullable=False, comment="操作者")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    def __repr__(self):
        return f"<Policy {self.name}:{self.version} active={self.is_active}>"
