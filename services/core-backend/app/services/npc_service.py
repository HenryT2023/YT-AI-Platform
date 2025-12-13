"""
NPC 服务

处理 NPC 相关业务逻辑，包括调用 AI Orchestrator 进行对话
"""

from typing import Any, Optional
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.npc import NPC

logger = get_logger(__name__)


class NPCService:
    """NPC 业务服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_npc(self, npc_id: UUID) -> Optional[NPC]:
        """获取 NPC"""
        result = await self.db.execute(
            select(NPC).where(NPC.id == npc_id, NPC.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_npc_by_name(self, site_id: str, name: str) -> Optional[NPC]:
        """根据名称获取 NPC"""
        result = await self.db.execute(
            select(NPC).where(
                NPC.site_id == site_id,
                NPC.name == name,
                NPC.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def chat_with_npc(
        self,
        npc_id: UUID,
        message: str,
        session_id: str,
        visitor_id: Optional[UUID] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        与 NPC 对话

        调用 AI Orchestrator 服务处理对话
        """
        npc = await self.get_npc(npc_id)
        if not npc:
            raise ValueError(f"NPC not found: {npc_id}")

        # 调用 AI Orchestrator
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{settings.AI_ORCHESTRATOR_URL}/api/v1/chat",
                    json={
                        "npc_id": str(npc_id),
                        "npc_persona": npc.persona,
                        "message": message,
                        "session_id": session_id,
                        "visitor_id": str(visitor_id) if visitor_id else None,
                        "context": context,
                    },
                    headers={"X-API-Key": settings.INTERNAL_API_KEY},
                    timeout=30.0,
                )
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                logger.error(
                    "ai_orchestrator_error",
                    npc_id=str(npc_id),
                    status_code=e.response.status_code,
                )
                # 返回兜底响应
                fallback = npc.fallback_responses or ["抱歉，我现在无法回答这个问题。"]
                return {
                    "content": fallback[0],
                    "npc_id": str(npc_id),
                    "session_id": session_id,
                    "error": True,
                }

            except httpx.RequestError as e:
                logger.error("ai_orchestrator_connection_error", error=str(e))
                fallback = npc.fallback_responses or ["抱歉，系统暂时无法响应。"]
                return {
                    "content": fallback[0],
                    "npc_id": str(npc_id),
                    "session_id": session_id,
                    "error": True,
                }

    async def get_greeting(
        self,
        npc_id: UUID,
        context: Optional[dict[str, Any]] = None,
    ) -> str:
        """获取 NPC 问候语"""
        npc = await self.get_npc(npc_id)
        if not npc:
            return "你好！"

        templates = npc.greeting_templates or []
        if templates:
            # TODO: 根据上下文选择合适的问候语
            return templates[0]
        return "你好！有什么可以帮助你的吗？"
