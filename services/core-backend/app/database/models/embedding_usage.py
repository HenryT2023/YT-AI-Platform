"""
Embedding 使用审计模型

记录每次 embedding 调用的详细信息，用于成本监控、去重统计和限流治理
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TenantMixin


class EmbeddingStatus(str, Enum):
    """Embedding 调用状态"""
    SUCCESS = "success"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    DEDUP_HIT = "dedup_hit"


class EmbeddingObjectType(str, Enum):
    """被向量化的对象类型"""
    EVIDENCE = "evidence"
    CONTENT = "content"
    CONTENT_CHUNK = "content_chunk"


class EmbeddingUsage(Base, TenantMixin):
    """
    Embedding 使用审计表

    记录每次 embedding 调用的详细信息：
    - 调用来源（evidence/content）
    - 提供者和模型
    - 输入字符数和估算 token 数
    - 成本估算
    - 延迟和状态
    - 错误信息（如有）
    """

    __tablename__ = "embedding_usage"

    # 主键
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    # 对象信息
    object_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    object_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Embedding 提供者信息
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False)

    # 输入统计
    input_chars: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_tokens: Mapped[int] = mapped_column(Integer, nullable=False)

    # 成本估算 (USD)
    cost_estimate: Mapped[float] = mapped_column(Float, server_default="0", nullable=False)

    # 性能指标
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    # 状态
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # 错误信息（可选）
    error_type: Mapped[Optional[str]] = mapped_column(String(100))
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # 限流信息（可选）
    backoff_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    retry_count: Mapped[Optional[int]] = mapped_column(Integer)

    # 关联信息（可选）
    trace_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)

    # 内容 hash（用于去重追溯）
    content_hash: Mapped[Optional[str]] = mapped_column(String(64))

    # 时间
    created_at: Mapped[datetime] = mapped_column(server_default="now()", nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<EmbeddingUsage(id={self.id}, object_type={self.object_type}, status={self.status})>"

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """
        估算 token 数量
        
        粗略估算：中文约 2 字符/token，英文约 4 字符/token
        这里使用保守估算：1.5 字符/token
        """
        return max(1, len(text) // 2)

    @classmethod
    def calculate_cost(cls, provider: str, model: str, tokens: int) -> float:
        """
        计算成本估算 (USD)
        
        基于 pricing 配置计算
        """
        from app.core.embedding_pricing import get_embedding_price
        price_per_1k = get_embedding_price(provider, model)
        return (tokens / 1000) * price_per_1k
