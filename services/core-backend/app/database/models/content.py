"""
内容模型

带 tenant_id/site_id，支持状态流转
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import AuditMixin, Base, TenantMixin

if TYPE_CHECKING:
    from app.database.models.site import Site


class ContentStatus(str, Enum):
    """内容状态"""
    DRAFT = "draft"           # 草稿
    REVIEW = "review"         # 审核中
    PUBLISHED = "published"   # 已发布
    OFFLINE = "offline"       # 已下线


class ContentType(str, Enum):
    """内容类型"""
    KNOWLEDGE = "knowledge"       # 知识条目
    STORY = "story"               # 故事/传说
    GUIDE = "guide"               # 导览文案
    ANNOUNCEMENT = "announcement" # 公告
    FAQ = "faq"                   # 常见问题


class Content(Base, TenantMixin, AuditMixin):
    """
    内容实体

    统一的内容管理表，支持多种内容类型
    带 tenant_id/site_id
    """

    __tablename__ = "contents"

    # 主键
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    # 内容类型
    content_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # 基本信息
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # 分类与标签
    category: Mapped[Optional[str]] = mapped_column(String(100))
    tags: Mapped[list] = mapped_column(ARRAY(String), server_default="{}", nullable=False)
    domains: Mapped[list] = mapped_column(ARRAY(String), server_default="{}", nullable=False)

    # 来源与可信度（用于知识条目）
    source: Mapped[Optional[str]] = mapped_column(Text)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))
    source_date: Mapped[Optional[datetime]] = mapped_column()
    credibility_score: Mapped[float] = mapped_column(server_default="1.0", nullable=False)

    # 验证状态
    verified: Mapped[bool] = mapped_column(server_default="false", nullable=False)
    verified_by: Mapped[Optional[str]] = mapped_column(String(100))
    verified_at: Mapped[Optional[datetime]] = mapped_column()

    # 向量化信息
    embedding_model: Mapped[Optional[str]] = mapped_column(String(100))
    embedding_id: Mapped[Optional[str]] = mapped_column(String(200))
    embedded_at: Mapped[Optional[datetime]] = mapped_column()

    # 全文搜索
    search_vector: Mapped[Optional[str]] = mapped_column(TSVECTOR)

    # 元数据
    extra_data: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}", nullable=False)

    # 统计
    view_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    citation_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)

    # 状态
    status: Mapped[str] = mapped_column(
        String(20),
        server_default="draft",
        nullable=False,
        index=True,
    )

    # 发布信息
    published_at: Mapped[Optional[datetime]] = mapped_column()
    published_by: Mapped[Optional[str]] = mapped_column(String(100))

    # 排序
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)

    # 关系
    site: Mapped["Site"] = relationship("Site", back_populates="contents")

    def __repr__(self) -> str:
        return f"<Content(id={self.id}, title={self.title[:30]}, status={self.status})>"

    def publish(self, publisher: str) -> None:
        """发布内容"""
        self.status = ContentStatus.PUBLISHED.value
        self.published_at = datetime.utcnow()
        self.published_by = publisher

    def offline(self) -> None:
        """下线内容"""
        self.status = ContentStatus.OFFLINE.value
