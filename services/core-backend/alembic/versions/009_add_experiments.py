"""add experiments tables

Revision ID: 009
Revises: 008
Create Date: 2025-12-14

新增 A/B 实验表：
- experiments: 实验定义
- experiment_assignments: 分桶记录
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # experiments 表
    op.create_table(
        'experiments',
        sa.Column('id', UUID(as_uuid=False), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('tenant_id', sa.String(100), nullable=False),
        sa.Column('site_id', sa.String(100), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('status', sa.String(20), server_default='draft', nullable=False),
        sa.Column('config', JSONB, server_default='{}', nullable=False),
        sa.Column('start_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_experiments_tenant_id', 'experiments', ['tenant_id'])
    op.create_index('ix_experiments_site_id', 'experiments', ['site_id'])
    op.create_index('ix_experiments_status', 'experiments', ['status'])
    op.create_index('ix_experiments_tenant_site_status', 'experiments', ['tenant_id', 'site_id', 'status'])
    
    # experiment_assignments 表
    op.create_table(
        'experiment_assignments',
        sa.Column('id', UUID(as_uuid=False), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('experiment_id', UUID(as_uuid=False), sa.ForeignKey('experiments.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', sa.String(100), nullable=False),
        sa.Column('site_id', sa.String(100), nullable=False),
        sa.Column('subject_type', sa.String(20), nullable=False),
        sa.Column('subject_key', sa.String(200), nullable=False),
        sa.Column('variant', sa.String(100), nullable=False),
        sa.Column('bucket_hash', sa.Integer, nullable=False),
        sa.Column('strategy_overrides', JSONB, server_default='{}', nullable=False),
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_experiment_assignments_experiment_id', 'experiment_assignments', ['experiment_id'])
    op.create_index('ix_experiment_assignments_tenant_id', 'experiment_assignments', ['tenant_id'])
    op.create_index('ix_experiment_assignments_site_id', 'experiment_assignments', ['site_id'])
    op.create_index('ix_experiment_assignments_subject_key', 'experiment_assignments', ['subject_key'])
    op.create_index('ix_experiment_assignments_variant', 'experiment_assignments', ['variant'])
    # 唯一约束：同一实验中同一 subject 只能有一个分配
    op.create_index(
        'ix_experiment_assignments_unique',
        'experiment_assignments',
        ['experiment_id', 'subject_key'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table('experiment_assignments')
    op.drop_table('experiments')
