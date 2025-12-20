"""merge_v100_indexes

Revision ID: aedc19269759
Revises: ae727f3d9b63, v100_perf_indexes
Create Date: 2025-12-20 17:43:57.271428

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aedc19269759'
down_revision: Union[str, None] = ('ae727f3d9b63', 'v100_perf_indexes')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
