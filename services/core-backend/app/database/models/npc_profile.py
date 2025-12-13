"""
NPC 人设模型

版本化设计：npc_id + version + active
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import AuditMixin, Base, TenantMixin

if TYPE_CHECKING:
    from app.database.models.site import Site


class NPCProfile(Base, TenantMixin, AuditMixin):
    """
    NPC 人设实体

    版本化设计：
    - npc_id: NPC 唯一标识
    - version: 版本号
    - active: 是否为当前激活版本

    同一个 npc_id 可以有多个版本，但只有一个 active=True
    """

    __tablename__ = "npc_profiles"

    # 主键（每个版本一个 ID）
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    # NPC 标识（同一 NPC 的所有版本共享）
    npc_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # 版本控制
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true", index=True)

    # 基本信息
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    npc_type: Mapped[Optional[str]] = mapped_column(String(50))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))

    # 人设配置（JSON Schema 验证）
    persona: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 身份信息
    era: Mapped[Optional[str]] = mapped_column(String(100))
    role: Mapped[Optional[str]] = mapped_column(String(200))
    background: Mapped[Optional[str]] = mapped_column(Text)

    # 性格特征
    personality_traits: Mapped[list] = mapped_column(ARRAY(String), server_default="{}", nullable=False)
    speaking_style: Mapped[Optional[str]] = mapped_column(Text)
    tone: Mapped[Optional[str]] = mapped_column(String(50))
    catchphrases: Mapped[list] = mapped_column(ARRAY(String), server_default="{}", nullable=False)

    # 知识领域
    knowledge_domains: Mapped[list] = mapped_column(ARRAY(String), server_default="{}", nullable=False)

    # 对话配置
    greeting_templates: Mapped[list] = mapped_column(ARRAY(String), server_default="{}", nullable=False)
    fallback_responses: Mapped[list] = mapped_column(ARRAY(String), server_default="{}", nullable=False)
    max_response_length: Mapped[int] = mapped_column(Integer, server_default="500", nullable=False)

    # 约束
    forbidden_topics: Mapped[list] = mapped_column(ARRAY(String), server_default="{}", nullable=False)
    must_cite_sources: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    time_awareness: Mapped[Optional[str]] = mapped_column(String(50))

    # 语音配置
    voice_id: Mapped[Optional[str]] = mapped_column(String(100))
    voice_config: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 状态
    status: Mapped[str] = mapped_column(String(20), server_default="active", nullable=False)

    # 关系
    site: Mapped["Site"] = relationship("Site", back_populates="npc_profiles")

    def __repr__(self) -> str:
        return f"<NPCProfile(npc_id={self.npc_id}, version={self.version}, active={self.active})>"

    def create_new_version(self) -> "NPCProfile":
        """创建新版本"""
        new_profile = NPCProfile(
            npc_id=self.npc_id,
            version=self.version + 1,
            active=False,
            tenant_id=self.tenant_id,
            site_id=self.site_id,
            name=self.name,
            display_name=self.display_name,
            npc_type=self.npc_type,
            avatar_url=self.avatar_url,
            persona=self.persona.copy(),
            era=self.era,
            role=self.role,
            background=self.background,
            personality_traits=self.personality_traits.copy(),
            speaking_style=self.speaking_style,
            tone=self.tone,
            catchphrases=self.catchphrases.copy(),
            knowledge_domains=self.knowledge_domains.copy(),
            greeting_templates=self.greeting_templates.copy(),
            fallback_responses=self.fallback_responses.copy(),
            max_response_length=self.max_response_length,
            forbidden_topics=self.forbidden_topics.copy(),
            must_cite_sources=self.must_cite_sources,
            time_awareness=self.time_awareness,
            voice_id=self.voice_id,
            voice_config=self.voice_config.copy(),
        )
        return new_profile
