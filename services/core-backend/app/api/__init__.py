"""
API 路由模块

统一注册所有 API 路由
"""

from fastapi import APIRouter

from app.api.v1 import (
    achievements,
    solar_terms,
    iot_devices,
    recommendations,
    auth,
    chat,
    sites,
    scenes,
    pois,
    npcs,
    quests,
    quest_progress,
    quest_submissions,
    visitors,
    visitor_profiles,
    tenants,
    users,
    knowledge,
    mcp_tools,
    health,
    contents,
    trace,
    tools,
    prompts,
    feedback,
    vector_coverage,
    embedding_usage,
    experiments,
    policies,
    releases,
    runtime_config,
    alerts,
    public,
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
router.include_router(quest_submissions.router, prefix="/v1/admin/quest-submissions", tags=["任务提交管理"])
router.include_router(visitors.router, prefix="/v1/visitors", tags=["游客"])
router.include_router(visitor_profiles.router, prefix="/v1", tags=["游客画像"])
router.include_router(achievements.router, prefix="/v1", tags=["成就体系"])

# 节气与农耕知识
router.include_router(solar_terms.router, prefix="/v1", tags=["节气农耕"])

# IoT 设备管理
router.include_router(iot_devices.router, prefix="/v1", tags=["IoT设备"])

# 推荐与上下文
router.include_router(recommendations.router, prefix="/v1", tags=["智能推荐"])

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

# 用户反馈
router.include_router(feedback.router, prefix="/v1", tags=["用户反馈"])

# 向量覆盖率
router.include_router(vector_coverage.router, prefix="/v1", tags=["向量检索"])

# Embedding 使用统计
router.include_router(embedding_usage.router, prefix="/v1", tags=["Embedding监控"])

# A/B 实验
router.include_router(experiments.router, prefix="/v1", tags=["A/B实验"])

# 策略管理
router.include_router(policies.router, prefix="/v1/policies", tags=["策略管理"])

# Release 发布包
router.include_router(releases.router, prefix="/v1/releases", tags=["发布包"])

# 运行态配置
router.include_router(runtime_config.router, prefix="/v1/runtime", tags=["运行态配置"])

# 告警评估
router.include_router(alerts.router, prefix="/v1", tags=["告警监控"])

# Public API（无需鉴权）
router.include_router(public.router, prefix="/v1", tags=["公开接口"])
