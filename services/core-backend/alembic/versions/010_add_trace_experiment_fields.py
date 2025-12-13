"""add trace experiment fields

Revision ID: 010
Revises: 009
Create Date: 2025-12-14

为 trace_ledger 表添加 A/B 实验字段：
- experiment_id
- experiment_variant
- strategy_snapshot
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = '010'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('trace_ledger', sa.Column('experiment_id', UUID(as_uuid=False), nullable=True))
    op.add_column('trace_ledger', sa.Column('experiment_variant', sa.String(100), nullable=True))
    op.add_column('trace_ledger', sa.Column('strategy_snapshot', JSONB, server_default='{}', nullable=False))
    
    op.create_index('ix_trace_ledger_experiment_id', 'trace_ledger', ['experiment_id'])
    op.create_index('ix_trace_ledger_experiment_variant', 'trace_ledger', ['experiment_variant'])
    op.create_index('ix_trace_ledger_experiment_variant_combo', 'trace_ledger', ['experiment_id', 'experiment_variant'])


def downgrade() -> None:
    op.drop_index('ix_trace_ledger_experiment_variant_combo', table_name='trace_ledger')
    op.drop_index('ix_trace_ledger_experiment_variant', table_name='trace_ledger')
    op.drop_index('ix_trace_ledger_experiment_id', table_name='trace_ledger')
    
    op.drop_column('trace_ledger', 'strategy_snapshot')
    op.drop_column('trace_ledger', 'experiment_variant')
    op.drop_column('trace_ledger', 'experiment_id')
