"""
数据库模型通用 Mixins 和工具函数
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlalchemy.orm import declared_attr


def generate_prefixed_uuid(prefix: str) -> str:
    """
    生成带前缀的 UUID
    
    Args:
        prefix: 前缀，如 "ae" (alert event), "as" (alert silence)
    
    Returns:
        格式: {prefix}-{uuid}，如 "ae-550e8400-e29b-41d4-a716-446655440000"
    """
    return f"{prefix}-{uuid.uuid4()}"


class TimestampMixin:
    """时间戳 Mixin，自动添加 created_at 和 updated_at 字段"""
    
    @declared_attr
    def created_at(cls):
        return Column(
            DateTime,
            default=datetime.utcnow,
            nullable=False,
        )
    
    @declared_attr
    def updated_at(cls):
        return Column(
            DateTime,
            default=datetime.utcnow,
            onupdate=datetime.utcnow,
            nullable=False,
        )


class TenantMixin:
    """租户 Mixin，添加 tenant_id 和 site_id 字段"""
    
    @declared_attr
    def tenant_id(cls):
        from sqlalchemy import String
        return Column(String(64), nullable=False, index=True)
    
    @declared_attr
    def site_id(cls):
        from sqlalchemy import String
        return Column(String(64), nullable=True, index=True)
