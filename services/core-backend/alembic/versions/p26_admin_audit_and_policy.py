"""P26: Admin audit log and policy tables

Revision ID: p26_admin_audit_policy
Revises: 
Create Date: 2024-12-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'p26_admin_audit_policy'
down_revision = None  # 需要根据实际情况设置
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建 admin_audit_log 表
    op.create_table(
        'admin_audit_log',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('actor', sa.String(255), nullable=False, index=True),
        sa.Column('action', sa.String(100), nullable=False, index=True),
        sa.Column('target_type', sa.String(100), nullable=False, index=True),
        sa.Column('target_id', sa.String(255), nullable=True),
        sa.Column('payload', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, index=True),
    )
    
    # 创建 policies 表
    op.create_table(
        'policies',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, index=True),
        sa.Column('version', sa.String(50), nullable=False, index=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('content', postgresql.JSONB, nullable=False),
        sa.Column('is_active', sa.Boolean, default=False, nullable=False, index=True),
        sa.Column('operator', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, index=True),
    )
    
    # 创建复合索引
    op.create_index(
        'ix_policies_name_version',
        'policies',
        ['name', 'version'],
        unique=True,
    )
    op.create_index(
        'ix_policies_name_active',
        'policies',
        ['name', 'is_active'],
    )


def downgrade() -> None:
    op.drop_index('ix_policies_name_active', table_name='policies')
    op.drop_index('ix_policies_name_version', table_name='policies')
    op.drop_table('policies')
    op.drop_table('admin_audit_log')
