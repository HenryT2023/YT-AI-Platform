"""
数据库模型

所有 SQLAlchemy 模型的统一导出
"""

from app.database.models.tenant import Tenant
from app.database.models.site import Site, SiteStatsDaily
from app.database.models.user import User
from app.database.models.content import Content, ContentStatus
from app.database.models.npc_profile import NPCProfile
from app.database.models.quest import Quest, QuestStep
from app.database.models.quest_submission import QuestSubmission
from app.database.models.evidence import Evidence, EvidenceSourceType
from app.database.models.conversation import Conversation, Message
from app.database.models.trace_ledger import TraceLedger, PolicyMode
from app.database.models.user_feedback import UserFeedback, FeedbackType
from app.database.models.analytics_event import AnalyticsEvent
from app.database.models.npc_prompt import NPCPrompt
from app.database.models.vector_sync_job import VectorSyncJob, VectorSyncStatus
from app.database.models.embedding_usage import EmbeddingUsage, EmbeddingStatus, EmbeddingObjectType
from app.database.models.alerts import AlertEvent, AlertSilence, AlertStatus
from app.database.models.refresh_token import RefreshToken
from app.database.models.visitor_profile import (
    VisitorProfile,
    VisitorTag,
    VisitorCheckIn,
    VisitorInteraction,
)
from app.database.models.achievement import (
    Achievement,
    UserAchievement,
    AchievementCategory,
    AchievementTier,
    RuleType,
)
from app.database.models.solar_term import (
    SolarTerm,
    FarmingKnowledge,
)
from app.database.models.iot_device import (
    IoTDevice,
    IoTDeviceLog,
    DeviceType,
    DeviceStatus,
    EventType,
)

__all__ = [
    # Core
    "Tenant",
    "Site",
    "SiteStatsDaily",
    "User",
    # Content
    "Content",
    "ContentStatus",
    # NPC
    "NPCProfile",
    "NPCPrompt",
    # Quest
    "Quest",
    "QuestStep",
    "QuestSubmission",
    # Evidence
    "Evidence",
    "EvidenceSourceType",
    # Conversation
    "Conversation",
    "Message",
    # Trace
    "TraceLedger",
    "PolicyMode",
    # Feedback
    "UserFeedback",
    "FeedbackType",
    # Analytics
    "AnalyticsEvent",
    # Vector Sync
    "VectorSyncJob",
    "VectorSyncStatus",
    # Embedding Usage
    "EmbeddingUsage",
    "EmbeddingStatus",
    "EmbeddingObjectType",
    # Alerts
    "AlertEvent",
    "AlertSilence",
    "AlertStatus",
    # Auth
    "RefreshToken",
    # Visitor Profile
    "VisitorProfile",
    "VisitorTag",
    "VisitorCheckIn",
    "VisitorInteraction",
    # Achievement
    "Achievement",
    "UserAchievement",
    "AchievementCategory",
    "AchievementTier",
    "RuleType",
    # Solar Term & Farming
    "SolarTerm",
    "FarmingKnowledge",
    # IoT Device
    "IoTDevice",
    "IoTDeviceLog",
    "DeviceType",
    "DeviceStatus",
    "EventType",
]
