"""
MCP 工具调用的 Pydantic Schema

用于 API 请求/响应验证
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolCallRequest(BaseModel):
    """工具调用请求"""

    tool_name: str = Field(..., description="工具名称")
    params: Dict[str, Any] = Field(default_factory=dict, description="工具参数")
    session_id: Optional[str] = Field(None, description="会话 ID")


class ToolCallResponse(BaseModel):
    """工具调用响应"""

    success: bool
    tool_name: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    trace_id: str
    span_id: Optional[str] = None
    duration_ms: Optional[int] = None
    evidence_ids: List[str] = Field(default_factory=list)


class ToolDefinition(BaseModel):
    """工具定义"""

    name: str
    description: str
    version: str = "1.0.0"
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    category: str = "general"
    tags: List[str] = Field(default_factory=list)
    requires_evidence: bool = False
    ai_callable: bool = True


class OpenAIFunction(BaseModel):
    """OpenAI function calling 格式"""

    type: str = "function"
    function: Dict[str, Any]


class EvidenceItem(BaseModel):
    """证据条目"""

    id: str
    title: str
    content_snippet: str
    source: Optional[str] = None
    credibility_score: float = 1.0
    verified: bool = False
    knowledge_type: Optional[str] = None


class EvidenceChain(BaseModel):
    """证据链"""

    trace_id: str
    evidence_ids: List[str]
    evidences: List[EvidenceItem] = Field(default_factory=list)
    total_credibility: float = 0.0
    has_verified_evidence: bool = False

    def compute_credibility(self) -> float:
        """计算总体可信度"""
        if not self.evidences:
            return 0.0

        total = sum(e.credibility_score for e in self.evidences)
        self.total_credibility = total / len(self.evidences)

        # 如果有经过验证的证据，提高可信度
        if any(e.verified for e in self.evidences):
            self.has_verified_evidence = True
            self.total_credibility = min(1.0, self.total_credibility * 1.2)

        return self.total_credibility
