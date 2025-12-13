"""add feedback fields

Revision ID: 005
Revises: 004
Create Date: 2024-12-13

新增 user_feedbacks 表字段：
- severity
- suggested_fix
- resolved_by_content_id
- resolved_by_evidence_id
- resolved_at
- resolved_by
- resolution_notes
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 新增 severity 字段
    op.add_column(
        "user_feedbacks",
        sa.Column("severity", sa.String(20), server_default="medium", nullable=False),
    )
    op.create_index("ix_user_feedbacks_severity", "user_feedbacks", ["severity"])

    # 新增 suggested_fix 字段
    op.add_column(
        "user_feedbacks",
        sa.Column("suggested_fix", sa.Text(), nullable=True),
    )

    # 新增解决关联字段
    op.add_column(
        "user_feedbacks",
        sa.Column("resolved_by_content_id", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.add_column(
        "user_feedbacks",
        sa.Column("resolved_by_evidence_id", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.add_column(
        "user_feedbacks",
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "user_feedbacks",
        sa.Column("resolved_by", sa.String(100), nullable=True),
    )
    op.add_column(
        "user_feedbacks",
        sa.Column("resolution_notes", sa.Text(), nullable=True),
    )

    # 创建索引
    op.create_index(
        "ix_user_feedbacks_resolved_by_content_id",
        "user_feedbacks",
        ["resolved_by_content_id"],
    )
    op.create_index(
        "ix_user_feedbacks_resolved_by_evidence_id",
        "user_feedbacks",
        ["resolved_by_evidence_id"],
    )

    # 创建外键（如果 contents 和 evidences 表存在）
    # 注意：这里使用 try-except 因为表可能不存在
    try:
        op.create_foreign_key(
            "fk_user_feedbacks_content",
            "user_feedbacks",
            "contents",
            ["resolved_by_content_id"],
            ["id"],
            ondelete="SET NULL",
        )
    except Exception:
        pass

    try:
        op.create_foreign_key(
            "fk_user_feedbacks_evidence",
            "user_feedbacks",
            "evidences",
            ["resolved_by_evidence_id"],
            ["id"],
            ondelete="SET NULL",
        )
    except Exception:
        pass


def downgrade() -> None:
    # 删除外键
    try:
        op.drop_constraint("fk_user_feedbacks_content", "user_feedbacks", type_="foreignkey")
    except Exception:
        pass

    try:
        op.drop_constraint("fk_user_feedbacks_evidence", "user_feedbacks", type_="foreignkey")
    except Exception:
        pass

    # 删除索引
    op.drop_index("ix_user_feedbacks_resolved_by_evidence_id", "user_feedbacks")
    op.drop_index("ix_user_feedbacks_resolved_by_content_id", "user_feedbacks")
    op.drop_index("ix_user_feedbacks_severity", "user_feedbacks")

    # 删除字段
    op.drop_column("user_feedbacks", "resolution_notes")
    op.drop_column("user_feedbacks", "resolved_by")
    op.drop_column("user_feedbacks", "resolved_at")
    op.drop_column("user_feedbacks", "resolved_by_evidence_id")
    op.drop_column("user_feedbacks", "resolved_by_content_id")
    op.drop_column("user_feedbacks", "suggested_fix")
    op.drop_column("user_feedbacks", "severity")
