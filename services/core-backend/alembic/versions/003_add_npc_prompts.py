"""Add npc_prompts table

Revision ID: 003_npc_prompts
Revises: 002_analytics
Create Date: 2024-12-13

新增 npc_prompts 表用于可版本化的 Prompt 资产管理
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003_npc_prompts'
down_revision: Union[str, None] = '002_analytics'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'npc_prompts',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('site_id', sa.String(50), sa.ForeignKey('sites.id', ondelete='CASCADE'), nullable=False),
        # NPC 关联
        sa.Column('npc_id', sa.String(100), nullable=False),
        # 版本信息
        sa.Column('version', sa.Integer, nullable=False, default=1),
        sa.Column('active', sa.Boolean, default=False),
        # Prompt 内容
        sa.Column('content', sa.Text, nullable=False),
        # 元数据和策略
        sa.Column('meta', postgresql.JSONB, server_default='{}', nullable=False),
        sa.Column('policy', postgresql.JSONB, server_default='{}', nullable=False),
        # 审计信息
        sa.Column('author', sa.String(100)),
        sa.Column('operator_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('description', sa.Text),
        # 时间戳
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
    )

    # 创建索引
    op.create_index('ix_npc_prompts_tenant_id', 'npc_prompts', ['tenant_id'])
    op.create_index('ix_npc_prompts_site_id', 'npc_prompts', ['site_id'])
    op.create_index('ix_npc_prompts_npc_id', 'npc_prompts', ['npc_id'])
    op.create_index('ix_npc_prompts_active', 'npc_prompts', ['active'])

    # 唯一约束：同一 NPC 在同一租户/站点下，版本号唯一
    op.create_unique_constraint(
        'uq_npc_prompt_version',
        'npc_prompts',
        ['tenant_id', 'site_id', 'npc_id', 'version']
    )

    # 部分索引：同一 NPC 在同一租户/站点下，只能有一个 active（PostgreSQL 特有）
    op.execute("""
        CREATE UNIQUE INDEX ix_npc_prompt_single_active
        ON npc_prompts (tenant_id, site_id, npc_id)
        WHERE active = true AND deleted_at IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_npc_prompt_single_active")
    op.drop_table('npc_prompts')
