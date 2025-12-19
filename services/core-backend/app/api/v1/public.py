"""
Public Read API

无需鉴权的只读 API，用于 visitor-h5 获取场景数据

P0.5 稳定性保证：
- 只读，不做鉴权
- 异常返回空数组，不抛 500

v0.2-1 新增：
- Quest 提交 API
- Quest 进度查询 API
"""

import structlog
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Path, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.engine import get_db
from app.database.models.npc_profile import NPCProfile
from app.database.models.content import Content
from app.database.models.quest import Quest, QuestStep
from app.database.models.quest_submission import QuestSubmission
from app.core.redis_client import get_redis, QuestSubmitRateLimiter

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
# Quest Submission Schemas (v0.2-1)
# ============================================================

class QuestSubmitRequest(BaseModel):
    """Quest 提交请求"""
    tenant_id: str = Field(..., min_length=1, max_length=50)
    site_id: str = Field(..., min_length=1, max_length=50)
    session_id: str = Field(..., min_length=8, max_length=100, description="会话 ID，长度 8-100")
    proof_type: str = Field(default="text", max_length=50)
    proof_payload: dict = Field(default_factory=dict)
    
    @field_validator("proof_payload")
    @classmethod
    def validate_proof_payload(cls, v: dict) -> dict:
        # 限制 answer 长度
        if "answer" in v and isinstance(v["answer"], str):
            if len(v["answer"]) > 500:
                raise ValueError("answer 长度不能超过 500 字符")
        return v


class QuestSubmitResponse(BaseModel):
    """Quest 提交响应"""
    submission_id: str
    status: str
    created_at: datetime


class QuestSubmissionItem(BaseModel):
    """Quest 提交记录"""
    submission_id: str
    quest_id: str
    proof_type: str
    proof_payload: dict
    status: str
    # v0.2.2 审核字段
    review_status: str = "pending"
    review_comment: Optional[str] = None
    created_at: datetime


class QuestProgressResponse(BaseModel):
    """Quest 进度响应"""
    completed_quest_ids: List[str] = Field(default_factory=list, description="已通过审核的任务 ID")
    submissions: List[QuestSubmissionItem] = Field(default_factory=list)


# ============================================================
# 防刷配置
# ============================================================

RATE_LIMIT_WINDOW_SECONDS = 60  # 1 分钟窗口
RATE_LIMIT_MAX_SUBMISSIONS = 3  # 每个 session_id+quest_id 每分钟最多 3 次


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


# ============================================================
# Quest Submission API (v0.2-1, v0.2.1 稳定化)
# ============================================================

@router.post("/quests/{quest_id}/submit", response_model=QuestSubmitResponse)
async def submit_quest(
    quest_id: str = Path(..., description="任务 ID"),
    request: QuestSubmitRequest = ...,
    db: AsyncSession = Depends(get_db),
) -> QuestSubmitResponse:
    """
    提交任务 proof
    
    v0.2.1 稳定化：
    - quest_id 存在性校验（400 if not found）
    - Redis 防刷（429 if rate limited）
    - 时间统一为 DB now()，timezone-aware
    
    限制：
    - session_id 必填且长度 8-100
    - proof_payload.answer 长度限制 500
    - 每个 session_id+quest_id 每 60 秒最多提交 3 次
    """
    log = logger.bind(
        tenant_id=request.tenant_id,
        site_id=request.site_id,
        session_id=request.session_id,
        quest_id=quest_id,
    )
    
    # ========================================
    # Step 1: quest_id 存在性校验
    # quest_id 可能是 config.quest_id 或 name
    # ========================================
    try:
        # 查询所有符合条件的 Quest，检查 quest_id 是否匹配
        quest_stmt = select(Quest).where(
            Quest.tenant_id == request.tenant_id,
            Quest.site_id == request.site_id,
            Quest.status == "active",
            Quest.deleted_at.is_(None),
        )
        quest_result = await db.execute(quest_stmt)
        quests = quest_result.scalars().all()
        
        # 检查 quest_id 是否匹配任何 Quest
        quest_exists = any(
            (q.config.get("quest_id", q.name) if q.config else q.name) == quest_id
            for q in quests
        )
        
        if not quest_exists:
            log.warning("quest_not_found", quest_id=quest_id)
            raise HTTPException(
                status_code=400,
                detail=f"任务不存在: {quest_id}"
            )
    except HTTPException:
        raise
    except Exception as e:
        log.error("quest_check_error", error=str(e))
        raise HTTPException(
            status_code=400,
            detail=f"任务校验失败: {quest_id}"
        )
    
    # ========================================
    # Step 2: Redis 防刷检查
    # ========================================
    try:
        redis_client = await get_redis()
        rate_limiter = QuestSubmitRateLimiter(
            redis_client,
            window_seconds=RATE_LIMIT_WINDOW_SECONDS,
            max_submissions=RATE_LIMIT_MAX_SUBMISSIONS,
        )
        
        is_allowed, current_count, remaining_seconds = await rate_limiter.check_and_increment(
            tenant_id=request.tenant_id,
            site_id=request.site_id,
            session_id=request.session_id,
            quest_id=quest_id,
        )
        
        if not is_allowed:
            log.warning(
                "quest_submit_rate_limited",
                current_count=current_count,
                remaining_seconds=remaining_seconds,
            )
            raise HTTPException(
                status_code=429,
                detail=f"提交过于频繁，请 {remaining_seconds} 秒后重试",
                headers={"Retry-After": str(remaining_seconds)},
            )
    except HTTPException:
        raise
    except Exception as e:
        # Redis 异常不阻塞提交，降级为无防刷
        log.warning("redis_rate_limit_error", error=str(e))
    
    # ========================================
    # Step 3: 创建提交记录
    # ========================================
    try:
        submission = QuestSubmission(
            tenant_id=request.tenant_id,
            site_id=request.site_id,
            session_id=request.session_id,
            quest_id=quest_id,
            proof_type=request.proof_type,
            proof_payload=request.proof_payload,
            status="submitted",
            # created_at/updated_at 由 DB server_default=now() 自动设置
        )
        
        db.add(submission)
        await db.commit()
        await db.refresh(submission)
        
        log.info("quest_submitted", submission_id=submission.id)
        
        return QuestSubmitResponse(
            submission_id=submission.id,
            status=submission.status,
            created_at=submission.created_at,
        )
        
    except Exception as e:
        log.error("quest_submit_db_error", error=str(e))
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail="提交保存失败，请稍后重试"
        )


@router.get("/quests/progress", response_model=QuestProgressResponse)
async def get_quest_progress(
    tenant_id: str = Query(..., description="租户 ID"),
    site_id: str = Query(..., description="站点 ID"),
    session_id: str = Query(..., min_length=8, max_length=100, description="会话 ID"),
    db: AsyncSession = Depends(get_db),
) -> QuestProgressResponse:
    """
    获取任务进度
    
    返回该 session 的所有提交记录和已完成的任务 ID 列表
    """
    log = logger.bind(tenant_id=tenant_id, site_id=site_id, session_id=session_id)
    
    try:
        # 查询该 session 的所有提交记录
        stmt = select(QuestSubmission).where(
            QuestSubmission.tenant_id == tenant_id,
            QuestSubmission.site_id == site_id,
            QuestSubmission.session_id == session_id,
        ).order_by(QuestSubmission.created_at.desc())
        
        result = await db.execute(stmt)
        submissions = result.scalars().all()
        
        # v0.2.2: 使用 review_status 判断完成状态
        # approved → 视为完成
        completed_quest_ids = list(set(
            s.quest_id for s in submissions if s.review_status == "approved"
        ))
        
        submission_items = [
            QuestSubmissionItem(
                submission_id=s.id,
                quest_id=s.quest_id,
                proof_type=s.proof_type,
                proof_payload=s.proof_payload,
                status=s.status,
                review_status=s.review_status,
                review_comment=s.review_comment if s.review_status == "rejected" else None,
                created_at=s.created_at,
            )
            for s in submissions
        ]
        
        log.info("quest_progress_fetched", submission_count=len(submissions))
        
        return QuestProgressResponse(
            completed_quest_ids=completed_quest_ids,
            submissions=submission_items,
        )
        
    except Exception as e:
        log.error("quest_progress_error", error=str(e))
        return QuestProgressResponse()
