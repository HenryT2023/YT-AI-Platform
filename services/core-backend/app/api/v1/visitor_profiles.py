"""
游客画像 API

提供游客画像的 CRUD 操作、标签管理、打卡记录、交互统计等功能
"""

from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.visitor_profile import (
    VisitorProfileCreate,
    VisitorProfileUpdate,
    VisitorProfileResponse,
    VisitorProfileListResponse,
    VisitorTagCreate,
    VisitorTagUpdate,
    VisitorTagResponse,
    VisitorCheckInCreate,
    VisitorCheckInResponse,
    VisitorInteractionCreate,
    VisitorInteractionUpdate,
    VisitorInteractionResponse,
    ProfileAnalytics,
)
from app.core.rbac import ViewerOrAbove
from app.core.tenant_scope import RequiredScope
from app.database.models import (
    VisitorProfile,
    VisitorTag,
    VisitorCheckIn,
    VisitorInteraction,
)
from app.services.achievement_service import check_achievements_for_user
from app.database.models import User
from app.db.session import get_db

router = APIRouter(prefix="/visitor-profiles", tags=["visitor-profiles"])


# ============ VisitorProfile CRUD ============

@router.post("", response_model=VisitorProfileResponse, status_code=201)
async def create_visitor_profile(
    profile: VisitorProfileCreate,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """创建游客画像"""
    
    # 检查用户是否存在
    user_result = await db.execute(
        select(User).where(
            User.id == str(profile.user_id),
            User.tenant_id == scope.tenant_id
        )
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    # 检查是否已有画像
    existing = await db.execute(
        select(VisitorProfile).where(
            VisitorProfile.user_id == profile.user_id,
            VisitorProfile.tenant_id == scope.tenant_id,
            VisitorProfile.site_id == scope.site_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该用户已有画像")
    
    # 创建画像
    db_profile = VisitorProfile(
        tenant_id=scope.tenant_id,
        site_id=scope.site_id,
        user_id=profile.user_id,
        activity_level=profile.activity_level,
        engagement_score=profile.engagement_score,
        learning_style=profile.learning_style,
        notes=profile.notes,
    )
    
    db.add(db_profile)
    await db.commit()
    await db.refresh(db_profile)
    
    return db_profile


@router.get("", response_model=VisitorProfileListResponse)
async def list_visitor_profiles(
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    activity_level: Optional[str] = Query(None, description="活跃度过滤"),
    min_engagement: Optional[float] = Query(None, ge=0, le=100, description="最小参与度"),
):
    """查询游客画像列表"""
    
    # 构建查询条件
    conditions = [
        VisitorProfile.tenant_id == scope.tenant_id,
        VisitorProfile.site_id == scope.site_id,
    ]
    
    if activity_level:
        conditions.append(VisitorProfile.activity_level == activity_level)
    if min_engagement is not None:
        conditions.append(VisitorProfile.engagement_score >= min_engagement)
    
    # 查询总数
    count_result = await db.execute(
        select(func.count(VisitorProfile.id)).where(and_(*conditions))
    )
    total = count_result.scalar_one()
    
    # 查询列表
    offset = (page - 1) * page_size
    result = await db.execute(
        select(VisitorProfile)
        .where(and_(*conditions))
        .order_by(VisitorProfile.last_active_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    profiles = result.scalars().all()
    
    return VisitorProfileListResponse(
        items=profiles,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{profile_id}", response_model=VisitorProfileResponse)
async def get_visitor_profile(
    profile_id: UUID,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """获取游客画像详情"""
    
    result = await db.execute(
        select(VisitorProfile).where(
            VisitorProfile.id == profile_id,
            VisitorProfile.tenant_id == scope.tenant_id,
            VisitorProfile.site_id == scope.site_id
        )
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail="画像不存在")
    
    return profile


@router.patch("/{profile_id}", response_model=VisitorProfileResponse)
async def update_visitor_profile(
    profile_id: UUID,
    profile_update: VisitorProfileUpdate,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """更新游客画像"""
    
    result = await db.execute(
        select(VisitorProfile).where(
            VisitorProfile.id == profile_id,
            VisitorProfile.tenant_id == scope.tenant_id,
            VisitorProfile.site_id == scope.site_id
        )
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail="画像不存在")
    
    # 更新字段
    update_data = profile_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(profile, field, value)
    
    await db.commit()
    await db.refresh(profile)
    
    return profile


@router.delete("/{profile_id}", status_code=204)
async def delete_visitor_profile(
    profile_id: UUID,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """删除游客画像"""
    
    result = await db.execute(
        select(VisitorProfile).where(
            VisitorProfile.id == profile_id,
            VisitorProfile.tenant_id == scope.tenant_id,
            VisitorProfile.site_id == scope.site_id
        )
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail="画像不存在")
    
    await db.delete(profile)
    await db.commit()


# ============ VisitorTag 管理 ============

@router.post("/{profile_id}/tags", response_model=VisitorTagResponse, status_code=201)
async def add_visitor_tag(
    profile_id: UUID,
    tag: VisitorTagCreate,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """添加游客标签"""
    
    # 验证画像存在
    profile_result = await db.execute(
        select(VisitorProfile).where(
            VisitorProfile.id == profile_id,
            VisitorProfile.tenant_id == scope.tenant_id,
            VisitorProfile.site_id == scope.site_id
        )
    )
    if not profile_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="画像不存在")
    
    # 创建标签
    db_tag = VisitorTag(
        tenant_id=scope.tenant_id,
        site_id=scope.site_id,
        profile_id=profile_id,
        tag_type=tag.tag_type,
        tag_key=tag.tag_key,
        tag_value=tag.tag_value,
        confidence=tag.confidence,
        source=tag.source,
        source_ref=tag.source_ref,
        expires_at=tag.expires_at,
    )
    
    db.add(db_tag)
    await db.commit()
    await db.refresh(db_tag)
    
    return db_tag


@router.get("/{profile_id}/tags", response_model=list[VisitorTagResponse])
async def list_visitor_tags(
    profile_id: UUID,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
    tag_type: Optional[str] = Query(None, description="标签类型过滤"),
    active_only: bool = Query(True, description="仅显示激活的标签"),
):
    """查询游客标签列表"""
    
    conditions = [
        VisitorTag.profile_id == profile_id,
        VisitorTag.tenant_id == scope.tenant_id,
        VisitorTag.site_id == scope.site_id,
    ]
    
    if active_only:
        conditions.append(VisitorTag.is_active == True)
    if tag_type:
        conditions.append(VisitorTag.tag_type == tag_type)
    
    result = await db.execute(
        select(VisitorTag)
        .where(and_(*conditions))
        .order_by(VisitorTag.created_at.desc())
    )
    
    return result.scalars().all()


@router.patch("/{profile_id}/tags/{tag_id}", response_model=VisitorTagResponse)
async def update_visitor_tag(
    profile_id: UUID,
    tag_id: UUID,
    tag_update: VisitorTagUpdate,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """更新游客标签"""
    
    result = await db.execute(
        select(VisitorTag).where(
            VisitorTag.id == tag_id,
            VisitorTag.profile_id == profile_id,
            VisitorTag.tenant_id == scope.tenant_id,
            VisitorTag.site_id == scope.site_id
        )
    )
    tag = result.scalar_one_or_none()
    
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    
    # 更新字段
    update_data = tag_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tag, field, value)
    
    await db.commit()
    await db.refresh(tag)
    
    return tag


@router.delete("/{profile_id}/tags/{tag_id}", status_code=204)
async def delete_visitor_tag(
    profile_id: UUID,
    tag_id: UUID,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """删除游客标签"""
    
    result = await db.execute(
        select(VisitorTag).where(
            VisitorTag.id == tag_id,
            VisitorTag.profile_id == profile_id,
            VisitorTag.tenant_id == scope.tenant_id,
            VisitorTag.site_id == scope.site_id
        )
    )
    tag = result.scalar_one_or_none()
    
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    
    await db.delete(tag)
    await db.commit()


# ============ VisitorCheckIn 打卡记录 ============

@router.post("/{profile_id}/check-ins", response_model=VisitorCheckInResponse, status_code=201)
async def create_check_in(
    profile_id: UUID,
    check_in: VisitorCheckInCreate,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """创建场景打卡记录"""
    
    # 验证画像存在
    profile_result = await db.execute(
        select(VisitorProfile).where(
            VisitorProfile.id == profile_id,
            VisitorProfile.tenant_id == scope.tenant_id,
            VisitorProfile.site_id == scope.site_id
        )
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="画像不存在")
    
    # 创建打卡记录
    db_check_in = VisitorCheckIn(
        tenant_id=scope.tenant_id,
        site_id=scope.site_id,
        profile_id=profile_id,
        scene_id=check_in.scene_id,
        duration_minutes=check_in.duration_minutes,
        latitude=check_in.latitude,
        longitude=check_in.longitude,
        accuracy=check_in.accuracy,
        photo_count=check_in.photo_count,
        interaction_count=check_in.interaction_count,
        check_in_metadata=check_in.check_in_metadata,
    )
    
    db.add(db_check_in)
    
    # 更新画像统计
    profile.check_in_count += 1
    if check_in.duration_minutes:
        profile.total_duration_minutes += check_in.duration_minutes
    
    await db.commit()
    await db.refresh(db_check_in)
    
    # v0.2.0: 触发成就检查
    if profile.user_id:
        try:
            unlocked = await check_achievements_for_user(
                db=db,
                tenant_id=scope.tenant_id,
                site_id=scope.site_id,
                user_id=profile.user_id,
                event_name="check_in",
                event_data={"scene_id": str(check_in.scene_id)},
            )
            if unlocked:
                await db.commit()
        except Exception:
            pass  # 成就检查失败不影响主流程
    
    return db_check_in


@router.get("/{profile_id}/check-ins", response_model=list[VisitorCheckInResponse])
async def list_check_ins(
    profile_id: UUID,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
    scene_id: Optional[UUID] = Query(None, description="场景 ID 过滤"),
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
):
    """查询打卡记录列表"""
    
    conditions = [
        VisitorCheckIn.profile_id == profile_id,
        VisitorCheckIn.tenant_id == scope.tenant_id,
        VisitorCheckIn.site_id == scope.site_id,
    ]
    
    if scene_id:
        conditions.append(VisitorCheckIn.scene_id == scene_id)
    
    result = await db.execute(
        select(VisitorCheckIn)
        .where(and_(*conditions))
        .order_by(VisitorCheckIn.check_in_at.desc())
        .limit(limit)
    )
    
    return result.scalars().all()


# ============ VisitorInteraction NPC 交互 ============

@router.post("/{profile_id}/interactions", response_model=VisitorInteractionResponse, status_code=201)
async def create_or_update_interaction(
    profile_id: UUID,
    interaction: VisitorInteractionCreate,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """创建或更新 NPC 交互记录"""
    
    # 验证画像存在
    profile_result = await db.execute(
        select(VisitorProfile).where(
            VisitorProfile.id == profile_id,
            VisitorProfile.tenant_id == scope.tenant_id,
            VisitorProfile.site_id == scope.site_id
        )
    )
    if not profile_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="画像不存在")
    
    # 查找已有交互记录
    existing_result = await db.execute(
        select(VisitorInteraction).where(
            VisitorInteraction.profile_id == profile_id,
            VisitorInteraction.npc_id == interaction.npc_id,
            VisitorInteraction.tenant_id == scope.tenant_id,
            VisitorInteraction.site_id == scope.site_id
        )
    )
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        # 更新已有记录
        existing.conversation_count += interaction.conversation_count
        existing.message_count += interaction.message_count
        existing.total_duration_minutes += interaction.total_duration_minutes
        if interaction.sentiment_score is not None:
            existing.sentiment_score = interaction.sentiment_score
        if interaction.satisfaction_score is not None:
            existing.satisfaction_score = interaction.satisfaction_score
        if interaction.interaction_data:
            existing.interaction_data = interaction.interaction_data
        
        await db.commit()
        await db.refresh(existing)
        return existing
    else:
        # 创建新记录
        db_interaction = VisitorInteraction(
            tenant_id=scope.tenant_id,
            site_id=scope.site_id,
            profile_id=profile_id,
            npc_id=interaction.npc_id,
            conversation_count=interaction.conversation_count,
            message_count=interaction.message_count,
            total_duration_minutes=interaction.total_duration_minutes,
            sentiment_score=interaction.sentiment_score,
            satisfaction_score=interaction.satisfaction_score,
            interaction_data=interaction.interaction_data,
        )
        
        db.add(db_interaction)
        await db.commit()
        await db.refresh(db_interaction)
        
        return db_interaction


@router.get("/{profile_id}/interactions", response_model=list[VisitorInteractionResponse])
async def list_interactions(
    profile_id: UUID,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
    npc_id: Optional[UUID] = Query(None, description="NPC ID 过滤"),
):
    """查询 NPC 交互记录列表"""
    
    conditions = [
        VisitorInteraction.profile_id == profile_id,
        VisitorInteraction.tenant_id == scope.tenant_id,
        VisitorInteraction.site_id == scope.site_id,
    ]
    
    if npc_id:
        conditions.append(VisitorInteraction.npc_id == npc_id)
    
    result = await db.execute(
        select(VisitorInteraction)
        .where(and_(*conditions))
        .order_by(VisitorInteraction.last_interaction_at.desc())
    )
    
    return result.scalars().all()
