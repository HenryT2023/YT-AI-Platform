"""
Release 数据库模型

策略与内容发布包，支持多站点、一键切换与回滚
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from sqlalchemy import Column, String, DateTime, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class ReleaseStatus(str, Enum):
    """Release 状态"""
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class Release(Base):
    """发布包表"""
    
    __tablename__ = "releases"
    
    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(100), nullable=False, index=True, comment="租户 ID")
    site_id = Column(String(100), nullable=False, index=True, comment="站点 ID")
    name = Column(String(255), nullable=False, comment="发布包名称")
    description = Column(Text, nullable=True, comment="发布包描述")
    status = Column(
        SQLEnum(ReleaseStatus),
        default=ReleaseStatus.DRAFT,
        nullable=False,
        index=True,
        comment="状态: draft/active/archived",
    )
    payload = Column(JSONB, nullable=False, comment="发布包内容")
    created_by = Column(String(255), nullable=False, comment="创建者")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    activated_at = Column(DateTime, nullable=True, comment="激活时间")
    archived_at = Column(DateTime, nullable=True, comment="归档时间")
    
    def __repr__(self):
        return f"<Release {self.id}: {self.name} ({self.status})>"


class ReleaseHistory(Base):
    """发布历史记录表"""
    
    __tablename__ = "release_history"
    
    id = Column(String(36), primary_key=True)
    release_id = Column(String(36), nullable=False, index=True, comment="Release ID")
    tenant_id = Column(String(100), nullable=False, index=True)
    site_id = Column(String(100), nullable=False, index=True)
    action = Column(String(50), nullable=False, comment="操作: activate/rollback/archive")
    previous_release_id = Column(String(36), nullable=True, comment="前一个 active release")
    operator = Column(String(255), nullable=False, comment="操作者")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    def __repr__(self):
        return f"<ReleaseHistory {self.id}: {self.action} {self.release_id}>"
