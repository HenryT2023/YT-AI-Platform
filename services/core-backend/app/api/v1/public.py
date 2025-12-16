"""
Public Read API

无需鉴权的只读 API，用于 visitor-h5 获取场景数据

P0.5 稳定性保证：
- 只读，不做鉴权
- 异常返回空数组，不抛 500
"""

import structlog
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.engine import get_db
from app.database.models.npc_profile import NPCProfile
from app.database.models.content import Content
from app.database.models.quest import Quest, QuestStep

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/public", tags=["public"])


# ============================================================
# Response Schemas
# ============================================================

class PublicNPCItem(BaseModel):
    """NPC 公开信息"""
    npc_id: str
    name: str
    display_name: Optional[str] = None
    role: Optional[str] = None
    intro: Optional[str] = Field(None, description="简介")
    avatar_url: Optional[str] = None
    avatar_emoji: Optional[str] = Field(None, description="Emoji 头像")
    color: Optional[str] = Field(None, description="渐变色 class")
    greeting: Optional[str] = Field(None, description="问候语")


class PublicPOIItem(BaseModel):
    """POI 公开信息"""
    poi_id: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    extra: dict = Field(default_factory=dict)


class PublicQuestStepItem(BaseModel):
    """Quest 步骤"""
    step_number: int
    name: str
    description: Optional[str] = None
    step_type: str


class PublicQuestItem(BaseModel):
    """Quest 公开信息"""
    quest_id: str
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    quest_type: Optional[str] = None
    category: Optional[str] = None
    difficulty: Optional[str] = None
    estimated_duration_minutes: Optional[int] = None
    tags: List[str] = Field(default_factory=list)
    rewards: dict = Field(default_factory=dict)
    steps: List[PublicQuestStepItem] = Field(default_factory=list)


# ============================================================
# API Endpoints
# ============================================================

@router.get("/npcs", response_model=List[PublicNPCItem])
async def list_public_npcs(
    tenant_id: str = Query(..., description="租户 ID"),
    site_id: str = Query(..., description="站点 ID"),
    db: AsyncSession = Depends(get_db),
) -> List[PublicNPCItem]:
    """
    获取 NPC 列表（公开）
    
    只返回 active=True 的 NPC
    """
    log = logger.bind(tenant_id=tenant_id, site_id=site_id)
    
    try:
        stmt = select(NPCProfile).where(
            NPCProfile.tenant_id == tenant_id,
            NPCProfile.site_id == site_id,
            NPCProfile.active == True,
            NPCProfile.deleted_at.is_(None),
        ).order_by(NPCProfile.created_at)
        
        result = await db.execute(stmt)
        npcs = result.scalars().all()
        
        items = []
        for npc in npcs:
            # 从 persona.extra 提取前端需要的字段
            extra = npc.persona.get("extra", {}) if npc.persona else {}
            greeting = npc.greeting_templates[0] if npc.greeting_templates else None
            
            items.append(PublicNPCItem(
                npc_id=npc.npc_id,
                name=npc.name,
                display_name=npc.display_name,
                role=npc.role,
                intro=extra.get("intro") or npc.background,
                avatar_url=npc.avatar_url,
                avatar_emoji=extra.get("avatar_emoji"),
                color=extra.get("color"),
                greeting=greeting,
            ))
        
        log.info("public_npcs_list", count=len(items))
        return items
        
    except Exception as e:
        log.error("public_npcs_error", error=str(e))
        return []


@router.get("/pois", response_model=List[PublicPOIItem])
async def list_public_pois(
    tenant_id: str = Query(..., description="租户 ID"),
    site_id: str = Query(..., description="站点 ID"),
    db: AsyncSession = Depends(get_db),
) -> List[PublicPOIItem]:
    """
    获取 POI 列表（公开）
    
    只返回 status=published 的 POI
    """
    log = logger.bind(tenant_id=tenant_id, site_id=site_id)
    
    try:
        stmt = select(Content).where(
            Content.tenant_id == tenant_id,
            Content.site_id == site_id,
            Content.content_type == "poi",
            Content.status == "published",
            Content.deleted_at.is_(None),
        ).order_by(Content.sort_order, Content.created_at)
        
        result = await db.execute(stmt)
        pois = result.scalars().all()
        
        items = []
        for poi in pois:
            items.append(PublicPOIItem(
                poi_id=poi.slug or str(poi.id),
                name=poi.title,
                description=poi.summary or poi.body[:200] if poi.body else None,
                category=poi.category,
                tags=poi.tags or [],
                extra=poi.extra_data or {},
            ))
        
        log.info("public_pois_list", count=len(items))
        return items
        
    except Exception as e:
        log.error("public_pois_error", error=str(e))
        return []


@router.get("/quests", response_model=List[PublicQuestItem])
async def list_public_quests(
    tenant_id: str = Query(..., description="租户 ID"),
    site_id: str = Query(..., description="站点 ID"),
    db: AsyncSession = Depends(get_db),
) -> List[PublicQuestItem]:
    """
    获取 Quest 列表（公开）
    
    只返回 status=active 的 Quest
    """
    log = logger.bind(tenant_id=tenant_id, site_id=site_id)
    
    try:
        stmt = select(Quest).where(
            Quest.tenant_id == tenant_id,
            Quest.site_id == site_id,
            Quest.status == "active",
            Quest.deleted_at.is_(None),
        ).order_by(Quest.sort_order, Quest.created_at)
        
        result = await db.execute(stmt)
        quests = result.scalars().all()
        
        items = []
        for quest in quests:
            # quest.steps 已通过 relationship 加载
            steps = [
                PublicQuestStepItem(
                    step_number=step.step_number,
                    name=step.name,
                    description=step.description,
                    step_type=step.step_type,
                )
                for step in sorted(quest.steps, key=lambda s: s.step_number)
            ]
            
            items.append(PublicQuestItem(
                quest_id=quest.config.get("quest_id", quest.name) if quest.config else quest.name,
                name=quest.name,
                display_name=quest.display_name,
                description=quest.description,
                quest_type=quest.quest_type,
                category=quest.category,
                difficulty=quest.difficulty,
                estimated_duration_minutes=quest.estimated_duration_minutes,
                tags=quest.tags or [],
                rewards=quest.rewards or {},
                steps=steps,
            ))
        
        log.info("public_quests_list", count=len(items))
        return items
        
    except Exception as e:
        log.error("public_quests_error", error=str(e))
        return []
