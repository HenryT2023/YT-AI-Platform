"""
MCP (Model Context Protocol) 模块

提供与 core-backend MCP 工具的交互能力
"""

from app.mcp.protocol import MCPToolCall, MCPToolResult
from app.mcp.tool_client import MCPToolClient
from app.mcp.schemas import ToolCallRequest, ToolCallResponse

__all__ = [
    "MCPToolCall",
    "MCPToolResult",
    "MCPToolClient",
    "ToolCallRequest",
    "ToolCallResponse",
]
