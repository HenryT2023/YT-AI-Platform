"""
用户反馈模型

记录用户对 AI 回答的纠错和评价

v2 改进：
- 新增 severity 字段
- 新增 suggested_fix 字段
- 新增 resolved_by_content_id / resolved_by_evidence_id
- 支持纠错闭环工作流
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TenantMixin


class FeedbackType(str, Enum):
    """反馈类型"""
    CORRECTION = "correction"     # 纠错
    FACT_ERROR = "fact_error"     # 事实错误
    MISSING_INFO = "missing_info" # 信息缺失
    RATING = "rating"             # 评分
    SUGGESTION = "suggestion"     # 建议
    COMPLAINT = "complaint"       # 投诉
    PRAISE = "praise"             # 表扬


class FeedbackSeverity(str, Enum):
    """反馈严重程度"""
    LOW = "low"           # 低：小问题
    MEDIUM = "medium"     # 中：需要修正
    HIGH = "high"         # 高：严重错误
    CRITICAL = "critical" # 紧急：必须立即处理


class FeedbackStatus(str, Enum):
    """反馈状态"""
    PENDING = "pending"           # 待处理
    REVIEWING = "reviewing"       # 审核中
    ACCEPTED = "accepted"         # 已采纳
    REJECTED = "rejected"         # 已拒绝
    RESOLVED = "resolved"         # 已解决
    ARCHIVED = "archived"         # 已归档


class UserFeedback(Base, TenantMixin):
    """
    用户反馈实体

    记录用户对 AI 回答的反馈
    带 tenant_id/site_id
    """

    __tablename__ = "user_feedbacks"

    # 主键
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    # 关联信息
    trace_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        index=True,
    )
    message_id: Mapped[Optional[str]] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("messages.id", ondelete="SET NULL"),
        index=True,
    )

    # 反馈者
    user_id: Mapped[Optional[str]] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # 反馈类型
    feedback_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # 评分（1-5）
    rating: Mapped[Optional[int]] = mapped_column(Integer)

    # 反馈内容
    content: Mapped[Optional[str]] = mapped_column(Text)

    # 严重程度
    severity: Mapped[str] = mapped_column(String(20), server_default="medium", nullable=False, index=True)

    # 纠错信息
    original_response: Mapped[Optional[str]] = mapped_column(Text)
    corrected_response: Mapped[Optional[str]] = mapped_column(Text)
    correction_reason: Mapped[Optional[str]] = mapped_column(Text)
    suggested_fix: Mapped[Optional[str]] = mapped_column(Text)  # 用户建议的修正

    # 标签
    tags: Mapped[list] = mapped_column(ARRAY(String), server_default="{}", nullable=False)

    # 处理信息
    status: Mapped[str] = mapped_column(String(20), server_default="pending", nullable=False, index=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column()
    review_notes: Mapped[Optional[str]] = mapped_column(Text)

    # 解决关联（绑定修订版本）
    resolved_by_content_id: Mapped[Optional[str]] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("contents.id", ondelete="SET NULL"),
        index=True,
    )
    resolved_by_evidence_id: Mapped[Optional[str]] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("evidences.id", ondelete="SET NULL"),
        index=True,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column()
    resolved_by: Mapped[Optional[str]] = mapped_column(String(100))
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text)

    # 是否已应用到知识库
    applied_to_knowledge: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    applied_at: Mapped[Optional[datetime]] = mapped_column()

    # 元数据
    metadata: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 时间
    created_at: Mapped[datetime] = mapped_column(server_default="now()", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default="now()", onupdate="now()", nullable=False)

    def __repr__(self) -> str:
        return f"<UserFeedback(id={self.id}, type={self.feedback_type}, status={self.status})>"

    def accept(self, reviewer: str, notes: Optional[str] = None) -> None:
        """采纳反馈"""
        self.status = FeedbackStatus.ACCEPTED.value
        self.reviewed_by = reviewer
        self.reviewed_at = datetime.utcnow()
        self.review_notes = notes

    def reject(self, reviewer: str, notes: Optional[str] = None) -> None:
        """拒绝反馈"""
        self.status = FeedbackStatus.REJECTED.value
        self.reviewed_by = reviewer
        self.reviewed_at = datetime.utcnow()
        self.review_notes = notes

    def resolve(
        self,
        resolver: str,
        notes: Optional[str] = None,
        content_id: Optional[str] = None,
        evidence_id: Optional[str] = None,
    ) -> None:
        """解决反馈（绑定修订版本）"""
        self.status = FeedbackStatus.RESOLVED.value
        self.resolved_by = resolver
        self.resolved_at = datetime.utcnow()
        self.resolution_notes = notes
        if content_id:
            self.resolved_by_content_id = content_id
        if evidence_id:
            self.resolved_by_evidence_id = evidence_id

    def archive(self) -> None:
        """归档反馈"""
        self.status = FeedbackStatus.ARCHIVED.value
