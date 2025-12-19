"""
游客画像 API Schemas
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ============ VisitorProfile Schemas ============

class VisitorProfileBase(BaseModel):
    """游客画像基础 Schema"""
    activity_level: str = Field("new", description="活跃度: new/casual/active/power")
    engagement_score: float = Field(0.0, ge=0, le=100, description="参与度评分")
    learning_style: Optional[str] = Field(None, description="学习风格")
    notes: Optional[str] = Field(None, description="备注")


class VisitorProfileCreate(VisitorProfileBase):
    """创建游客画像"""
    user_id: UUID = Field(..., description="用户 ID")


class VisitorProfileUpdate(BaseModel):
    """更新游客画像"""
    activity_level: Optional[str] = None
    engagement_score: Optional[float] = Field(None, ge=0, le=100)
    learning_style: Optional[str] = None
    favorite_npc_id: Optional[UUID] = None
    favorite_scene_id: Optional[UUID] = None
    interest_tags: Optional[dict] = None
    notes: Optional[str] = None


class VisitorProfileStats(BaseModel):
    """游客画像统计信息"""
    visit_count: int = 0
    total_duration_minutes: int = 0
    conversation_count: int = 0
    quest_completed_count: int = 0
    achievement_count: int = 0
    check_in_count: int = 0


class VisitorProfileResponse(VisitorProfileBase):
    """游客画像响应"""
    id: UUID
    tenant_id: str
    site_id: str
    user_id: UUID
    
    # 统计信息
    visit_count: int
    total_duration_minutes: int
    conversation_count: int
    quest_completed_count: int
    achievement_count: int
    check_in_count: int
    
    # 偏好
    favorite_npc_id: Optional[UUID]
    favorite_scene_id: Optional[UUID]
    interest_tags: Optional[dict]
    
    # 时间
    first_visit_at: datetime
    last_visit_at: datetime
    last_active_at: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VisitorProfileListResponse(BaseModel):
    """游客画像列表响应"""
    items: list[VisitorProfileResponse]
    total: int
    page: int
    page_size: int


# ============ VisitorTag Schemas ============

class VisitorTagBase(BaseModel):
    """游客标签基础 Schema"""
    tag_type: str = Field(..., description="标签类型: interest/behavior/achievement/custom")
    tag_key: str = Field(..., max_length=100, description="标签键")
    tag_value: str = Field(..., max_length=200, description="标签值")
    confidence: float = Field(1.0, ge=0, le=1, description="置信度")
    source: str = Field("manual", description="来源: auto/manual/ai")
    source_ref: Optional[str] = Field(None, description="来源引用")


class VisitorTagCreate(VisitorTagBase):
    """创建游客标签"""
    profile_id: UUID = Field(..., description="画像 ID")
    expires_at: Optional[datetime] = Field(None, description="过期时间")


class VisitorTagUpdate(BaseModel):
    """更新游客标签"""
    tag_value: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0, le=1)
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None


class VisitorTagResponse(VisitorTagBase):
    """游客标签响应"""
    id: UUID
    tenant_id: str
    site_id: str
    profile_id: UUID
    is_active: bool
    expires_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ VisitorCheckIn Schemas ============

class VisitorCheckInBase(BaseModel):
    """场景打卡基础 Schema"""
    scene_id: UUID = Field(..., description="场景 ID")
    duration_minutes: Optional[int] = Field(None, ge=0, description="停留时长（分钟）")
    latitude: Optional[float] = Field(None, description="纬度")
    longitude: Optional[float] = Field(None, description="经度")
    accuracy: Optional[float] = Field(None, ge=0, description="定位精度（米）")
    photo_count: int = Field(0, ge=0, description="拍照数量")
    interaction_count: int = Field(0, ge=0, description="交互次数")


class VisitorCheckInCreate(VisitorCheckInBase):
    """创建场景打卡"""
    profile_id: UUID = Field(..., description="画像 ID")
    check_in_metadata: Optional[dict] = Field(None, description="扩展元数据")


class VisitorCheckInResponse(VisitorCheckInBase):
    """场景打卡响应"""
    id: UUID
    tenant_id: str
    site_id: str
    profile_id: UUID
    check_in_at: datetime
    check_in_metadata: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


# ============ VisitorInteraction Schemas ============

class VisitorInteractionBase(BaseModel):
    """NPC 交互基础 Schema"""
    npc_id: UUID = Field(..., description="NPC ID")
    conversation_count: int = Field(0, ge=0, description="对话次数")
    message_count: int = Field(0, ge=0, description="消息数量")
    total_duration_minutes: int = Field(0, ge=0, description="总对话时长（分钟）")
    sentiment_score: Optional[float] = Field(None, ge=-1, le=1, description="情感评分")
    satisfaction_score: Optional[float] = Field(None, ge=0, le=5, description="满意度评分")


class VisitorInteractionCreate(VisitorInteractionBase):
    """创建 NPC 交互记录"""
    profile_id: UUID = Field(..., description="画像 ID")
    interaction_data: Optional[dict] = Field(None, description="交互详细数据")


class VisitorInteractionUpdate(BaseModel):
    """更新 NPC 交互记录"""
    conversation_count: Optional[int] = Field(None, ge=0)
    message_count: Optional[int] = Field(None, ge=0)
    total_duration_minutes: Optional[int] = Field(None, ge=0)
    sentiment_score: Optional[float] = Field(None, ge=-1, le=1)
    satisfaction_score: Optional[float] = Field(None, ge=0, le=5)
    interaction_data: Optional[dict] = None


class VisitorInteractionResponse(VisitorInteractionBase):
    """NPC 交互响应"""
    id: UUID
    tenant_id: str
    site_id: str
    profile_id: UUID
    first_interaction_at: datetime
    last_interaction_at: datetime
    interaction_data: Optional[dict]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ 批量操作 Schemas ============

class BatchTagCreate(BaseModel):
    """批量创建标签"""
    profile_id: UUID
    tags: list[VisitorTagBase]


class ProfileAnalytics(BaseModel):
    """画像分析数据"""
    profile_id: UUID
    total_engagement_time: int  # 总参与时长（分钟）
    avg_session_duration: float  # 平均会话时长
    favorite_npcs: list[dict]  # 最喜欢的 NPC 列表
    favorite_scenes: list[dict]  # 最喜欢的场景列表
    active_tags: list[VisitorTagResponse]  # 活跃标签
    recent_check_ins: list[VisitorCheckInResponse]  # 最近打卡
