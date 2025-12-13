"""
领域模型

核心实体：Tenant, User, Site, Scene, POI, NPC, Quest, Asset, Visitor 等
所有实体都带 tenant_id + site_id 以支持多租户多站点架构

注意：v0.1.0 起，新模型统一使用 app.database.models
本模块保留旧模型以保持向后兼容，新代码请使用 app.database.models
"""

# ============================================================
# 新模型（推荐使用）- 来自 app.database.models
# ============================================================
from app.database.models import (
    Tenant as TenantNew,
    Site as SiteNew,
    User as UserNew,
    Content,
    ContentStatus,
    NPCProfile,
    Quest as QuestNew,
    QuestStep as QuestStepNew,
    Evidence,
    EvidenceSourceType,
    Conversation,
    Message,
    TraceLedger,
    PolicyMode,
    UserFeedback,
    FeedbackType,
)

# ============================================================
# 旧模型（向后兼容）- 逐步废弃
# ============================================================
from app.domain.tenant import Tenant
from app.domain.user import User, UserRole
from app.domain.site import Site
from app.domain.scene import Scene
from app.domain.npc import NPC
from app.domain.poi import POI
from app.domain.quest import Quest, QuestStep
from app.domain.visitor import Visitor, VisitorQuest
from app.domain.knowledge import KnowledgeEntry, KnowledgeType
from app.domain.tool_call_log import ToolCallLog, ToolCallStatus

__all__ = [
    # 新模型（推荐）
    "TenantNew",
    "SiteNew",
    "UserNew",
    "Content",
    "ContentStatus",
    "NPCProfile",
    "QuestNew",
    "QuestStepNew",
    "Evidence",
    "EvidenceSourceType",
    "Conversation",
    "Message",
    "TraceLedger",
    "PolicyMode",
    "UserFeedback",
    "FeedbackType",
    # 旧模型（兼容）
    "Tenant",
    "User",
    "UserRole",
    "Site",
    "Scene",
    "NPC",
    "POI",
    "Quest",
    "QuestStep",
    "Visitor",
    "VisitorQuest",
    "KnowledgeEntry",
    "KnowledgeType",
    "ToolCallLog",
    "ToolCallStatus",
]
