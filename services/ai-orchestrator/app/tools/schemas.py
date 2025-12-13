"""
Tool Client Schema 定义
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolContext(BaseModel):
    """工具调用上下文"""

    tenant_id: str
    site_id: str
    trace_id: str
    span_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    npc_id: Optional[str] = None


class ToolAudit(BaseModel):
    """工具调用审计信息"""

    trace_id: str
    tool_name: str
    status: str
    latency_ms: int
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    request_payload_hash: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ToolCallResult(BaseModel):
    """工具调用结果"""

    success: bool
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    audit: Optional[ToolAudit] = None


class ToolMetadata(BaseModel):
    """工具元数据"""

    name: str
    version: str
    description: str
    category: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    requires_auth: bool = True
    ai_callable: bool = True


class NPCProfile(BaseModel):
    """NPC 人设"""

    npc_id: str
    version: int
    active: bool
    name: str
    display_name: Optional[str] = None
    npc_type: Optional[str] = None
    persona: Dict[str, Any] = Field(default_factory=dict)
    knowledge_domains: List[str] = Field(default_factory=list)
    greeting_templates: List[str] = Field(default_factory=list)
    fallback_responses: List[str] = Field(default_factory=list)
    max_response_length: int = 500
    must_cite_sources: bool = True


class ContentItem(BaseModel):
    """内容条目"""

    id: str
    content_type: str
    title: str
    summary: Optional[str] = None
    body: str
    tags: List[str] = Field(default_factory=list)
    domains: List[str] = Field(default_factory=list)
    credibility_score: float = 1.0
    verified: bool = False


class EvidenceItem(BaseModel):
    """证据条目"""

    id: str
    source_type: str
    source_ref: Optional[str] = None
    title: Optional[str] = None
    excerpt: str
    confidence: float = 1.0
    verified: bool = False
    tags: List[str] = Field(default_factory=list)


class PromptInfo(BaseModel):
    """Prompt 信息"""

    npc_id: str
    prompt_type: str
    prompt_text: str
    version: int
    metadata: Dict[str, Any] = Field(default_factory=dict)
