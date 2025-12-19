"""add_review_fields_to_quest_submissions

Revision ID: 71cb7030dab0
Revises: 5bb3d58eaf67
Create Date: 2025-12-17 23:36:52.761073

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '71cb7030dab0'
down_revision: Union[str, None] = '5bb3d58eaf67'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 添加审核流程字段到 quest_submissions 表
    op.add_column('quest_submissions', sa.Column('review_status', sa.String(length=20), server_default='pending', nullable=False))
    op.add_column('quest_submissions', sa.Column('review_comment', sa.Text(), nullable=True))
    op.add_column('quest_submissions', sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('quest_submissions', sa.Column('reviewed_by', sa.String(length=100), nullable=True))
    op.create_index(op.f('ix_quest_submissions_review_status'), 'quest_submissions', ['review_status'], unique=False)


def downgrade() -> None:
    # 删除审核流程字段
    op.drop_index(op.f('ix_quest_submissions_review_status'), table_name='quest_submissions')
    op.drop_column('quest_submissions', 'reviewed_by')
    op.drop_column('quest_submissions', 'reviewed_at')
    op.drop_column('quest_submissions', 'review_comment')
    op.drop_column('quest_submissions', 'review_status')
