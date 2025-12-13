"""API 路由模块"""

from fastapi import APIRouter

from app.api.v1 import chat, npc, observability, trace

router = APIRouter()

router.include_router(chat.router, prefix="/v1/chat", tags=["对话"])
router.include_router(npc.router, prefix="/v1/npc", tags=["NPC对话"])
router.include_router(observability.router, prefix="/v1", tags=["可观测性"])
router.include_router(trace.router, prefix="/v1", tags=["Trace回放"])
