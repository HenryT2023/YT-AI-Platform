"""merge_p28_alerts

Revision ID: b96da687dc6b
Revises: 010, p28_alerts_events
Create Date: 2025-12-14 17:53:49.522893

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b96da687dc6b'
down_revision: Union[str, None] = ('010', 'p28_alerts_events')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
