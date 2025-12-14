"""
MCP 工具调用日志模型

ToolCallLog 记录所有 MCP 工具调用，用于审计、回放、调试
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text, Integer, Float
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ToolCallStatus:
    """工具调用状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class ToolCallLog(Base, TimestampMixin):
    """工具调用日志实体"""

    __tablename__ = "tool_call_logs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # 追踪标识
    trace_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    span_id: Mapped[Optional[str]] = mapped_column(String(100))
    parent_span_id: Mapped[Optional[str]] = mapped_column(String(100))

    # 多租户隔离
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tenants.id"), nullable=False)
    site_id: Mapped[str] = mapped_column(String(50), ForeignKey("sites.id"), nullable=False)

    # 调用者信息
    caller_service: Mapped[str] = mapped_column(String(100), nullable=False)  # ai-orchestrator
    caller_session_id: Mapped[Optional[str]] = mapped_column(String(200))
    caller_user_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True))
    caller_visitor_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True))

    # 工具信息
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    tool_version: Mapped[str] = mapped_column(String(20), default="1.0.0")

    # 输入输出
    input_params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    error_code: Mapped[Optional[str]] = mapped_column(String(50))

    # 执行信息
    status: Mapped[str] = mapped_column(String(20), default=ToolCallStatus.PENDING)
    started_at: Mapped[Optional[datetime]] = mapped_column()
    completed_at: Mapped[Optional[datetime]] = mapped_column()
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # 资源消耗
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float)

    # 元数据
    call_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    def __repr__(self) -> str:
        return f"<ToolCallLog(id={self.id}, tool={self.tool_name}, status={self.status})>"

    def mark_success(self, result: dict[str, Any], duration_ms: int) -> None:
        """标记调用成功"""
        self.status = ToolCallStatus.SUCCESS
        self.output_result = result
        self.completed_at = datetime.utcnow()
        self.duration_ms = duration_ms

    def mark_failed(self, error_message: str, error_code: Optional[str] = None) -> None:
        """标记调用失败"""
        self.status = ToolCallStatus.FAILED
        self.error_message = error_message
        self.error_code = error_code
        self.completed_at = datetime.utcnow()
