"""
对话 API

处理 NPC 对话请求
"""

from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.orchestrator import NPCOrchestrator

router = APIRouter()
logger = get_logger(__name__)

# 全局编排器实例
orchestrator = NPCOrchestrator()


class ChatRequest(BaseModel):
    """对话请求"""

    npc_id: UUID
    npc_persona: dict[str, Any] = Field(..., description="NPC 人设配置")
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = Field(None, description="会话 ID，不提供则自动生成")
    visitor_id: Optional[UUID] = None
    context: Optional[dict[str, Any]] = Field(None, description="额外上下文")


class ChatResponse(BaseModel):
    """对话响应"""

    content: str
    npc_id: str
    session_id: str
    sources: list[str] = Field(default_factory=list)
    guardrail_passed: bool = True
    tokens_used: Optional[int] = None


class GreetingRequest(BaseModel):
    """问候请求"""

    npc_persona: dict[str, Any]
    context: Optional[dict[str, Any]] = None


class GreetingResponse(BaseModel):
    """问候响应"""

    greeting: str


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    NPC 对话接口

    处理用户与 NPC 的对话请求，返回 NPC 的回复
    """
    session_id = request.session_id or str(uuid4())

    try:
        result = await orchestrator.chat(
            npc_id=request.npc_id,
            npc_persona=request.npc_persona,
            user_message=request.message,
            session_id=session_id,
            visitor_id=request.visitor_id,
            context=request.context,
        )

        return ChatResponse(
            content=result["content"],
            npc_id=result["npc_id"],
            session_id=result["session_id"],
            sources=result.get("sources", []),
            guardrail_passed=result.get("guardrail_passed", True),
            tokens_used=result.get("tokens_used"),
        )

    except Exception as e:
        logger.error("chat_error", error=str(e), npc_id=str(request.npc_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="对话处理失败，请稍后重试",
        )


@router.post("/greeting", response_model=GreetingResponse)
async def get_greeting(request: GreetingRequest) -> GreetingResponse:
    """
    获取 NPC 问候语

    根据 NPC 人设和上下文返回合适的问候语
    """
    greeting = await orchestrator.get_greeting(
        npc_persona=request.npc_persona,
        context=request.context,
    )
    return GreetingResponse(greeting=greeting)
