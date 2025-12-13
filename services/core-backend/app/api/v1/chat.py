"""
对话 API

游客与 NPC 对话的入口
"""

from typing import Annotated, Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.db import get_db
from app.services.npc_service import NPCService

router = APIRouter()


class ChatRequest(BaseModel):
    """对话请求"""

    npc_id: UUID
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = Field(None, description="会话 ID，不提供则自动生成")
    visitor_id: Optional[UUID] = None
    context: Optional[dict[str, Any]] = Field(None, description="额外上下文（场景、位置等）")


class ChatResponse(BaseModel):
    """对话响应"""

    content: str
    npc_id: str
    session_id: str
    sources: list[str] = Field(default_factory=list)
    error: bool = False


class GreetingRequest(BaseModel):
    """问候请求"""

    npc_id: UUID
    context: Optional[dict[str, Any]] = None


class GreetingResponse(BaseModel):
    """问候响应"""

    greeting: str
    npc_id: str


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> ChatResponse:
    """
    与 NPC 对话

    发送消息给指定 NPC，获取 AI 生成的回复
    """
    session_id = request.session_id or str(uuid4())
    service = NPCService(db)

    try:
        result = await service.chat_with_npc(
            npc_id=request.npc_id,
            message=request.message,
            session_id=session_id,
            visitor_id=request.visitor_id,
            context=request.context,
        )

        return ChatResponse(
            content=result["content"],
            npc_id=result["npc_id"],
            session_id=result["session_id"],
            sources=result.get("sources", []),
            error=result.get("error", False),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post("/greeting", response_model=GreetingResponse)
async def get_greeting(
    request: GreetingRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[str, Depends(get_current_user)],
) -> GreetingResponse:
    """
    获取 NPC 问候语

    根据 NPC 和上下文返回合适的问候语
    """
    service = NPCService(db)
    greeting = await service.get_greeting(
        npc_id=request.npc_id,
        context=request.context,
    )
    return GreetingResponse(greeting=greeting, npc_id=str(request.npc_id))
