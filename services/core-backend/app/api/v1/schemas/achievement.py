"""
成就体系 API Schemas
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ============ Achievement Schemas ============

class AchievementRuleConfig(BaseModel):
    """成就规则配置"""
    type: str = Field(..., description="规则类型: count/event/composite")
    metric: Optional[str] = Field(None, description="指标名（计数型）")
    threshold: Optional[int] = Field(None, description="阈值（计数型）")
    operator: Optional[str] = Field("gte", description="比较运算符: gte/gt/eq")
    event_name: Optional[str] = Field(None, description="事件名（事件型）")
    conditions: Optional[dict] = Field(None, description="条件（事件型）")
    rules: Optional[list] = Field(None, description="子规则（组合型）")


class AchievementBase(BaseModel):
    """成就基础 Schema"""
    code: str = Field(..., max_length=100, description="唯一标识码")
    name: str = Field(..., max_length=200, description="显示名称")
    description: Optional[str] = Field(None, description="描述")
    icon_url: Optional[str] = Field(None, max_length=500, description="图标 URL")
    category: str = Field("exploration", description="分类: exploration/social/learning/special")
    tier: int = Field(1, ge=1, le=4, description="等级: 1=铜, 2=银, 3=金, 4=钻石")
    points: int = Field(10, ge=0, description="积分值")
    rule_type: str = Field("count", description="规则类型: count/event/composite")
    rule_config: dict = Field(default_factory=dict, description="规则配置")
    is_hidden: bool = Field(False, description="是否隐藏成就")
    is_active: bool = Field(True, description="是否启用")
    sort_order: int = Field(0, description="排序")


class AchievementCreate(AchievementBase):
    """创建成就"""
    pass


class AchievementUpdate(BaseModel):
    """更新成就"""
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    icon_url: Optional[str] = Field(None, max_length=500)
    category: Optional[str] = None
    tier: Optional[int] = Field(None, ge=1, le=4)
    points: Optional[int] = Field(None, ge=0)
    rule_type: Optional[str] = None
    rule_config: Optional[dict] = None
    is_hidden: Optional[bool] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class AchievementResponse(AchievementBase):
    """成就响应"""
    id: UUID
    tenant_id: str
    site_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AchievementListResponse(BaseModel):
    """成就列表响应"""
    items: list[AchievementResponse]
    total: int
    page: int
    page_size: int


# ============ UserAchievement Schemas ============

class UserAchievementBase(BaseModel):
    """用户成就基础 Schema"""
    progress: int = Field(0, ge=0, description="当前进度")
    progress_target: int = Field(0, ge=0, description="目标值")


class UserAchievementGrant(BaseModel):
    """手动颁发成就"""
    user_id: UUID = Field(..., description="用户 ID")
    source_ref: Optional[str] = Field(None, description="来源引用")
    achievement_metadata: Optional[dict] = Field(None, description="扩展元数据")


class UserAchievementResponse(UserAchievementBase):
    """用户成就响应"""
    id: UUID
    tenant_id: str
    site_id: str
    user_id: UUID
    achievement_id: UUID
    unlocked_at: datetime
    source: str
    source_ref: Optional[str]
    achievement_metadata: Optional[dict]
    created_at: datetime
    updated_at: datetime
    
    # 嵌套成就信息
    achievement: Optional[AchievementResponse] = None

    class Config:
        from_attributes = True


class UserAchievementListResponse(BaseModel):
    """用户成就列表响应"""
    items: list[UserAchievementResponse]
    total: int


class AchievementProgress(BaseModel):
    """成就进度"""
    achievement_id: UUID
    achievement_code: str
    achievement_name: str
    category: str
    tier: int
    is_unlocked: bool
    unlocked_at: Optional[datetime]
    progress: int
    progress_target: int
    progress_percent: float


class UserAchievementProgressResponse(BaseModel):
    """用户成就进度响应"""
    user_id: UUID
    total_unlocked: int
    total_points: int
    achievements: list[AchievementProgress]


# ============ 统计 Schemas ============

class AchievementStats(BaseModel):
    """成就统计"""
    total_achievements: int
    total_unlocked: int
    unlock_rate: float
    category_stats: dict[str, int]
    tier_stats: dict[int, int]
