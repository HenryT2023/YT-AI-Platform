"""P28: 告警事件与静默表

Revision ID: p28_alerts_events
Revises: p27_release_gate
Create Date: 2024-12-14

新增表:
- alerts_events: 告警事件历史
- alerts_silences: 告警静默规则
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "p28_alerts_events"
down_revision = "p27_release_gate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建告警状态枚举
    alert_status_enum = sa.Enum("firing", "resolved", name="alert_status")
    alert_status_enum.create(op.get_bind(), checkfirst=True)
    
    # 创建 alerts_events 表
    op.create_table(
        "alerts_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("site_id", sa.String(64), nullable=True),
        sa.Column("alert_code", sa.String(128), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("status", alert_status_enum, nullable=False, server_default="firing"),
        sa.Column("window", sa.String(16), nullable=False, server_default="15m"),
        sa.Column("current_value", sa.Float, nullable=True),
        sa.Column("threshold", sa.Float, nullable=True),
        sa.Column("condition", sa.String(16), nullable=True),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("dedup_key", sa.String(256), nullable=False),
        sa.Column("first_seen_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("context", JSONB, nullable=False, server_default="{}"),
        sa.Column("webhook_sent", sa.String(16), nullable=True),
        sa.Column("webhook_sent_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    
    # alerts_events 索引
    op.create_index("ix_alerts_events_tenant_id", "alerts_events", ["tenant_id"])
    op.create_index("ix_alerts_events_site_id", "alerts_events", ["site_id"])
    op.create_index("ix_alerts_events_alert_code", "alerts_events", ["alert_code"])
    op.create_index("ix_alerts_events_severity", "alerts_events", ["severity"])
    op.create_index("ix_alerts_events_status", "alerts_events", ["status"])
    op.create_index("ix_alerts_events_dedup_key", "alerts_events", ["dedup_key"])
    op.create_index("ix_alerts_events_tenant_status", "alerts_events", ["tenant_id", "status"])
    op.create_index("ix_alerts_events_dedup_status", "alerts_events", ["dedup_key", "status"])
    op.create_index("ix_alerts_events_first_seen", "alerts_events", ["first_seen_at"])
    
    # 创建 alerts_silences 表
    op.create_table(
        "alerts_silences",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("site_id", sa.String(64), nullable=True),
        sa.Column("alert_code", sa.String(128), nullable=True),
        sa.Column("severity", sa.String(32), nullable=True),
        sa.Column("starts_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("ends_at", sa.DateTime, nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False, server_default="admin_console"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    
    # alerts_silences 索引
    op.create_index("ix_alerts_silences_tenant_id", "alerts_silences", ["tenant_id"])
    op.create_index("ix_alerts_silences_site_id", "alerts_silences", ["site_id"])
    op.create_index("ix_alerts_silences_alert_code", "alerts_silences", ["alert_code"])
    op.create_index("ix_alerts_silences_severity", "alerts_silences", ["severity"])
    op.create_index("ix_alerts_silences_tenant_active", "alerts_silences", ["tenant_id", "starts_at", "ends_at"])


def downgrade() -> None:
    op.drop_table("alerts_silences")
    op.drop_table("alerts_events")
    
    # 删除枚举
    alert_status_enum = sa.Enum("firing", "resolved", name="alert_status")
    alert_status_enum.drop(op.get_bind(), checkfirst=True)
