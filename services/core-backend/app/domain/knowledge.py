"""
知识条目模型

Knowledge 代表可被 RAG 检索的知识条目
是证据链（Evidence Chain）的来源
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text, Integer, Float
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuditMixin, Base


class KnowledgeType:
    """知识类型常量"""
    HISTORICAL_FACT = "historical_fact"  # 历史事实
    CULTURAL_HERITAGE = "cultural_heritage"  # 文化遗产
    FARMING_WISDOM = "farming_wisdom"  # 农耕智慧
    ANCESTRAL_TEACHING = "ancestral_teaching"  # 祖训
    LOCAL_CUSTOM = "local_custom"  # 地方习俗
    ARCHITECTURE = "architecture"  # 建筑知识
    GENEALOGY = "genealogy"  # 族谱
    CRAFT = "craft"  # 工艺技术
    SOLAR_TERM = "solar_term"  # 节气知识
    OTHER = "other"


class KnowledgeEntry(Base, AuditMixin):
    """知识条目实体"""

    __tablename__ = "knowledge_entries"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # 多租户隔离
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tenants.id"), nullable=False)
    site_id: Mapped[str] = mapped_column(String(50), ForeignKey("sites.id"), nullable=False)

    # 基本信息
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)

    # 分类
    knowledge_type: Mapped[str] = mapped_column(String(50), default=KnowledgeType.OTHER)
    domains: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # 来源与可信度
    source: Mapped[Optional[str]] = mapped_column(Text)  # 来源描述
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))
    source_date: Mapped[Optional[datetime]] = mapped_column()
    credibility_score: Mapped[float] = mapped_column(Float, default=1.0)  # 0-1 可信度评分
    verified: Mapped[bool] = mapped_column(default=False)  # 是否经过人工验证
    verified_by: Mapped[Optional[str]] = mapped_column(String(100))
    verified_at: Mapped[Optional[datetime]] = mapped_column()

    # 向量化状态
    embedding_model: Mapped[Optional[str]] = mapped_column(String(100))
    embedding_id: Mapped[Optional[str]] = mapped_column(String(200))  # Qdrant point ID
    embedded_at: Mapped[Optional[datetime]] = mapped_column()

    # 全文搜索
    search_vector: Mapped[Optional[str]] = mapped_column(TSVECTOR)

    # 元数据
    metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # 引用计数（被 AI 引用的次数）
    citation_count: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(20), default="active")

    def __repr__(self) -> str:
        return f"<KnowledgeEntry(id={self.id}, title={self.title[:30]}...)>"

    def to_evidence(self) -> dict[str, Any]:
        """转换为证据格式"""
        return {
            "id": str(self.id),
            "title": self.title,
            "content_snippet": self.content[:500] if self.content else "",
            "source": self.source,
            "credibility_score": self.credibility_score,
            "verified": self.verified,
            "knowledge_type": self.knowledge_type,
        }
