"""add feedback workflow fields

Revision ID: 008
Revises: 007
Create Date: 2025-12-14

为 user_feedbacks 表添加工单化字段：
- assignee, group: 分派信息
- sla_due_at, overdue_flag: SLA
- triaged_at, in_progress_at, closed_at: 状态时间戳
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 分派信息
    op.add_column('user_feedbacks', sa.Column('assignee', sa.String(100), nullable=True))
    op.add_column('user_feedbacks', sa.Column('group', sa.String(100), nullable=True))
    
    # SLA
    op.add_column('user_feedbacks', sa.Column('sla_due_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('user_feedbacks', sa.Column('overdue_flag', sa.Boolean, server_default='false', nullable=False))
    
    # 状态时间戳
    op.add_column('user_feedbacks', sa.Column('triaged_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('user_feedbacks', sa.Column('in_progress_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('user_feedbacks', sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True))
    
    # 索引
    op.create_index('ix_user_feedbacks_assignee', 'user_feedbacks', ['assignee'])
    op.create_index('ix_user_feedbacks_group', 'user_feedbacks', ['group'])
    op.create_index('ix_user_feedbacks_sla_due_at', 'user_feedbacks', ['sla_due_at'])
    op.create_index('ix_user_feedbacks_overdue_flag', 'user_feedbacks', ['overdue_flag'])
    
    # 复合索引用于 overdue 扫描
    op.create_index(
        'ix_user_feedbacks_overdue_scan',
        'user_feedbacks',
        ['status', 'sla_due_at', 'overdue_flag']
    )


def downgrade() -> None:
    op.drop_index('ix_user_feedbacks_overdue_scan', table_name='user_feedbacks')
    op.drop_index('ix_user_feedbacks_overdue_flag', table_name='user_feedbacks')
    op.drop_index('ix_user_feedbacks_sla_due_at', table_name='user_feedbacks')
    op.drop_index('ix_user_feedbacks_group', table_name='user_feedbacks')
    op.drop_index('ix_user_feedbacks_assignee', table_name='user_feedbacks')
    
    op.drop_column('user_feedbacks', 'closed_at')
    op.drop_column('user_feedbacks', 'in_progress_at')
    op.drop_column('user_feedbacks', 'triaged_at')
    op.drop_column('user_feedbacks', 'overdue_flag')
    op.drop_column('user_feedbacks', 'sla_due_at')
    op.drop_column('user_feedbacks', 'group')
    op.drop_column('user_feedbacks', 'assignee')
