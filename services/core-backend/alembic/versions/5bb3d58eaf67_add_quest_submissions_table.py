"""add_quest_submissions_table

Revision ID: 5bb3d58eaf67
Revises: 011_add_refresh_tokens
Create Date: 2025-12-16 14:11:13.832676

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5bb3d58eaf67'
down_revision: Union[str, None] = '011_add_refresh_tokens'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 创建 quest_submissions 表
    op.create_table('quest_submissions',
        sa.Column('id', sa.UUID(as_uuid=False), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('session_id', sa.String(length=100), nullable=False),
        sa.Column('quest_id', sa.String(length=100), nullable=False),
        sa.Column('proof_type', sa.String(length=50), server_default='text', nullable=False),
        sa.Column('proof_payload', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('status', sa.String(length=20), server_default='submitted', nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('site_id', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 创建索引
    op.create_index('ix_quest_submissions_quest_id', 'quest_submissions', ['quest_id'], unique=False)
    op.create_index('ix_quest_submissions_session_id', 'quest_submissions', ['session_id'], unique=False)
    op.create_index('ix_quest_submissions_session_quest_created', 'quest_submissions', ['session_id', 'quest_id', 'created_at'], unique=False)
    op.create_index('ix_quest_submissions_site_id', 'quest_submissions', ['site_id'], unique=False)
    op.create_index('ix_quest_submissions_tenant_id', 'quest_submissions', ['tenant_id'], unique=False)
    op.create_index('ix_quest_submissions_tenant_site_session_quest', 'quest_submissions', ['tenant_id', 'site_id', 'session_id', 'quest_id'], unique=False)


def downgrade() -> None:
    # 删除索引
    op.drop_index('ix_quest_submissions_tenant_site_session_quest', table_name='quest_submissions')
    op.drop_index('ix_quest_submissions_tenant_id', table_name='quest_submissions')
    op.drop_index('ix_quest_submissions_site_id', table_name='quest_submissions')
    op.drop_index('ix_quest_submissions_session_quest_created', table_name='quest_submissions')
    op.drop_index('ix_quest_submissions_session_id', table_name='quest_submissions')
    op.drop_index('ix_quest_submissions_quest_id', table_name='quest_submissions')
    
    # 删除表
    op.drop_table('quest_submissions')
