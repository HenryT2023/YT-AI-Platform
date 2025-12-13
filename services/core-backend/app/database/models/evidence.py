"""
证据模型

用于证据链追溯
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import AuditMixin, Base, TenantMixin


class EvidenceSourceType(str, Enum):
    """证据来源类型"""
    KNOWLEDGE_BASE = "knowledge_base"     # 知识库
    DOCUMENT = "document"                 # 文档
    ORAL_HISTORY = "oral_history"         # 口述历史
    ARCHIVE = "archive"                   # 档案
    GENEALOGY = "genealogy"               # 族谱
    INSCRIPTION = "inscription"           # 碑刻
    ARTIFACT = "artifact"                 # 文物
    EXTERNAL_API = "external_api"         # 外部 API
    USER_INPUT = "user_input"             # 用户输入
    AI_GENERATED = "ai_generated"         # AI 生成


class Evidence(Base, TenantMixin, AuditMixin):
    """
    证据实体

    记录 NPC 回答所依据的证据来源
    带 tenant_id/site_id
    """

    __tablename__ = "evidences"

    # 主键
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    # 来源类型
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # 来源引用（如 content_id、document_id 等）
    source_ref: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))

    # 内容摘录
    title: Mapped[Optional[str]] = mapped_column(String(500))
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    # 可信度
    confidence: Mapped[float] = mapped_column(Float, server_default="1.0", nullable=False)

    # 验证状态
    verified: Mapped[bool] = mapped_column(server_default="false", nullable=False)
    verified_by: Mapped[Optional[str]] = mapped_column(String(100))
    verified_at: Mapped[Optional[datetime]] = mapped_column()

    # 分类标签
    tags: Mapped[list] = mapped_column(ARRAY(String), server_default="{}", nullable=False)
    domains: Mapped[list] = mapped_column(ARRAY(String), server_default="{}", nullable=False)

    # 元数据
    extra_data: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}", nullable=False)

    # 向量化状态
    vector_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    vector_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # 引用计数
    citation_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)

    # 状态
    status: Mapped[str] = mapped_column(String(20), server_default="active", nullable=False)

    def __repr__(self) -> str:
        return f"<Evidence(id={self.id}, source_type={self.source_type}, confidence={self.confidence})>"

    def to_chain_item(self) -> dict:
        """转换为证据链条目格式"""
        return {
            "id": self.id,
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "title": self.title,
            "excerpt": self.excerpt[:200] if self.excerpt else "",
            "confidence": self.confidence,
            "verified": self.verified,
            "tags": self.tags,
        }
