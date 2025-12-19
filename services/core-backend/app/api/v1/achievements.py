"""
成就体系 API

提供成就定义的 CRUD 操作、用户成就管理、手动颁发等功能
"""

from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.schemas.achievement import (
    AchievementCreate,
    AchievementUpdate,
    AchievementResponse,
    AchievementListResponse,
    UserAchievementGrant,
    UserAchievementResponse,
    UserAchievementListResponse,
    AchievementProgress,
    UserAchievementProgressResponse,
)
from app.core.rbac import ViewerOrAbove
from app.core.tenant_scope import RequiredScope
from app.database.models import (
    Achievement,
    UserAchievement,
    User,
    VisitorProfile,
)
from app.db.session import get_db

router = APIRouter(prefix="/achievements", tags=["achievements"])


# ============ Achievement CRUD ============

@router.post("", response_model=AchievementResponse, status_code=201)
async def create_achievement(
    achievement: AchievementCreate,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """创建成就定义"""
    
    # 检查 code 是否已存在
    existing = await db.execute(
        select(Achievement).where(
            Achievement.tenant_id == scope.tenant_id,
            Achievement.site_id == scope.site_id,
            Achievement.code == achievement.code
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"成就代码 '{achievement.code}' 已存在")
    
    db_achievement = Achievement(
        tenant_id=scope.tenant_id,
        site_id=scope.site_id,
        **achievement.model_dump()
    )
    
    db.add(db_achievement)
    await db.commit()
    await db.refresh(db_achievement)
    
    return db_achievement


@router.get("", response_model=AchievementListResponse)
async def list_achievements(
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    category: Optional[str] = Query(None, description="分类过滤"),
    is_active: Optional[bool] = Query(None, description="是否启用"),
):
    """查询成就列表"""
    
    conditions = [
        Achievement.tenant_id == scope.tenant_id,
        Achievement.site_id == scope.site_id,
    ]
    
    if category:
        conditions.append(Achievement.category == category)
    if is_active is not None:
        conditions.append(Achievement.is_active == is_active)
    
    # 查询总数
    count_result = await db.execute(
        select(func.count(Achievement.id)).where(and_(*conditions))
    )
    total = count_result.scalar_one()
    
    # 查询列表
    offset = (page - 1) * page_size
    result = await db.execute(
        select(Achievement)
        .where(and_(*conditions))
        .order_by(Achievement.sort_order, Achievement.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    achievements = result.scalars().all()
    
    return AchievementListResponse(
        items=achievements,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{achievement_id}", response_model=AchievementResponse)
async def get_achievement(
    achievement_id: UUID,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """获取成就详情"""
    
    result = await db.execute(
        select(Achievement).where(
            Achievement.id == achievement_id,
            Achievement.tenant_id == scope.tenant_id,
            Achievement.site_id == scope.site_id
        )
    )
    achievement = result.scalar_one_or_none()
    
    if not achievement:
        raise HTTPException(status_code=404, detail="成就不存在")
    
    return achievement


@router.patch("/{achievement_id}", response_model=AchievementResponse)
async def update_achievement(
    achievement_id: UUID,
    achievement_update: AchievementUpdate,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """更新成就"""
    
    result = await db.execute(
        select(Achievement).where(
            Achievement.id == achievement_id,
            Achievement.tenant_id == scope.tenant_id,
            Achievement.site_id == scope.site_id
        )
    )
    achievement = result.scalar_one_or_none()
    
    if not achievement:
        raise HTTPException(status_code=404, detail="成就不存在")
    
    update_data = achievement_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(achievement, field, value)
    
    await db.commit()
    await db.refresh(achievement)
    
    return achievement


@router.delete("/{achievement_id}", status_code=204)
async def delete_achievement(
    achievement_id: UUID,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """删除成就"""
    
    result = await db.execute(
        select(Achievement).where(
            Achievement.id == achievement_id,
            Achievement.tenant_id == scope.tenant_id,
            Achievement.site_id == scope.site_id
        )
    )
    achievement = result.scalar_one_or_none()
    
    if not achievement:
        raise HTTPException(status_code=404, detail="成就不存在")
    
    await db.delete(achievement)
    await db.commit()


# ============ 手动颁发成就 ============

@router.post("/{achievement_id}/grant", response_model=UserAchievementResponse, status_code=201)
async def grant_achievement(
    achievement_id: UUID,
    grant: UserAchievementGrant,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """手动颁发成就给用户"""
    
    # 验证成就存在
    achievement_result = await db.execute(
        select(Achievement).where(
            Achievement.id == achievement_id,
            Achievement.tenant_id == scope.tenant_id,
            Achievement.site_id == scope.site_id
        )
    )
    achievement = achievement_result.scalar_one_or_none()
    if not achievement:
        raise HTTPException(status_code=404, detail="成就不存在")
    
    # 验证用户存在
    user_result = await db.execute(
        select(User).where(
            User.id == str(grant.user_id),
            User.tenant_id == scope.tenant_id
        )
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    # 检查是否已解锁
    existing = await db.execute(
        select(UserAchievement).where(
            UserAchievement.user_id == grant.user_id,
            UserAchievement.achievement_id == achievement_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户已解锁该成就")
    
    # 创建用户成就记录
    user_achievement = UserAchievement(
        tenant_id=scope.tenant_id,
        site_id=scope.site_id,
        user_id=grant.user_id,
        achievement_id=achievement_id,
        progress=achievement.rule_config.get("threshold", 0) if achievement.rule_type == "count" else 0,
        progress_target=achievement.rule_config.get("threshold", 0) if achievement.rule_type == "count" else 0,
        source="manual",
        source_ref=grant.source_ref,
        achievement_metadata=grant.achievement_metadata,
    )
    
    db.add(user_achievement)
    
    # 更新游客画像的成就计数
    profile_result = await db.execute(
        select(VisitorProfile).where(
            VisitorProfile.user_id == grant.user_id,
            VisitorProfile.tenant_id == scope.tenant_id,
            VisitorProfile.site_id == scope.site_id
        )
    )
    profile = profile_result.scalar_one_or_none()
    if profile:
        profile.achievement_count += 1
    
    await db.commit()
    await db.refresh(user_achievement)
    
    return user_achievement


# ============ 用户成就查询 ============

@router.get("/users/{user_id}/achievements", response_model=UserAchievementListResponse)
async def get_user_achievements(
    user_id: UUID,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """获取用户已解锁的成就列表"""
    
    result = await db.execute(
        select(UserAchievement)
        .options(selectinload(UserAchievement.achievement))
        .where(
            UserAchievement.user_id == user_id,
            UserAchievement.tenant_id == scope.tenant_id,
            UserAchievement.site_id == scope.site_id
        )
        .order_by(UserAchievement.unlocked_at.desc())
    )
    user_achievements = result.scalars().all()
    
    return UserAchievementListResponse(
        items=user_achievements,
        total=len(user_achievements),
    )


@router.get("/users/{user_id}/progress", response_model=UserAchievementProgressResponse)
async def get_user_achievement_progress(
    user_id: UUID,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """获取用户成就进度（包括未解锁的）"""
    
    # 获取所有活跃的成就
    achievements_result = await db.execute(
        select(Achievement).where(
            Achievement.tenant_id == scope.tenant_id,
            Achievement.site_id == scope.site_id,
            Achievement.is_active == True,
            Achievement.is_hidden == False
        )
    )
    achievements = achievements_result.scalars().all()
    
    # 获取用户已解锁的成就
    user_achievements_result = await db.execute(
        select(UserAchievement).where(
            UserAchievement.user_id == user_id,
            UserAchievement.tenant_id == scope.tenant_id,
            UserAchievement.site_id == scope.site_id
        )
    )
    user_achievements = {ua.achievement_id: ua for ua in user_achievements_result.scalars().all()}
    
    # 构建进度列表
    progress_list = []
    total_points = 0
    
    for achievement in achievements:
        user_achievement = user_achievements.get(achievement.id)
        is_unlocked = user_achievement is not None
        
        progress = user_achievement.progress if user_achievement else 0
        progress_target = achievement.rule_config.get("threshold", 0) if achievement.rule_type == "count" else 1
        
        if is_unlocked:
            total_points += achievement.points
        
        progress_list.append(AchievementProgress(
            achievement_id=achievement.id,
            achievement_code=achievement.code,
            achievement_name=achievement.name,
            category=achievement.category,
            tier=achievement.tier,
            is_unlocked=is_unlocked,
            unlocked_at=user_achievement.unlocked_at if user_achievement else None,
            progress=progress,
            progress_target=progress_target,
            progress_percent=min(100.0, (progress / progress_target * 100) if progress_target > 0 else 0),
        ))
    
    return UserAchievementProgressResponse(
        user_id=user_id,
        total_unlocked=len(user_achievements),
        total_points=total_points,
        achievements=progress_list,
    )
