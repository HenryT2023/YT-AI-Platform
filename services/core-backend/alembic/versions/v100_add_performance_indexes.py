"""v1.0.0 添加性能优化索引

Revision ID: v100_perf_indexes
Revises: 
Create Date: 2024-12-20

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'v100_perf_indexes'
down_revision = 'b96da687dc6b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """添加性能优化索引"""

    # ============================================================
    # 任务表索引
    # ============================================================
    op.create_index(
        'idx_quests_tenant_site_status',
        'quests',
        ['tenant_id', 'site_id', 'status'],
        if_not_exists=True,
    )
    op.create_index(
        'idx_quests_category',
        'quests',
        ['tenant_id', 'site_id', 'category'],
        if_not_exists=True,
    )

    # ============================================================
    # 游客画像索引
    # ============================================================
    op.create_index(
        'idx_visitor_profiles_user',
        'visitor_profiles',
        ['tenant_id', 'site_id', 'user_id'],
        if_not_exists=True,
    )
    op.create_index(
        'idx_visitor_profiles_updated',
        'visitor_profiles',
        ['updated_at'],
        if_not_exists=True,
    )

    # ============================================================
    # 对话表索引
    # ============================================================
    op.create_index(
        'idx_conversations_user',
        'conversations',
        ['tenant_id', 'site_id', 'user_id'],
        if_not_exists=True,
    )
    op.create_index(
        'idx_conversations_npc',
        'conversations',
        ['tenant_id', 'site_id', 'npc_id'],
        if_not_exists=True,
    )
    op.create_index(
        'idx_conversations_session',
        'conversations',
        ['session_id'],
        if_not_exists=True,
    )

    # ============================================================
    # 消息表索引
    # ============================================================
    op.create_index(
        'idx_messages_conversation',
        'messages',
        ['conversation_id', 'created_at'],
        if_not_exists=True,
    )

    # ============================================================
    # NPC 表索引
    # ============================================================
    op.create_index(
        'idx_npc_profiles_tenant_site',
        'npc_profiles',
        ['tenant_id', 'site_id', 'status'],
        if_not_exists=True,
    )
    op.create_index(
        'idx_npc_profiles_npc_id',
        'npc_profiles',
        ['npc_id'],
        if_not_exists=True,
    )

    # ============================================================
    # 成就表索引
    # ============================================================
    op.create_index(
        'idx_achievements_tenant_site',
        'achievements',
        ['tenant_id', 'site_id', 'category'],
        if_not_exists=True,
    )
    op.create_index(
        'idx_user_achievements_user',
        'user_achievements',
        ['tenant_id', 'site_id', 'user_id'],
        if_not_exists=True,
    )

    # ============================================================
    # 打卡表索引
    # ============================================================
    op.create_index(
        'idx_visitor_checkins_profile_time',
        'visitor_check_ins',
        ['tenant_id', 'site_id', 'profile_id', 'check_in_at'],
        if_not_exists=True,
    )

    # ============================================================
    # 内容表索引
    # ============================================================
    op.create_index(
        'idx_contents_tenant_site_status',
        'contents',
        ['tenant_id', 'site_id', 'status'],
        if_not_exists=True,
    )
    op.create_index(
        'idx_contents_type',
        'contents',
        ['tenant_id', 'site_id', 'content_type'],
        if_not_exists=True,
    )

    # ============================================================
    # 农耕知识索引
    # ============================================================
    op.create_index(
        'idx_farming_knowledge_solar_term',
        'farming_knowledge',
        ['tenant_id', 'site_id', 'solar_term_code'],
        if_not_exists=True,
    )
    op.create_index(
        'idx_farming_knowledge_category',
        'farming_knowledge',
        ['tenant_id', 'site_id', 'category'],
        if_not_exists=True,
    )


def downgrade() -> None:
    """删除索引"""
    indexes = [
        ('idx_quests_tenant_site_status', 'quests'),
        ('idx_quests_category', 'quests'),
        ('idx_visitor_profiles_user', 'visitor_profiles'),
        ('idx_visitor_profiles_updated', 'visitor_profiles'),
        ('idx_conversations_user', 'conversations'),
        ('idx_conversations_npc', 'conversations'),
        ('idx_conversations_session', 'conversations'),
        ('idx_messages_conversation', 'messages'),
        ('idx_npc_profiles_tenant_site', 'npc_profiles'),
        ('idx_npc_profiles_npc_id', 'npc_profiles'),
        ('idx_achievements_tenant_site', 'achievements'),
        ('idx_user_achievements_user', 'user_achievements'),
        ('idx_visitor_checkins_profile_time', 'visitor_check_ins'),
        ('idx_contents_tenant_site_status', 'contents'),
        ('idx_contents_type', 'contents'),
        ('idx_farming_knowledge_solar_term', 'farming_knowledge'),
        ('idx_farming_knowledge_category', 'farming_knowledge'),
    ]

    for index_name, table_name in indexes:
        op.drop_index(index_name, table_name=table_name, if_exists=True)
