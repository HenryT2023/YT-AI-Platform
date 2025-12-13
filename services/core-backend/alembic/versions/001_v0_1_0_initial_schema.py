"""v0.1.0 Initial Schema

Revision ID: 001_v0_1_0
Revises: 
Create Date: 2024-12-13

创建 v0.1.0 数据库底座：
- tenants: 租户表（全局）
- sites: 站点表
- users: 用户表（支持微信小程序）
- contents: 内容表（知识库、故事等）
- npc_profiles: NPC 人设表（版本化）
- quests: 研学任务表
- quest_steps: 任务步骤表
- evidences: 证据表
- conversations: 会话表
- messages: 消息表
- trace_ledger: 证据链账本
- user_feedbacks: 用户反馈表
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_v0_1_0'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================
    # 1. tenants - 租户表（全局表，无 tenant_id）
    # ==========================================
    op.create_table(
        'tenants',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('display_name', sa.String(200)),
        sa.Column('description', sa.Text),
        sa.Column('config', postgresql.JSONB, server_default='{}', nullable=False),
        sa.Column('plan', sa.String(50), server_default='free', nullable=False),
        sa.Column('quota', postgresql.JSONB, server_default='{}', nullable=False),
        sa.Column('contact_email', sa.String(200)),
        sa.Column('contact_phone', sa.String(50)),
        sa.Column('status', sa.String(20), server_default='active', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('created_by', sa.String(100)),
        sa.Column('updated_by', sa.String(100)),
    )
    op.create_index('ix_tenants_status', 'tenants', ['status'])

    # ==========================================
    # 2. sites - 站点表
    # ==========================================
    op.create_table(
        'sites',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('display_name', sa.String(200)),
        sa.Column('description', sa.Text),
        sa.Column('config', postgresql.JSONB, server_default='{}', nullable=False),
        sa.Column('theme', postgresql.JSONB, server_default='{}', nullable=False),
        sa.Column('location_lat', sa.Float),
        sa.Column('location_lng', sa.Float),
        sa.Column('timezone', sa.String(50), server_default='Asia/Shanghai'),
        sa.Column('status', sa.String(20), server_default='active', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('created_by', sa.String(100)),
        sa.Column('updated_by', sa.String(100)),
    )
    op.create_index('ix_sites_tenant_id', 'sites', ['tenant_id'])
    op.create_index('ix_sites_status', 'sites', ['status'])

    # ==========================================
    # 3. users - 用户表
    # ==========================================
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenants.id', ondelete='CASCADE')),
        sa.Column('username', sa.String(100), unique=True),
        sa.Column('email', sa.String(200), unique=True),
        sa.Column('phone', sa.String(50), unique=True),
        sa.Column('hashed_password', sa.String(200)),
        # 微信小程序字段
        sa.Column('wx_openid', sa.String(100), unique=True),
        sa.Column('wx_unionid', sa.String(100)),
        sa.Column('wx_session_key', sa.String(200)),
        # 用户信息
        sa.Column('display_name', sa.String(200)),
        sa.Column('avatar_url', sa.String(500)),
        sa.Column('profile', postgresql.JSONB, server_default='{}', nullable=False),
        # 角色与权限
        sa.Column('role', sa.String(50), server_default='visitor', nullable=False),
        sa.Column('permissions', postgresql.ARRAY(sa.String), server_default='{}', nullable=False),
        sa.Column('allowed_site_ids', postgresql.ARRAY(sa.String(50))),
        # 状态
        sa.Column('is_active', sa.Boolean, server_default='true', nullable=False),
        sa.Column('is_verified', sa.Boolean, server_default='false', nullable=False),
        sa.Column('status', sa.String(20), server_default='active', nullable=False),
        # 登录信息
        sa.Column('last_login_at', sa.DateTime(timezone=True)),
        sa.Column('last_login_ip', sa.String(50)),
        # 审计
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('created_by', sa.String(100)),
        sa.Column('updated_by', sa.String(100)),
    )
    op.create_index('ix_users_tenant_id', 'users', ['tenant_id'])
    op.create_index('ix_users_username', 'users', ['username'])
    op.create_index('ix_users_email', 'users', ['email'])
    op.create_index('ix_users_phone', 'users', ['phone'])
    op.create_index('ix_users_wx_openid', 'users', ['wx_openid'])
    op.create_index('ix_users_wx_unionid', 'users', ['wx_unionid'])
    op.create_index('ix_users_role', 'users', ['role'])

    # ==========================================
    # 4. contents - 内容表
    # ==========================================
    op.create_table(
        'contents',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('site_id', sa.String(50), sa.ForeignKey('sites.id', ondelete='CASCADE'), nullable=False),
        # 类型
        sa.Column('content_type', sa.String(50), nullable=False),
        # 基本信息
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('slug', sa.String(200)),
        sa.Column('summary', sa.Text),
        sa.Column('body', sa.Text, nullable=False),
        # 分类
        sa.Column('category', sa.String(100)),
        sa.Column('tags', postgresql.ARRAY(sa.String), server_default='{}', nullable=False),
        sa.Column('domains', postgresql.ARRAY(sa.String), server_default='{}', nullable=False),
        # 来源
        sa.Column('source', sa.Text),
        sa.Column('source_url', sa.String(1000)),
        sa.Column('source_date', sa.DateTime(timezone=True)),
        sa.Column('credibility_score', sa.Float, server_default='1.0', nullable=False),
        # 验证
        sa.Column('verified', sa.Boolean, server_default='false', nullable=False),
        sa.Column('verified_by', sa.String(100)),
        sa.Column('verified_at', sa.DateTime(timezone=True)),
        # 向量化
        sa.Column('embedding_model', sa.String(100)),
        sa.Column('embedding_id', sa.String(200)),
        sa.Column('embedded_at', sa.DateTime(timezone=True)),
        # 全文搜索
        sa.Column('search_vector', postgresql.TSVECTOR),
        # 元数据
        sa.Column('metadata', postgresql.JSONB, server_default='{}', nullable=False),
        # 统计
        sa.Column('view_count', sa.Integer, server_default='0', nullable=False),
        sa.Column('citation_count', sa.Integer, server_default='0', nullable=False),
        # 状态
        sa.Column('status', sa.String(20), server_default='draft', nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True)),
        sa.Column('published_by', sa.String(100)),
        sa.Column('sort_order', sa.Integer, server_default='0', nullable=False),
        # 审计
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('created_by', sa.String(100)),
        sa.Column('updated_by', sa.String(100)),
    )
    op.create_index('ix_contents_tenant_id', 'contents', ['tenant_id'])
    op.create_index('ix_contents_site_id', 'contents', ['site_id'])
    op.create_index('ix_contents_content_type', 'contents', ['content_type'])
    op.create_index('ix_contents_status', 'contents', ['status'])
    op.create_index('ix_contents_slug', 'contents', ['slug'])
    op.create_index('ix_contents_search_vector', 'contents', ['search_vector'], postgresql_using='gin')

    # ==========================================
    # 5. npc_profiles - NPC 人设表（版本化）
    # ==========================================
    op.create_table(
        'npc_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('site_id', sa.String(50), sa.ForeignKey('sites.id', ondelete='CASCADE'), nullable=False),
        # NPC 标识与版本
        sa.Column('npc_id', sa.String(100), nullable=False),
        sa.Column('version', sa.Integer, server_default='1', nullable=False),
        sa.Column('active', sa.Boolean, server_default='true', nullable=False),
        # 基本信息
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('display_name', sa.String(200)),
        sa.Column('npc_type', sa.String(50)),
        sa.Column('avatar_url', sa.String(500)),
        # 人设配置
        sa.Column('persona', postgresql.JSONB, server_default='{}', nullable=False),
        # 身份
        sa.Column('era', sa.String(100)),
        sa.Column('role', sa.String(200)),
        sa.Column('background', sa.Text),
        # 性格
        sa.Column('personality_traits', postgresql.ARRAY(sa.String), server_default='{}', nullable=False),
        sa.Column('speaking_style', sa.Text),
        sa.Column('tone', sa.String(50)),
        sa.Column('catchphrases', postgresql.ARRAY(sa.String), server_default='{}', nullable=False),
        # 知识领域
        sa.Column('knowledge_domains', postgresql.ARRAY(sa.String), server_default='{}', nullable=False),
        # 对话配置
        sa.Column('greeting_templates', postgresql.ARRAY(sa.String), server_default='{}', nullable=False),
        sa.Column('fallback_responses', postgresql.ARRAY(sa.String), server_default='{}', nullable=False),
        sa.Column('max_response_length', sa.Integer, server_default='500', nullable=False),
        # 约束
        sa.Column('forbidden_topics', postgresql.ARRAY(sa.String), server_default='{}', nullable=False),
        sa.Column('must_cite_sources', sa.Boolean, server_default='true', nullable=False),
        sa.Column('time_awareness', sa.String(50)),
        # 语音
        sa.Column('voice_id', sa.String(100)),
        sa.Column('voice_config', postgresql.JSONB, server_default='{}', nullable=False),
        # 状态
        sa.Column('status', sa.String(20), server_default='active', nullable=False),
        # 审计
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('created_by', sa.String(100)),
        sa.Column('updated_by', sa.String(100)),
    )
    op.create_index('ix_npc_profiles_tenant_id', 'npc_profiles', ['tenant_id'])
    op.create_index('ix_npc_profiles_site_id', 'npc_profiles', ['site_id'])
    op.create_index('ix_npc_profiles_npc_id', 'npc_profiles', ['npc_id'])
    op.create_index('ix_npc_profiles_active', 'npc_profiles', ['active'])
    # 唯一约束：同一 npc_id + version 只能有一条记录
    op.create_unique_constraint('uq_npc_profiles_npc_id_version', 'npc_profiles', ['npc_id', 'version'])

    # ==========================================
    # 6. quests - 研学任务表
    # ==========================================
    op.create_table(
        'quests',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('site_id', sa.String(50), sa.ForeignKey('sites.id', ondelete='CASCADE'), nullable=False),
        # 基本信息
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('display_name', sa.String(200)),
        sa.Column('description', sa.Text),
        # 类型
        sa.Column('quest_type', sa.String(50)),
        sa.Column('category', sa.String(100)),
        sa.Column('tags', postgresql.ARRAY(sa.String), server_default='{}', nullable=False),
        # 难度
        sa.Column('difficulty', sa.String(20)),
        sa.Column('estimated_duration_minutes', sa.Integer),
        # 奖励
        sa.Column('rewards', postgresql.JSONB, server_default='{}', nullable=False),
        sa.Column('prerequisites', postgresql.JSONB, server_default='{}', nullable=False),
        # 关联
        sa.Column('scene_ids', postgresql.ARRAY(sa.String), server_default='{}', nullable=False),
        sa.Column('config', postgresql.JSONB, server_default='{}', nullable=False),
        # 状态
        sa.Column('status', sa.String(20), server_default='active', nullable=False),
        sa.Column('sort_order', sa.Integer, server_default='0', nullable=False),
        # 审计
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('created_by', sa.String(100)),
        sa.Column('updated_by', sa.String(100)),
    )
    op.create_index('ix_quests_tenant_id', 'quests', ['tenant_id'])
    op.create_index('ix_quests_site_id', 'quests', ['site_id'])

    # ==========================================
    # 7. quest_steps - 任务步骤表
    # ==========================================
    op.create_table(
        'quest_steps',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('site_id', sa.String(50), sa.ForeignKey('sites.id', ondelete='CASCADE'), nullable=False),
        sa.Column('quest_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('quests.id', ondelete='CASCADE'), nullable=False),
        # 步骤信息
        sa.Column('step_number', sa.Integer, nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('step_type', sa.String(50), nullable=False),
        # 配置
        sa.Column('target_config', postgresql.JSONB, server_default='{}', nullable=False),
        sa.Column('validation_config', postgresql.JSONB, server_default='{}', nullable=False),
        sa.Column('hints', postgresql.ARRAY(sa.String), server_default='{}', nullable=False),
        sa.Column('rewards', postgresql.JSONB, server_default='{}', nullable=False),
        # 审计
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('created_by', sa.String(100)),
        sa.Column('updated_by', sa.String(100)),
    )
    op.create_index('ix_quest_steps_quest_id', 'quest_steps', ['quest_id'])

    # ==========================================
    # 8. evidences - 证据表
    # ==========================================
    op.create_table(
        'evidences',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('site_id', sa.String(50), sa.ForeignKey('sites.id', ondelete='CASCADE'), nullable=False),
        # 来源
        sa.Column('source_type', sa.String(50), nullable=False),
        sa.Column('source_ref', sa.String(200)),
        sa.Column('source_url', sa.String(1000)),
        # 内容
        sa.Column('title', sa.String(500)),
        sa.Column('excerpt', sa.Text, nullable=False),
        sa.Column('excerpt_hash', sa.String(64)),
        # 可信度
        sa.Column('confidence', sa.Float, server_default='1.0', nullable=False),
        # 验证
        sa.Column('verified', sa.Boolean, server_default='false', nullable=False),
        sa.Column('verified_by', sa.String(100)),
        sa.Column('verified_at', sa.DateTime(timezone=True)),
        # 分类
        sa.Column('tags', postgresql.ARRAY(sa.String), server_default='{}', nullable=False),
        sa.Column('domains', postgresql.ARRAY(sa.String), server_default='{}', nullable=False),
        # 元数据
        sa.Column('metadata', postgresql.JSONB, server_default='{}', nullable=False),
        sa.Column('citation_count', sa.Integer, server_default='0', nullable=False),
        # 状态
        sa.Column('status', sa.String(20), server_default='active', nullable=False),
        # 审计
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('created_by', sa.String(100)),
        sa.Column('updated_by', sa.String(100)),
    )
    op.create_index('ix_evidences_tenant_id', 'evidences', ['tenant_id'])
    op.create_index('ix_evidences_site_id', 'evidences', ['site_id'])
    op.create_index('ix_evidences_source_type', 'evidences', ['source_type'])
    op.create_index('ix_evidences_source_ref', 'evidences', ['source_ref'])
    op.create_index('ix_evidences_excerpt_hash', 'evidences', ['excerpt_hash'])

    # ==========================================
    # 9. conversations - 会话表
    # ==========================================
    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('site_id', sa.String(50), sa.ForeignKey('sites.id', ondelete='CASCADE'), nullable=False),
        # 会话标识
        sa.Column('session_id', sa.String(100), nullable=False, unique=True),
        # 参与者
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('npc_id', sa.String(100)),
        # 信息
        sa.Column('title', sa.String(200)),
        sa.Column('summary', sa.Text),
        sa.Column('context', postgresql.JSONB, server_default='{}', nullable=False),
        # 统计
        sa.Column('message_count', sa.Integer, server_default='0', nullable=False),
        sa.Column('total_tokens', sa.Integer, server_default='0', nullable=False),
        # 时间
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_message_at', sa.DateTime(timezone=True)),
        sa.Column('ended_at', sa.DateTime(timezone=True)),
        # 状态
        sa.Column('status', sa.String(20), server_default='active', nullable=False),
        # 审计
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('created_by', sa.String(100)),
        sa.Column('updated_by', sa.String(100)),
    )
    op.create_index('ix_conversations_tenant_id', 'conversations', ['tenant_id'])
    op.create_index('ix_conversations_site_id', 'conversations', ['site_id'])
    op.create_index('ix_conversations_session_id', 'conversations', ['session_id'])
    op.create_index('ix_conversations_user_id', 'conversations', ['user_id'])
    op.create_index('ix_conversations_npc_id', 'conversations', ['npc_id'])

    # ==========================================
    # 10. messages - 消息表
    # ==========================================
    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('site_id', sa.String(50), sa.ForeignKey('sites.id', ondelete='CASCADE'), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
        # 消息
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('tokens', sa.Integer),
        # 证据链
        sa.Column('evidence_ids', postgresql.ARRAY(sa.String), server_default='{}', nullable=False),
        sa.Column('trace_id', sa.String(100)),
        # 元数据
        sa.Column('metadata', postgresql.JSONB, server_default='{}', nullable=False),
        # 时间
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'])
    op.create_index('ix_messages_trace_id', 'messages', ['trace_id'])

    # ==========================================
    # 11. trace_ledger - 证据链账本
    # ==========================================
    op.create_table(
        'trace_ledger',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('site_id', sa.String(50), sa.ForeignKey('sites.id', ondelete='CASCADE'), nullable=False),
        # 追踪标识
        sa.Column('trace_id', sa.String(100), nullable=False, unique=True),
        sa.Column('span_id', sa.String(100)),
        sa.Column('parent_span_id', sa.String(100)),
        # 关联
        sa.Column('conversation_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('conversations.id', ondelete='SET NULL')),
        sa.Column('session_id', sa.String(100)),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('npc_id', sa.String(100)),
        # 请求
        sa.Column('request_type', sa.String(50), nullable=False),
        sa.Column('request_input', postgresql.JSONB, server_default='{}', nullable=False),
        # 工具调用
        sa.Column('tool_calls', postgresql.JSONB, server_default='[]', nullable=False),
        # 证据链
        sa.Column('evidence_ids', postgresql.ARRAY(sa.String), server_default='{}', nullable=False),
        sa.Column('evidence_chain', postgresql.JSONB, server_default='{}', nullable=False),
        # 策略
        sa.Column('policy_mode', sa.String(20), nullable=False),
        sa.Column('policy_reason', sa.String(200)),
        # 响应
        sa.Column('response_output', postgresql.JSONB),
        sa.Column('response_tokens', sa.Integer),
        # 模型
        sa.Column('model_provider', sa.String(50)),
        sa.Column('model_name', sa.String(100)),
        sa.Column('model_version', sa.String(50)),
        # 性能
        sa.Column('latency_ms', sa.Integer),
        sa.Column('prompt_tokens', sa.Integer),
        sa.Column('completion_tokens', sa.Integer),
        sa.Column('total_tokens', sa.Integer),
        sa.Column('cost_usd', sa.Float),
        # 质量
        sa.Column('confidence_score', sa.Float),
        sa.Column('guardrail_passed', sa.Boolean),
        sa.Column('guardrail_reason', sa.String(200)),
        # 错误
        sa.Column('error', sa.Text),
        sa.Column('error_code', sa.String(50)),
        # 状态
        sa.Column('status', sa.String(20), server_default='success', nullable=False),
        # 时间
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # 元数据
        sa.Column('metadata', postgresql.JSONB, server_default='{}', nullable=False),
    )
    op.create_index('ix_trace_ledger_tenant_id', 'trace_ledger', ['tenant_id'])
    op.create_index('ix_trace_ledger_site_id', 'trace_ledger', ['site_id'])
    op.create_index('ix_trace_ledger_trace_id', 'trace_ledger', ['trace_id'])
    op.create_index('ix_trace_ledger_session_id', 'trace_ledger', ['session_id'])
    op.create_index('ix_trace_ledger_user_id', 'trace_ledger', ['user_id'])
    op.create_index('ix_trace_ledger_npc_id', 'trace_ledger', ['npc_id'])
    op.create_index('ix_trace_ledger_policy_mode', 'trace_ledger', ['policy_mode'])
    op.create_index('ix_trace_ledger_status', 'trace_ledger', ['status'])
    op.create_index('ix_trace_ledger_created_at', 'trace_ledger', ['created_at'])

    # ==========================================
    # 12. user_feedbacks - 用户反馈表
    # ==========================================
    op.create_table(
        'user_feedbacks',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('site_id', sa.String(50), sa.ForeignKey('sites.id', ondelete='CASCADE'), nullable=False),
        # 关联
        sa.Column('trace_id', sa.String(100)),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('conversations.id', ondelete='SET NULL')),
        sa.Column('message_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('messages.id', ondelete='SET NULL')),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='SET NULL')),
        # 反馈类型
        sa.Column('feedback_type', sa.String(50), nullable=False),
        sa.Column('rating', sa.Integer),
        sa.Column('content', sa.Text),
        # 纠错
        sa.Column('original_response', sa.Text),
        sa.Column('corrected_response', sa.Text),
        sa.Column('correction_reason', sa.Text),
        # 标签
        sa.Column('tags', postgresql.ARRAY(sa.String), server_default='{}', nullable=False),
        # 处理
        sa.Column('status', sa.String(20), server_default='pending', nullable=False),
        sa.Column('reviewed_by', sa.String(100)),
        sa.Column('reviewed_at', sa.DateTime(timezone=True)),
        sa.Column('review_notes', sa.Text),
        # 应用
        sa.Column('applied_to_knowledge', sa.Boolean, server_default='false', nullable=False),
        sa.Column('applied_at', sa.DateTime(timezone=True)),
        # 元数据
        sa.Column('metadata', postgresql.JSONB, server_default='{}', nullable=False),
        # 时间
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_user_feedbacks_tenant_id', 'user_feedbacks', ['tenant_id'])
    op.create_index('ix_user_feedbacks_site_id', 'user_feedbacks', ['site_id'])
    op.create_index('ix_user_feedbacks_trace_id', 'user_feedbacks', ['trace_id'])
    op.create_index('ix_user_feedbacks_user_id', 'user_feedbacks', ['user_id'])
    op.create_index('ix_user_feedbacks_feedback_type', 'user_feedbacks', ['feedback_type'])
    op.create_index('ix_user_feedbacks_status', 'user_feedbacks', ['status'])

    # ==========================================
    # 创建全文搜索触发器
    # ==========================================
    op.execute("""
        CREATE OR REPLACE FUNCTION update_content_search_vector()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.search_vector := to_tsvector('simple', COALESCE(NEW.title, '') || ' ' || COALESCE(NEW.body, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trigger_update_content_search_vector
        BEFORE INSERT OR UPDATE ON contents
        FOR EACH ROW EXECUTE FUNCTION update_content_search_vector();
    """)


def downgrade() -> None:
    # 删除触发器和函数
    op.execute("DROP TRIGGER IF EXISTS trigger_update_content_search_vector ON contents")
    op.execute("DROP FUNCTION IF EXISTS update_content_search_vector()")

    # 按依赖顺序删除表
    op.drop_table('user_feedbacks')
    op.drop_table('trace_ledger')
    op.drop_table('messages')
    op.drop_table('conversations')
    op.drop_table('evidences')
    op.drop_table('quest_steps')
    op.drop_table('quests')
    op.drop_table('npc_profiles')
    op.drop_table('contents')
    op.drop_table('users')
    op.drop_table('sites')
    op.drop_table('tenants')
