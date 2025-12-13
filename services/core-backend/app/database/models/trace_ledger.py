"""
证据链账本模型

记录每次 AI 调用的完整追踪信息
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TenantMixin


class PolicyMode(str, Enum):
    """策略模式"""
    STRICT = "strict"           # 严格模式：必须有验证过的证据
    NORMAL = "normal"           # 正常模式：需要有证据
    RELAXED = "relaxed"         # 宽松模式：允许推测
    FALLBACK = "fallback"       # 兜底模式：使用保守回答


class TraceLedger(Base, TenantMixin):
    """
    证据链账本实体

    记录每次 AI 调用的完整追踪信息，用于：
    1. 审计：谁在什么时候调用了什么
    2. 追溯：AI 回答基于哪些证据
    3. 分析：性能、成本、质量分析
    4. 回放：问题排查和复现

    带 tenant_id/site_id
    """

    __tablename__ = "trace_ledger"

    # 主键
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    # 追踪标识
    trace_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    span_id: Mapped[Optional[str]] = mapped_column(String(100))
    parent_span_id: Mapped[Optional[str]] = mapped_column(String(100))

    # 会话关联
    conversation_id: Mapped[Optional[str]] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        index=True,
    )
    session_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)

    # 调用者信息
    user_id: Mapped[Optional[str]] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    npc_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)

    # 请求信息
    request_type: Mapped[str] = mapped_column(String(50), nullable=False)  # chat/greeting/tool_call
    request_input: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 工具调用记录
    tool_calls: Mapped[dict] = mapped_column(JSONB, server_default="[]", nullable=False)

    # 证据链
    evidence_ids: Mapped[list] = mapped_column(ARRAY(String), server_default="{}", nullable=False)
    evidence_chain: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 策略模式
    policy_mode: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    policy_reason: Mapped[Optional[str]] = mapped_column(String(200))

    # 响应信息
    response_output: Mapped[Optional[dict]] = mapped_column(JSONB)
    response_tokens: Mapped[Optional[int]] = mapped_column(Integer)

    # 模型信息
    model_provider: Mapped[Optional[str]] = mapped_column(String(50))
    model_name: Mapped[Optional[str]] = mapped_column(String(100))
    model_version: Mapped[Optional[str]] = mapped_column(String(50))

    # 性能指标
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float)

    # 质量指标
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)
    guardrail_passed: Mapped[Optional[bool]] = mapped_column()
    guardrail_reason: Mapped[Optional[str]] = mapped_column(String(200))

    # 错误信息
    error: Mapped[Optional[str]] = mapped_column(Text)
    error_code: Mapped[Optional[str]] = mapped_column(String(50))

    # 状态
    status: Mapped[str] = mapped_column(String(20), server_default="success", nullable=False, index=True)

    # 时间
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default="now()", nullable=False)

    # 元数据
    metadata: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    def __repr__(self) -> str:
        return f"<TraceLedger(trace_id={self.trace_id}, policy_mode={self.policy_mode})>"

    def mark_success(
        self,
        response_output: dict,
        latency_ms: int,
        tokens: Optional[int] = None,
    ) -> None:
        """标记成功完成"""
        self.status = "success"
        self.response_output = response_output
        self.latency_ms = latency_ms
        self.total_tokens = tokens
        self.completed_at = datetime.utcnow()

    def mark_failed(self, error: str, error_code: str) -> None:
        """标记失败"""
        self.status = "failed"
        self.error = error
        self.error_code = error_code
        self.completed_at = datetime.utcnow()
