"""
API 路由模块

统一注册所有 API 路由
"""

from fastapi import APIRouter

from app.api.v1 import sites, scenes, pois, npcs, quests, visitors, auth, chat, quest_progress

router = APIRouter()

router.include_router(auth.router, prefix="/v1/auth", tags=["认证"])
router.include_router(chat.router, prefix="/v1/chat", tags=["对话"])
router.include_router(sites.router, prefix="/v1/sites", tags=["站点"])
router.include_router(scenes.router, prefix="/v1/scenes", tags=["场景"])
router.include_router(pois.router, prefix="/v1/pois", tags=["兴趣点"])
router.include_router(npcs.router, prefix="/v1/npcs", tags=["NPC"])
router.include_router(quests.router, prefix="/v1/quests", tags=["研学任务"])
router.include_router(quest_progress.router, prefix="/v1/quest-progress", tags=["任务进度"])
router.include_router(visitors.router, prefix="/v1/visitors", tags=["游客"])
