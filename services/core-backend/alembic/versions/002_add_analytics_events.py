"""Add analytics_events table

Revision ID: 002_analytics
Revises: 001_v0_1_0
Create Date: 2024-12-13

新增 analytics_events 表用于记录用户行为事件
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002_analytics'
down_revision: Union[str, None] = '001_v0_1_0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'analytics_events',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('site_id', sa.String(50), sa.ForeignKey('sites.id', ondelete='CASCADE'), nullable=False),
        # 追踪信息
        sa.Column('trace_id', sa.String(100)),
        sa.Column('session_id', sa.String(100)),
        # 用户信息
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='SET NULL')),
        # 事件信息
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('event_data', postgresql.JSONB, server_default='{}', nullable=False),
        # 设备信息
        sa.Column('device_type', sa.String(50)),
        sa.Column('device_id', sa.String(200)),
        sa.Column('user_agent', sa.Text),
        sa.Column('ip_address', sa.String(50)),
        # 位置信息
        sa.Column('location_lat', sa.Float),
        sa.Column('location_lng', sa.Float),
        # 时间
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 创建索引
    op.create_index('ix_analytics_events_tenant_id', 'analytics_events', ['tenant_id'])
    op.create_index('ix_analytics_events_site_id', 'analytics_events', ['site_id'])
    op.create_index('ix_analytics_events_trace_id', 'analytics_events', ['trace_id'])
    op.create_index('ix_analytics_events_session_id', 'analytics_events', ['session_id'])
    op.create_index('ix_analytics_events_user_id', 'analytics_events', ['user_id'])
    op.create_index('ix_analytics_events_event_type', 'analytics_events', ['event_type'])
    op.create_index('ix_analytics_events_created_at', 'analytics_events', ['created_at'])


def downgrade() -> None:
    op.drop_table('analytics_events')
