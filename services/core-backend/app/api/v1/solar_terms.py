"""
节气与农耕知识 API
"""

from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import ViewerOrAbove
from app.core.tenant_scope import RequiredScope
from app.db import get_db
from app.database.models import SolarTerm, FarmingKnowledge

router = APIRouter()


# ============ Schemas ============

class SolarTermResponse(BaseModel):
    id: UUID
    code: str
    name: str
    order: int
    month: int
    day_start: int
    day_end: int
    description: Optional[str] = None
    farming_advice: Optional[str] = None
    cultural_customs: Optional[dict] = None
    poems: Optional[list] = None

    model_config = {"from_attributes": True}


class FarmingKnowledgeCreate(BaseModel):
    solar_term_code: Optional[str] = Field(None, description="关联节气代码")
    category: str = Field("general", description="分类")
    title: str = Field(..., max_length=200, description="标题")
    content: str = Field(..., description="内容")
    media_urls: Optional[dict] = Field(None, description="媒体 URL")
    related_pois: Optional[dict] = Field(None, description="关联兴趣点")
    is_active: bool = Field(True, description="是否启用")
    sort_order: int = Field(0, description="排序")


class FarmingKnowledgeUpdate(BaseModel):
    solar_term_code: Optional[str] = None
    category: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    media_urls: Optional[dict] = None
    related_pois: Optional[dict] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class FarmingKnowledgeResponse(BaseModel):
    id: UUID
    tenant_id: str
    site_id: str
    solar_term_code: Optional[str] = None
    category: str
    title: str
    content: str
    media_urls: Optional[dict] = None
    related_pois: Optional[dict] = None
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FarmingKnowledgeListResponse(BaseModel):
    items: List[FarmingKnowledgeResponse]
    total: int


# ============ Solar Term API ============

@router.get("/solar-terms", response_model=List[SolarTermResponse], tags=["solar-terms"])
async def list_solar_terms(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """获取二十四节气列表（公开接口）"""
    result = await db.execute(
        select(SolarTerm).order_by(SolarTerm.order)
    )
    return result.scalars().all()


@router.get("/solar-terms/current", response_model=SolarTermResponse, tags=["solar-terms"])
async def get_current_solar_term(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """获取当前节气（公开接口）"""
    today = datetime.now()
    month = today.month
    day = today.day
    
    # 查找当前日期所在的节气
    result = await db.execute(
        select(SolarTerm).where(
            SolarTerm.month == month,
            SolarTerm.day_start <= day,
            SolarTerm.day_end >= day
        )
    )
    term = result.scalar_one_or_none()
    
    if not term:
        # 如果精确匹配不到，找最接近的
        result = await db.execute(
            select(SolarTerm).where(SolarTerm.month == month).order_by(SolarTerm.day_start)
        )
        terms = result.scalars().all()
        if terms:
            for t in terms:
                if day >= t.day_start:
                    term = t
            if not term:
                term = terms[0]
    
    if not term:
        # 回退到上个月的最后一个节气
        prev_month = month - 1 if month > 1 else 12
        result = await db.execute(
            select(SolarTerm).where(SolarTerm.month == prev_month).order_by(SolarTerm.order.desc()).limit(1)
        )
        term = result.scalar_one_or_none()
    
    if not term:
        raise HTTPException(status_code=404, detail="未找到当前节气")
    
    return term


@router.get("/solar-terms/{code}", response_model=SolarTermResponse, tags=["solar-terms"])
async def get_solar_term(
    code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """获取节气详情（公开接口）"""
    result = await db.execute(
        select(SolarTerm).where(SolarTerm.code == code)
    )
    term = result.scalar_one_or_none()
    
    if not term:
        raise HTTPException(status_code=404, detail="节气不存在")
    
    return term


# ============ Farming Knowledge API ============

@router.get("/farming-knowledge", response_model=FarmingKnowledgeListResponse, tags=["farming-knowledge"])
async def list_farming_knowledge(
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
    solar_term_code: Optional[str] = Query(None, description="按节气筛选"),
    category: Optional[str] = Query(None, description="按分类筛选"),
    is_active: Optional[bool] = Query(None, description="按状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
):
    """获取农耕知识列表"""
    conditions = [
        FarmingKnowledge.tenant_id == scope.tenant_id,
        FarmingKnowledge.site_id == scope.site_id,
    ]
    
    if solar_term_code:
        conditions.append(FarmingKnowledge.solar_term_code == solar_term_code)
    if category:
        conditions.append(FarmingKnowledge.category == category)
    if is_active is not None:
        conditions.append(FarmingKnowledge.is_active == is_active)
    
    # 统计总数
    count_result = await db.execute(
        select(func.count(FarmingKnowledge.id)).where(*conditions)
    )
    total = count_result.scalar() or 0
    
    # 分页查询
    result = await db.execute(
        select(FarmingKnowledge)
        .where(*conditions)
        .order_by(FarmingKnowledge.sort_order, FarmingKnowledge.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = result.scalars().all()
    
    return FarmingKnowledgeListResponse(items=items, total=total)


@router.post("/farming-knowledge", response_model=FarmingKnowledgeResponse, status_code=201, tags=["farming-knowledge"])
async def create_farming_knowledge(
    data: FarmingKnowledgeCreate,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """创建农耕知识"""
    knowledge = FarmingKnowledge(
        tenant_id=scope.tenant_id,
        site_id=scope.site_id,
        **data.model_dump()
    )
    db.add(knowledge)
    await db.commit()
    await db.refresh(knowledge)
    return knowledge


@router.get("/farming-knowledge/{knowledge_id}", response_model=FarmingKnowledgeResponse, tags=["farming-knowledge"])
async def get_farming_knowledge(
    knowledge_id: UUID,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """获取农耕知识详情"""
    result = await db.execute(
        select(FarmingKnowledge).where(
            FarmingKnowledge.id == knowledge_id,
            FarmingKnowledge.tenant_id == scope.tenant_id,
            FarmingKnowledge.site_id == scope.site_id,
        )
    )
    knowledge = result.scalar_one_or_none()
    
    if not knowledge:
        raise HTTPException(status_code=404, detail="农耕知识不存在")
    
    return knowledge


@router.patch("/farming-knowledge/{knowledge_id}", response_model=FarmingKnowledgeResponse, tags=["farming-knowledge"])
async def update_farming_knowledge(
    knowledge_id: UUID,
    data: FarmingKnowledgeUpdate,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """更新农耕知识"""
    result = await db.execute(
        select(FarmingKnowledge).where(
            FarmingKnowledge.id == knowledge_id,
            FarmingKnowledge.tenant_id == scope.tenant_id,
            FarmingKnowledge.site_id == scope.site_id,
        )
    )
    knowledge = result.scalar_one_or_none()
    
    if not knowledge:
        raise HTTPException(status_code=404, detail="农耕知识不存在")
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(knowledge, field, value)
    
    await db.commit()
    await db.refresh(knowledge)
    return knowledge


@router.delete("/farming-knowledge/{knowledge_id}", status_code=204, tags=["farming-knowledge"])
async def delete_farming_knowledge(
    knowledge_id: UUID,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """删除农耕知识"""
    result = await db.execute(
        select(FarmingKnowledge).where(
            FarmingKnowledge.id == knowledge_id,
            FarmingKnowledge.tenant_id == scope.tenant_id,
            FarmingKnowledge.site_id == scope.site_id,
        )
    )
    knowledge = result.scalar_one_or_none()
    
    if not knowledge:
        raise HTTPException(status_code=404, detail="农耕知识不存在")
    
    await db.delete(knowledge)
    await db.commit()


@router.get("/farming-knowledge/by-term/{term_code}", response_model=List[FarmingKnowledgeResponse], tags=["farming-knowledge"])
async def get_farming_knowledge_by_term(
    term_code: str,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """按节气查询农耕知识"""
    result = await db.execute(
        select(FarmingKnowledge).where(
            FarmingKnowledge.tenant_id == scope.tenant_id,
            FarmingKnowledge.site_id == scope.site_id,
            FarmingKnowledge.solar_term_code == term_code,
            FarmingKnowledge.is_active == True,
        ).order_by(FarmingKnowledge.sort_order)
    )
    return result.scalars().all()
