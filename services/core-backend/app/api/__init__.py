"""
API 路由模块

统一注册所有 API 路由
"""

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    chat,
    sites,
    scenes,
    pois,
    npcs,
    quests,
    quest_progress,
    visitors,
    tenants,
    users,
    knowledge,
    mcp_tools,
    health,
    contents,
    trace,
    tools,
    prompts,
)

router = APIRouter()

# 健康检查
router.include_router(health.router, prefix="/health", tags=["健康检查"])

# 认证
router.include_router(auth.router, prefix="/v1/auth", tags=["认证"])

# 多租户管理
router.include_router(tenants.router, prefix="/v1/tenants", tags=["租户"])
router.include_router(users.router, prefix="/v1/users", tags=["用户"])

# 核心业务
router.include_router(chat.router, prefix="/v1/chat", tags=["对话"])
router.include_router(sites.router, prefix="/v1/sites", tags=["站点"])
router.include_router(scenes.router, prefix="/v1/scenes", tags=["场景"])
router.include_router(pois.router, prefix="/v1/pois", tags=["兴趣点"])
router.include_router(npcs.router, prefix="/v1/npcs", tags=["NPC"])
router.include_router(quests.router, prefix="/v1/quests", tags=["研学任务"])
router.include_router(quest_progress.router, prefix="/v1/quest-progress", tags=["任务进度"])
router.include_router(visitors.router, prefix="/v1/visitors", tags=["游客"])

# 内容与知识库
router.include_router(contents.router, prefix="/v1/contents", tags=["内容"])
router.include_router(knowledge.router, prefix="/v1/knowledge", tags=["知识库"])

# MCP 工具与追踪
router.include_router(mcp_tools.router, prefix="/v1/mcp-tools", tags=["MCP工具"])
router.include_router(trace.router, prefix="/v1/trace", tags=["证据链账本"])

# 工具服务（类 MCP HTTP Tool Server）
router.include_router(tools.router, prefix="/tools", tags=["工具服务"])

# Prompt Registry
router.include_router(prompts.router, prefix="/v1/prompts", tags=["Prompt管理"])
