"""
工具服务模块

提供类 MCP 的 HTTP Tool Server，暴露业务能力给 ai-orchestrator 调用

核心接口：
- POST /tools/list: 返回工具元数据
- POST /tools/call: 执行工具调用

所有工具调用：
- 必须携带 tenant_id, site_id, trace_id
- 输入输出通过 Pydantic v2 schema 校验
- 写入 trace_ledger 审计
"""

from app.tools.registry import ToolRegistry, get_tool_registry
from app.tools.executor import ToolExecutor
from app.tools.schemas import (
    ToolContext,
    ToolCallRequest,
    ToolCallResponse,
    ToolMetadata,
    ToolListResponse,
)

__all__ = [
    "ToolRegistry",
    "get_tool_registry",
    "ToolExecutor",
    "ToolContext",
    "ToolCallRequest",
    "ToolCallResponse",
    "ToolMetadata",
    "ToolListResponse",
]
