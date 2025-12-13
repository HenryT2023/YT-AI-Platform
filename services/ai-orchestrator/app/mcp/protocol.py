"""
MCP 协议定义

定义 MCP 工具调用的标准格式
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum


class MCPToolStatus(str, Enum):
    """工具调用状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class MCPToolCall:
    """MCP 工具调用请求"""

    tool_name: str
    params: Dict[str, Any]
    trace_id: str
    span_id: Optional[str] = None

    # 调用上下文
    tenant_id: Optional[str] = None
    site_id: Optional[str] = None
    session_id: Optional[str] = None
    visitor_id: Optional[str] = None

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "params": self.params,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "session_id": self.session_id,
            "visitor_id": self.visitor_id,
            "metadata": self.metadata,
        }


@dataclass
class MCPToolResult:
    """MCP 工具调用结果"""

    tool_name: str
    status: MCPToolStatus
    trace_id: str
    span_id: Optional[str] = None

    # 结果数据
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_code: Optional[str] = None

    # 执行信息
    duration_ms: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # 证据链（如果工具返回了证据）
    evidence_ids: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.status == MCPToolStatus.SUCCESS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status.value,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "result": self.result,
            "error": self.error,
            "error_code": self.error_code,
            "duration_ms": self.duration_ms,
            "evidence_ids": self.evidence_ids,
        }

    @classmethod
    def from_api_response(cls, response: Dict[str, Any]) -> "MCPToolResult":
        """从 API 响应构建结果"""
        return cls(
            tool_name=response.get("tool_name", ""),
            status=MCPToolStatus.SUCCESS if response.get("success") else MCPToolStatus.FAILED,
            trace_id=response.get("trace_id", ""),
            span_id=response.get("span_id"),
            result=response.get("result"),
            error=response.get("error"),
            error_code=response.get("error_code"),
            duration_ms=response.get("duration_ms"),
            evidence_ids=cls._extract_evidence_ids(response.get("result")),
        )

    @staticmethod
    def _extract_evidence_ids(result: Optional[Dict[str, Any]]) -> List[str]:
        """从结果中提取证据 ID"""
        if not result:
            return []

        evidence_ids = []

        # 从 knowledge.search 结果提取
        if "results" in result:
            for item in result["results"]:
                if "id" in item:
                    evidence_ids.append(item["id"])

        return evidence_ids


@dataclass
class MCPToolDefinition:
    """MCP 工具定义（从 core-backend 获取）"""

    name: str
    description: str
    version: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    category: str
    tags: List[str]
    requires_evidence: bool
    ai_callable: bool

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPToolDefinition":
        return cls(
            name=data["name"],
            description=data["description"],
            version=data.get("version", "1.0.0"),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
            category=data.get("category", "general"),
            tags=data.get("tags", []),
            requires_evidence=data.get("requires_evidence", False),
            ai_callable=data.get("ai_callable", True),
        )

    def to_openai_function(self) -> Dict[str, Any]:
        """转换为 OpenAI function calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }
