"""
NPC 模型

NPC (Non-Player Character) 代表虚拟人物角色
类型：祖先(ancestor)、匠人(craftsman)、农夫(farmer)、塾师(teacher)
"""

from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import AuditMixin, Base


class NPC(Base, AuditMixin):
    """NPC 实体"""

    __tablename__ = "npcs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    site_id: Mapped[str] = mapped_column(String(50), ForeignKey("sites.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    npc_type: Mapped[Optional[str]] = mapped_column(String(50))

    persona: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    avatar_asset_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True))
    voice_id: Mapped[Optional[str]] = mapped_column(String(100))

    scene_ids: Mapped[Optional[list[UUID]]] = mapped_column(ARRAY(PG_UUID(as_uuid=True)))

    greeting_templates: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    fallback_responses: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))

    status: Mapped[str] = mapped_column(String(20), default="active")

    site: Mapped["Site"] = relationship(back_populates="npcs")

    def __repr__(self) -> str:
        return f"<NPC(id={self.id}, name={self.name}, type={self.npc_type})>"

    @property
    def identity(self) -> dict[str, Any]:
        """获取 NPC 身份信息"""
        return self.persona.get("identity", {})

    @property
    def personality(self) -> dict[str, Any]:
        """获取 NPC 性格特征"""
        return self.persona.get("personality", {})

    @property
    def knowledge_domains(self) -> list[str]:
        """获取 NPC 知识领域"""
        return self.persona.get("knowledge_domains", [])

    @property
    def constraints(self) -> dict[str, Any]:
        """获取 NPC 约束配置"""
        return self.persona.get("constraints", {})


from app.domain.site import Site
