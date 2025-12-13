"""
工具服务 Schema 定义

所有工具的输入输出通过 Pydantic v2 校验
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field


class ToolContext(BaseModel):
    """
    工具调用上下文

    必须携带 tenant_id, site_id, trace_id
    """

    tenant_id: str = Field(..., description="租户 ID")
    site_id: str = Field(..., description="站点 ID")
    trace_id: str = Field(..., description="追踪 ID，用于全链路追踪")
    span_id: Optional[str] = Field(None, description="Span ID")
    user_id: Optional[str] = Field(None, description="用户 ID（可选）")
    session_id: Optional[str] = Field(None, description="会话 ID（可选）")
    npc_id: Optional[str] = Field(None, description="NPC ID（可选）")


class ToolCallRequest(BaseModel):
    """工具调用请求"""

    tool_name: str = Field(..., description="工具名称")
    input: Dict[str, Any] = Field(default_factory=dict, description="工具输入参数")
    context: ToolContext = Field(..., description="调用上下文")


class ToolAudit(BaseModel):
    """工具调用审计信息"""

    trace_id: str
    tool_name: str
    status: str  # success / error
    latency_ms: int
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    request_payload_hash: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ToolCallResponse(BaseModel):
    """工具调用响应"""

    success: bool
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    audit: ToolAudit


class ToolParameter(BaseModel):
    """工具参数定义"""

    name: str
    type: str
    description: str
    required: bool = True
    default: Optional[Any] = None
    enum: Optional[List[str]] = None


class ToolMetadata(BaseModel):
    """工具元数据"""

    name: str = Field(..., description="工具名称")
    version: str = Field(..., description="工具版本")
    description: str = Field(..., description="工具描述")
    category: str = Field(..., description="工具分类")
    input_schema: Dict[str, Any] = Field(..., description="输入 JSON Schema")
    output_schema: Dict[str, Any] = Field(..., description="输出 JSON Schema")
    requires_auth: bool = Field(True, description="是否需要认证")
    ai_callable: bool = Field(True, description="是否可被 AI 调用")


class ToolListResponse(BaseModel):
    """工具列表响应"""

    tools: List[ToolMetadata]
    total: int


# ============================================================
# 各工具的输入输出 Schema
# ============================================================

class GetNPCProfileInput(BaseModel):
    """get_npc_profile 输入"""

    npc_id: str = Field(..., description="NPC ID")
    version: Optional[int] = Field(None, description="指定版本号，不填则返回 active 版本")


class GetNPCProfileOutput(BaseModel):
    """get_npc_profile 输出"""

    npc_id: str
    version: int
    active: bool
    name: str
    display_name: Optional[str]
    npc_type: Optional[str]
    persona: Dict[str, Any]
    knowledge_domains: List[str]
    greeting_templates: List[str]
    fallback_responses: List[str]
    max_response_length: int
    must_cite_sources: bool


class SearchContentInput(BaseModel):
    """search_content 输入"""

    query: str = Field(..., description="搜索关键词")
    content_type: Optional[str] = Field(None, description="内容类型过滤")
    tags: Optional[List[str]] = Field(None, description="标签过滤")
    status: Optional[str] = Field("published", description="状态过滤")
    limit: int = Field(10, ge=1, le=50, description="返回数量限制")


class ContentItem(BaseModel):
    """内容条目"""

    id: str
    content_type: str
    title: str
    summary: Optional[str]
    body: str
    tags: List[str]
    domains: List[str]
    credibility_score: float
    verified: bool


class SearchContentOutput(BaseModel):
    """search_content 输出"""

    items: List[ContentItem]
    total: int
    query: str


class GetSiteMapInput(BaseModel):
    """get_site_map 输入"""

    include_pois: bool = Field(True, description="是否包含兴趣点")
    include_routes: bool = Field(False, description="是否包含路线")


class POIItem(BaseModel):
    """兴趣点"""

    id: str
    name: str
    type: str
    location: Optional[Dict[str, float]] = None
    description: Optional[str] = None


class GetSiteMapOutput(BaseModel):
    """get_site_map 输出"""

    site_id: str
    site_name: str
    pois: List[POIItem]
    routes: List[Dict[str, Any]]


class CreateDraftContentInput(BaseModel):
    """create_draft_content 输入"""

    content_type: str = Field(..., description="内容类型")
    title: str = Field(..., description="标题")
    body: str = Field(..., description="正文")
    summary: Optional[str] = Field(None, description="摘要")
    tags: List[str] = Field(default_factory=list, description="标签")
    domains: List[str] = Field(default_factory=list, description="知识领域")
    source: Optional[str] = Field(None, description="来源")


class CreateDraftContentOutput(BaseModel):
    """create_draft_content 输出"""

    content_id: str
    status: str
    created_at: datetime


class LogUserEventInput(BaseModel):
    """log_user_event 输入"""

    event_type: str = Field(..., description="事件类型")
    event_data: Dict[str, Any] = Field(default_factory=dict, description="事件数据")
    user_id: Optional[str] = Field(None, description="用户 ID")
    session_id: Optional[str] = Field(None, description="会话 ID")


class LogUserEventOutput(BaseModel):
    """log_user_event 输出"""

    event_id: str
    logged_at: datetime


class GetPromptActiveInput(BaseModel):
    """get_prompt_active 输入"""

    npc_id: str = Field(..., description="NPC ID")
    prompt_type: str = Field("system", description="Prompt 类型：system/greeting/fallback")


class GetPromptActiveOutput(BaseModel):
    """get_prompt_active 输出"""

    npc_id: str
    prompt_type: str
    prompt_text: str
    version: int
    metadata: Dict[str, Any]


class RetrieveEvidenceInput(BaseModel):
    """retrieve_evidence 输入"""

    query: str = Field(..., description="搜索关键词")
    domains: Optional[List[str]] = Field(None, description="知识领域过滤")
    limit: int = Field(5, ge=1, le=20, description="返回数量限制")
    min_score: float = Field(0.3, ge=0.0, le=1.0, description="最小相似度阈值")
    strategy: str = Field("hybrid", description="检索策略: trgm/qdrant/hybrid")
    use_trgm: bool = Field(True, description="[已废弃] 是否使用 pg_trgm，请使用 strategy")


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
    retrieval_score: Optional[float] = Field(None, description="检索分数")
    trgm_score: Optional[float] = Field(None, description="pg_trgm 分数")
    qdrant_score: Optional[float] = Field(None, description="Qdrant 向量分数")


class RetrieveEvidenceOutput(BaseModel):
    """retrieve_evidence 输出"""

    items: List[EvidenceItem]
    total: int
    query: str
    strategy: str = Field("hybrid", description="检索策略: trgm/qdrant/hybrid")
    search_method: str = Field("trgm", description="[已废弃] 使用 strategy")
    score_distribution: Optional[Dict[str, Any]] = Field(None, description="分数分布统计")


# ============================================================
# 用户反馈工具 Schema
# ============================================================

class SubmitFeedbackInput(BaseModel):
    """submit_feedback 输入"""

    trace_id: Optional[str] = Field(None, description="关联的 trace ID")
    conversation_id: Optional[str] = Field(None, description="关联的会话 ID")
    message_id: Optional[str] = Field(None, description="关联的消息 ID")
    feedback_type: str = Field(
        "correction",
        description="反馈类型: correction/fact_error/missing_info/rating/suggestion/complaint/praise",
    )
    severity: str = Field("medium", description="严重程度: low/medium/high/critical")
    content: str = Field(..., description="反馈内容")
    original_response: Optional[str] = Field(None, description="原始回答")
    suggested_fix: Optional[str] = Field(None, description="建议的修正")
    tags: List[str] = Field(default_factory=list, description="标签")


class SubmitFeedbackOutput(BaseModel):
    """submit_feedback 输出"""

    feedback_id: str
    status: str
    created_at: datetime


class ListFeedbackInput(BaseModel):
    """list_feedback 输入"""

    status: Optional[str] = Field(None, description="状态过滤: pending/reviewing/accepted/rejected/resolved")
    feedback_type: Optional[str] = Field(None, description="类型过滤")
    severity: Optional[str] = Field(None, description="严重程度过滤")
    limit: int = Field(10, ge=1, le=50, description="返回数量限制")


class FeedbackItem(BaseModel):
    """反馈条目"""

    id: str
    trace_id: Optional[str]
    feedback_type: str
    severity: str
    content: Optional[str]
    status: str
    created_at: datetime


class ListFeedbackOutput(BaseModel):
    """list_feedback 输出"""

    items: List[FeedbackItem]
    total: int


# ============================================================
# P23 新增：反馈工单化工具 Schema
# ============================================================

class TriageFeedbackInput(BaseModel):
    """triage_feedback 输入"""

    feedback_id: str = Field(..., description="反馈 ID")
    assignee: Optional[str] = Field(None, description="指定处理人")
    group: Optional[str] = Field(None, description="指定处理组")
    sla_hours: Optional[int] = Field(None, description="SLA 小时数")
    auto_route: bool = Field(True, description="是否使用自动分派规则")


class TriageFeedbackOutput(BaseModel):
    """triage_feedback 输出"""

    feedback_id: str
    status: str
    assignee: Optional[str]
    group: Optional[str]
    sla_due_at: Optional[datetime]


class UpdateFeedbackStatusInput(BaseModel):
    """update_feedback_status 输入"""

    feedback_id: str = Field(..., description="反馈 ID")
    status: str = Field(..., description="目标状态: triaged/in_progress/resolved/closed")
    notes: Optional[str] = Field(None, description="备注")
    resolver: Optional[str] = Field(None, description="解决者（resolved 状态需要）")


class UpdateFeedbackStatusOutput(BaseModel):
    """update_feedback_status 输出"""

    feedback_id: str
    status: str
    updated_at: datetime


class GetFeedbackStatsInput(BaseModel):
    """get_feedback_stats 输入"""

    days: int = Field(30, ge=1, le=365, description="统计天数")


class GetFeedbackStatsOutput(BaseModel):
    """get_feedback_stats 输出"""

    total: int
    overdue_count: int
    resolution_rate: float
    avg_resolution_time_hours: Optional[float]
    backlog_by_status: Dict[str, int]
