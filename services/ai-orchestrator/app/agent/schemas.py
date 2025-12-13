"""
Agent Runtime Schema 定义
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PolicyMode(str, Enum):
    """策略模式"""

    NORMAL = "normal"           # 正常模式：有足够证据
    CONSERVATIVE = "conservative"  # 保守模式：证据不足
    REFUSE = "refuse"           # 拒绝模式：敏感话题


class CitationItem(BaseModel):
    """引用条目"""

    evidence_id: str
    title: Optional[str] = None
    source_ref: Optional[str] = None
    excerpt: Optional[str] = None
    confidence: float = 1.0


class ChatRequest(BaseModel):
    """对话请求"""

    tenant_id: str = Field(..., description="租户 ID")
    site_id: str = Field(..., description="站点 ID")
    npc_id: str = Field(..., description="NPC ID")
    query: str = Field(..., description="用户问题")
    user_id: Optional[str] = Field(None, description="用户 ID")
    session_id: Optional[str] = Field(None, description="会话 ID")
    trace_id: Optional[str] = Field(None, description="追踪 ID（可选，不传则自动生成）")


class ChatResponse(BaseModel):
    """
    对话响应

    符合 Agent Output Protocol
    """

    trace_id: str = Field(..., description="追踪 ID")
    session_id: str = Field(..., description="会话 ID（用于多轮对话）")
    policy_mode: PolicyMode = Field(..., description="策略模式")
    answer_text: str = Field(..., description="回答文本")
    citations: List[CitationItem] = Field(default_factory=list, description="引用的证据")
    followup_questions: List[str] = Field(default_factory=list, description="后续问题建议")
    npc_name: Optional[str] = Field(None, description="NPC 名称")
    latency_ms: Optional[int] = Field(None, description="处理延迟（毫秒）")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="响应时间")


class ValidationResult(BaseModel):
    """校验结果"""

    valid: bool
    policy_mode: PolicyMode
    reason: Optional[str] = None
    filtered_text: Optional[str] = None
