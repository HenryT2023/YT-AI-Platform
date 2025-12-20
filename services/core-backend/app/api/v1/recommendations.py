"""
推荐与上下文 API

提供个性化推荐和上下文数据接口
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.engine import get_db
from app.api.deps import TenantContext, get_tenant_context
from app.services.context import ContextService
from app.services.recommendation import RecommendationService

router = APIRouter()


@router.get("/context/{visitor_id}")
async def get_visitor_context(
    visitor_id: UUID,
    location: Optional[str] = Query(None, description="当前位置"),
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
):
    """
    获取游客完整上下文

    用于 AI 编排层构建 Prompt
    """
    tenant_id, site_id = tenant_ctx.tenant_id, tenant_ctx.site_id
    service = ContextService(db)

    context = await service.build_context(
        tenant_id=tenant_id,
        site_id=site_id,
        visitor_id=visitor_id,
        location=location,
    )

    return context


@router.get("/context/{visitor_id}/summary")
async def get_visitor_context_summary(
    visitor_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
):
    """
    获取游客上下文的自然语言摘要

    用于直接注入 NPC Prompt
    """
    tenant_id, site_id = tenant_ctx.tenant_id, tenant_ctx.site_id
    service = ContextService(db)

    summary = await service.get_user_context_summary(
        tenant_id=tenant_id,
        site_id=site_id,
        visitor_id=visitor_id,
    )

    return {"summary": summary}


@router.get("/recommendations/home")
async def get_home_recommendations(
    visitor_id: Optional[UUID] = Query(None, description="游客 ID（可选）"),
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
):
    """
    获取首页聚合推荐数据

    包含：
    - 今日节气贴士
    - 推荐任务
    - 成就进度提示
    - 推荐话题
    - 个性化问候语
    """
    tenant_id, site_id = tenant_ctx.tenant_id, tenant_ctx.site_id
    service = RecommendationService(db)

    recommendations = await service.get_home_recommendations(
        tenant_id=tenant_id,
        site_id=site_id,
        visitor_id=visitor_id,
    )

    return recommendations


@router.get("/recommendations/quests")
async def get_quest_recommendations(
    visitor_id: Optional[UUID] = Query(None, description="游客 ID（可选）"),
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
):
    """
    获取推荐任务列表
    """
    tenant_id, site_id = tenant_ctx.tenant_id, tenant_ctx.site_id
    service = RecommendationService(db)

    # 构建上下文获取用户信息
    context_service = ContextService(db)
    context = await context_service.build_context(
        tenant_id=tenant_id,
        site_id=site_id,
        visitor_id=visitor_id,
    )

    quests = await service._get_recommended_quests(
        tenant_id=tenant_id,
        site_id=site_id,
        visitor_id=visitor_id,
        user_context=context["user"],
    )

    return {"items": quests[:limit], "total": len(quests)}


@router.get("/recommendations/topics")
async def get_topic_recommendations(
    visitor_id: Optional[UUID] = Query(None, description="游客 ID（可选）"),
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
):
    """
    获取推荐对话话题
    """
    tenant_id, site_id = tenant_ctx.tenant_id, tenant_ctx.site_id

    context_service = ContextService(db)
    context = await context_service.build_context(
        tenant_id=tenant_id,
        site_id=site_id,
        visitor_id=visitor_id,
    )

    service = RecommendationService(db)
    topics = await service._get_recommended_topics(
        user_context=context["user"],
        env_context=context["environment"],
    )

    return {"topics": topics}
