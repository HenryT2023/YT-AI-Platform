"""P27: Release Gate tables and trace release_id

Revision ID: p27_release_gate
Revises: p26_admin_audit_policy
Create Date: 2024-12-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'p27_release_gate'
down_revision = 'p26_admin_audit_policy'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建 releases 表
    op.create_table(
        'releases',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(100), nullable=False, index=True),
        sa.Column('site_id', sa.String(100), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('status', sa.String(20), nullable=False, index=True),
        sa.Column('payload', postgresql.JSONB, nullable=False),
        sa.Column('created_by', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, index=True),
        sa.Column('activated_at', sa.DateTime, nullable=True),
        sa.Column('archived_at', sa.DateTime, nullable=True),
    )
    
    # 创建复合索引
    op.create_index(
        'ix_releases_tenant_site_status',
        'releases',
        ['tenant_id', 'site_id', 'status'],
    )
    
    # 创建 release_history 表
    op.create_table(
        'release_history',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('release_id', sa.String(36), nullable=False, index=True),
        sa.Column('tenant_id', sa.String(100), nullable=False, index=True),
        sa.Column('site_id', sa.String(100), nullable=False, index=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('previous_release_id', sa.String(36), nullable=True),
        sa.Column('operator', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, index=True),
    )
    
    # 添加 release_id 到 trace_ledger
    op.add_column(
        'trace_ledger',
        sa.Column('release_id', postgresql.UUID(as_uuid=False), nullable=True, index=True),
    )
    op.create_index('ix_trace_ledger_release_id', 'trace_ledger', ['release_id'])


def downgrade() -> None:
    op.drop_index('ix_trace_ledger_release_id', table_name='trace_ledger')
    op.drop_column('trace_ledger', 'release_id')
    op.drop_table('release_history')
    op.drop_index('ix_releases_tenant_site_status', table_name='releases')
    op.drop_table('releases')
