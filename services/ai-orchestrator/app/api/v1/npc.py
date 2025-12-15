"""
NPC 对话 API

POST /v1/npc/chat - NPC 对话闭环
GET /v1/traces/{trace_id} - 追踪回放
"""

import structlog
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.agent import AgentRuntime, ChatRequest, ChatResponse
from app.tools import get_tool_client, ToolContext
from app.tools.client import generate_trace_id

router = APIRouter()
logger = structlog.get_logger(__name__)


class NPCChatRequest(BaseModel):
    """NPC 对话请求"""

    tenant_id: str = Field(..., description="租户 ID")
    site_id: str = Field(..., description="站点 ID")
    npc_id: str = Field(..., description="NPC ID")
    query: str = Field(..., min_length=1, max_length=1000, description="用户问题")
    user_id: Optional[str] = Field(None, description="用户 ID")
    session_id: Optional[str] = Field(None, description="会话 ID")


@router.post("/chat", response_model=ChatResponse)
async def npc_chat(
    request: NPCChatRequest,
    x_trace_id: Optional[str] = Header(None, alias="X-Trace-ID"),
) -> ChatResponse:
    """
    NPC 对话

    完整流程：
    1. 获取 NPC 人设
    2. 获取 Prompt
    3. 检索证据
    4. 调用 LLM 生成
    5. 输出校验
    6. 记录事件 + 写入 trace_ledger
    7. 返回响应

    响应格式（Agent Output Protocol）：
    - trace_id: 追踪 ID
    - policy_mode: 策略模式（normal/conservative/refuse）
    - answer_text: 回答文本
    - citations: 引用的证据
    - followup_questions: 后续问题建议
    """
    trace_id = x_trace_id or generate_trace_id()

    log = logger.bind(
        trace_id=trace_id,
        npc_id=request.npc_id,
        tenant_id=request.tenant_id,
    )
    log.info("npc_chat_request", query=request.query[:50])

    # 构建内部请求
    chat_request = ChatRequest(
        tenant_id=request.tenant_id,
        site_id=request.site_id,
        npc_id=request.npc_id,
        query=request.query,
        user_id=request.user_id,
        session_id=request.session_id,
        trace_id=trace_id,
    )

    # 执行对话
    runtime = AgentRuntime()
    response = await runtime.chat(chat_request)

    return response


@router.get("/traces/{trace_id}")
async def get_trace(
    trace_id: str,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_site_id: str = Header(..., alias="X-Site-ID"),
    include_session: bool = False,
):
    """
    获取追踪记录（回放接口）

    从 core-backend 获取 trace_ledger 记录

    Args:
        trace_id: 追踪 ID
        include_session: 是否包含会话最近消息摘要
    """
    log = logger.bind(trace_id=trace_id)
    log.info("get_trace_request", include_session=include_session)

    ctx = ToolContext(
        tenant_id=x_tenant_id,
        site_id=x_site_id,
        trace_id=trace_id,
    )

    tool_client = get_tool_client()
    trace = await tool_client.get_trace(trace_id, ctx)

    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace not found: {trace_id}",
        )

    # 如果请求包含会话摘要
    if include_session and trace.get("session_id"):
        try:
            from app.memory import get_session_memory

            memory = await get_session_memory()
            session_summary = await memory.get_session_summary(
                tenant_id=x_tenant_id,
                site_id=x_site_id,
                session_id=trace["session_id"],
                max_messages=5,
            )
            trace["session_summary"] = session_summary
        except Exception as e:
            log.warning("get_session_summary_failed", error=str(e))

    return trace


@router.delete("/sessions/{session_id}")
async def clear_session(
    session_id: str,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_site_id: str = Header(..., alias="X-Site-ID"),
    npc_id: Optional[str] = Query(default=None, description="NPC ID（可选，指定则只清空该 NPC 的记忆）"),
):
    """
    清空会话记忆

    用于用户主动清除对话历史

    Args:
        npc_id: 如果指定，只清空该 NPC 的记忆；否则清空整个 session
    """
    log = logger.bind(session_id=session_id, npc_id=npc_id)
    log.info("clear_session_request")

    try:
        from app.memory import get_session_memory

        memory = await get_session_memory()
        success = await memory.clear_session(
            tenant_id=x_tenant_id,
            site_id=x_site_id,
            session_id=session_id,
            npc_id=npc_id,
        )

        return {"success": success, "session_id": session_id, "npc_id": npc_id}

    except Exception as e:
        log.error("clear_session_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear session: {str(e)}",
        )


@router.get("/sessions/{session_id}")
async def get_session_summary(
    session_id: str,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_site_id: str = Header(..., alias="X-Site-ID"),
    npc_id: Optional[str] = Query(default=None, description="NPC ID（可选，指定则只获取该 NPC 的摘要）"),
    max_messages: int = Query(default=10, ge=1, le=50),
):
    """
    获取会话摘要

    返回会话的最近消息和统计信息

    Args:
        npc_id: 如果指定，只获取该 NPC 的摘要
    """
    log = logger.bind(session_id=session_id, npc_id=npc_id)
    log.info("get_session_summary_request")

    try:
        from app.memory import get_session_memory, get_preference_memory

        memory = await get_session_memory()
        pref_memory = await get_preference_memory()

        # 获取短记忆摘要（NPC 隔离）
        summary = await memory.get_session_summary(
            tenant_id=x_tenant_id,
            site_id=x_site_id,
            session_id=session_id,
            npc_id=npc_id,
            max_messages=max_messages,
        )

        # 获取偏好记忆（跨 NPC 共享）
        preference = await pref_memory.get_preference(
            tenant_id=x_tenant_id,
            site_id=x_site_id,
            session_id=session_id,
        )
        summary["preference"] = preference.to_dict()

        return summary

    except Exception as e:
        log.error("get_session_summary_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get session summary: {str(e)}",
        )


@router.put("/sessions/{session_id}/preference")
async def update_preference(
    session_id: str,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_site_id: str = Header(..., alias="X-Site-ID"),
    verbosity: Optional[str] = Query(default=None, description="回答详细程度: brief, normal, detailed"),
    tone: Optional[str] = Query(default=None, description="语气: casual, formal, respectful"),
    interest_tag: Optional[str] = Query(default=None, description="添加兴趣标签"),
):
    """
    更新用户偏好

    偏好记忆跨 NPC 共享，不存储史实内容
    """
    log = logger.bind(session_id=session_id)
    log.info("update_preference_request")

    try:
        from app.memory import get_preference_memory

        pref_memory = await get_preference_memory()

        # 获取当前偏好
        preference = await pref_memory.get_preference(
            tenant_id=x_tenant_id,
            site_id=x_site_id,
            session_id=session_id,
        )

        # 更新字段
        if verbosity and verbosity in ["brief", "normal", "detailed"]:
            preference.verbosity = verbosity
        if tone and tone in ["casual", "formal", "respectful"]:
            preference.tone = tone

        # 保存更新
        success = await pref_memory.update_preference(
            tenant_id=x_tenant_id,
            site_id=x_site_id,
            session_id=session_id,
            preference=preference,
        )

        # 添加兴趣标签
        if interest_tag:
            await pref_memory.add_interest_tag(
                tenant_id=x_tenant_id,
                site_id=x_site_id,
                session_id=session_id,
                tag=interest_tag,
            )

        return {"success": success, "preference": preference.to_dict()}

    except Exception as e:
        log.error("update_preference_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update preference: {str(e)}",
        )
