"""
NPC Prompt 模型

可版本化、可审计、可回滚的 Prompt 资产
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, Integer, Boolean, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TenantMixin, TimestampMixin


class NPCPrompt(Base, TenantMixin, TimestampMixin):
    """
    NPC Prompt 实体

    可版本化的 Prompt 资产，支持：
    - 版本管理：每个 NPC 可有多个版本
    - 激活控制：只有一个版本处于 active 状态
    - 审计追踪：记录操作人和时间
    - 回滚支持：可切换到历史版本

    真源（Source of Truth）：数据库
    data/prompts/ 作为初始化种子和备份
    """

    __tablename__ = "npc_prompts"

    # 主键
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    # NPC 关联
    npc_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # 版本信息
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Prompt 内容
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # 元数据（包含 name, description, author 等）
    meta: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 策略配置（引用要求、禁答要求等）
    policy: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    # 审计信息
    author: Mapped[Optional[str]] = mapped_column(String(100))
    operator_id: Mapped[Optional[str]] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    description: Mapped[Optional[str]] = mapped_column(Text)

    # 软删除
    deleted_at: Mapped[Optional[datetime]] = mapped_column()

    __table_args__ = (
        # 同一 NPC 在同一租户/站点下，版本号唯一
        UniqueConstraint(
            "tenant_id", "site_id", "npc_id", "version",
            name="uq_npc_prompt_version"
        ),
        # 同一 NPC 在同一租户/站点下，只能有一个 active
        Index(
            "ix_npc_prompt_active",
            "tenant_id", "site_id", "npc_id",
            postgresql_where="active = true AND deleted_at IS NULL"
        ),
    )

    def __repr__(self) -> str:
        return f"<NPCPrompt(npc_id={self.npc_id}, version={self.version}, active={self.active})>"
