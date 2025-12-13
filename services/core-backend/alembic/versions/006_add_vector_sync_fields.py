"""add vector sync fields

Revision ID: 006
Revises: 005
Create Date: 2025-12-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 为 evidences 表添加向量化状态字段
    op.add_column('evidences', sa.Column('vector_updated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('evidences', sa.Column('vector_hash', sa.String(64), nullable=True))
    op.create_index('ix_evidences_vector_updated_at', 'evidences', ['vector_updated_at'])

    # 2. 创建 vector_sync_jobs 表
    op.create_table(
        'vector_sync_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=False), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('tenant_id', sa.String(50), nullable=False, index=True),
        sa.Column('site_id', sa.String(50), nullable=True, index=True),
        sa.Column('job_type', sa.String(50), nullable=False, server_default='full_sync'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending', index=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_items', sa.Integer, nullable=False, server_default='0'),
        sa.Column('success_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('skip_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('failure_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('progress_percent', sa.Float, nullable=False, server_default='0'),
        sa.Column('current_batch', sa.Integer, nullable=False, server_default='0'),
        sa.Column('total_batches', sa.Integer, nullable=False, server_default='0'),
        sa.Column('error_summary', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('config', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('triggered_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('vector_sync_jobs')
    op.drop_index('ix_evidences_vector_updated_at', table_name='evidences')
    op.drop_column('evidences', 'vector_hash')
    op.drop_column('evidences', 'vector_updated_at')
