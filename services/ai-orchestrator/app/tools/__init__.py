"""
Tools 模块

与 core-backend Tool Server 通信
"""

from app.tools.client import ToolClient, get_tool_client, generate_trace_id
from app.tools.resilient_client import (
    ResilientToolClient,
    get_resilient_tool_client,
    ToolConfig,
    ToolPriority,
    ToolCallAudit,
    TOOL_CONFIGS,
)
from app.tools.schemas import (
    ToolContext,
    ToolCallResult,
    ToolMetadata,
    ToolAudit,
    NPCProfile,
    ContentItem,
    EvidenceItem,
    PromptInfo,
)

__all__ = [
    # 原始客户端
    "ToolClient",
    "get_tool_client",
    "generate_trace_id",
    # 弹性客户端
    "ResilientToolClient",
    "get_resilient_tool_client",
    "ToolConfig",
    "ToolPriority",
    "ToolCallAudit",
    "TOOL_CONFIGS",
    # Schemas
    "ToolContext",
    "ToolCallResult",
    "ToolMetadata",
    "ToolAudit",
    "NPCProfile",
    "ContentItem",
    "EvidenceItem",
    "PromptInfo",
]
