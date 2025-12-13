"""Add pg_trgm extension and GIN indexes for evidence search

Revision ID: 004_add_pg_trgm_indexes
Revises: 003_add_npc_prompts
Create Date: 2024-12-13

This migration:
1. Enables pg_trgm extension for trigram similarity search
2. Adds GIN indexes on evidence.title and evidence.excerpt
3. Adds GIN indexes on content.title and content.body
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '004_add_pg_trgm_indexes'
down_revision = '003_npc_prompts'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Enable pg_trgm extension
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 2. Add GIN indexes for evidence table
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_evidences_title_trgm
        ON evidences USING GIN (title gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_evidences_excerpt_trgm
        ON evidences USING GIN (excerpt gin_trgm_ops)
    """)

    # 3. Add GIN indexes for content table
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_contents_title_trgm
        ON contents USING GIN (title gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_contents_body_trgm
        ON contents USING GIN (body gin_trgm_ops)
    """)

    # 4. Set default similarity threshold (optional, can be adjusted per query)
    # This sets a session-level default, actual queries will override as needed
    op.execute("SELECT set_limit(0.3)")


def downgrade() -> None:
    # Drop GIN indexes
    op.execute("DROP INDEX IF EXISTS ix_evidences_title_trgm")
    op.execute("DROP INDEX IF EXISTS ix_evidences_excerpt_trgm")
    op.execute("DROP INDEX IF EXISTS ix_contents_title_trgm")
    op.execute("DROP INDEX IF EXISTS ix_contents_body_trgm")

    # Note: We don't drop the pg_trgm extension as other things might depend on it
