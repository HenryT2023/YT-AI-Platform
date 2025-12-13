"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2024-12-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Sites 表
    op.create_table(
        'sites',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('display_name', sa.String(200)),
        sa.Column('description', sa.Text),
        sa.Column('config', postgresql.JSONB, server_default='{}'),
        sa.Column('theme', postgresql.JSONB, server_default='{}'),
        sa.Column('location_lat', sa.Float),
        sa.Column('location_lng', sa.Float),
        sa.Column('timezone', sa.String(50), server_default='Asia/Shanghai'),
        sa.Column('status', sa.String(20), server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('created_by', sa.String(100)),
        sa.Column('updated_by', sa.String(100)),
    )
    op.create_index('ix_sites_status', 'sites', ['status'])

    # Scenes 表
    op.create_table(
        'scenes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('site_id', sa.String(50), sa.ForeignKey('sites.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('display_name', sa.String(200)),
        sa.Column('description', sa.Text),
        sa.Column('scene_type', sa.String(50)),
        sa.Column('location_lat', sa.Float),
        sa.Column('location_lng', sa.Float),
        sa.Column('boundary', postgresql.JSONB),
        sa.Column('config', postgresql.JSONB, server_default='{}'),
        sa.Column('parent_scene_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('scenes.id')),
        sa.Column('sort_order', sa.Integer, server_default='0'),
        sa.Column('status', sa.String(20), server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('created_by', sa.String(100)),
        sa.Column('updated_by', sa.String(100)),
    )
    op.create_index('ix_scenes_site_id', 'scenes', ['site_id'])
    op.create_index('ix_scenes_scene_type', 'scenes', ['scene_type'])

    # POIs 表
    op.create_table(
        'pois',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('site_id', sa.String(50), sa.ForeignKey('sites.id'), nullable=False),
        sa.Column('scene_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('scenes.id')),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('display_name', sa.String(200)),
        sa.Column('description', sa.Text),
        sa.Column('poi_type', sa.String(50)),
        sa.Column('location_lat', sa.Float),
        sa.Column('location_lng', sa.Float),
        sa.Column('indoor_position', postgresql.JSONB),
        sa.Column('content', postgresql.JSONB, server_default='{}'),
        sa.Column('media_asset_ids', postgresql.ARRAY(postgresql.UUID(as_uuid=True))),
        sa.Column('tags', postgresql.ARRAY(sa.String)),
        sa.Column('metadata', postgresql.JSONB, server_default='{}'),
        sa.Column('sort_order', sa.Integer, server_default='0'),
        sa.Column('status', sa.String(20), server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('created_by', sa.String(100)),
        sa.Column('updated_by', sa.String(100)),
    )
    op.create_index('ix_pois_site_id', 'pois', ['site_id'])
    op.create_index('ix_pois_scene_id', 'pois', ['scene_id'])

    # NPCs 表
    op.create_table(
        'npcs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('site_id', sa.String(50), sa.ForeignKey('sites.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('display_name', sa.String(200)),
        sa.Column('npc_type', sa.String(50)),
        sa.Column('persona', postgresql.JSONB, nullable=False),
        sa.Column('avatar_asset_id', postgresql.UUID(as_uuid=True)),
        sa.Column('model_asset_id', postgresql.UUID(as_uuid=True)),
        sa.Column('voice_id', sa.String(100)),
        sa.Column('scene_ids', postgresql.ARRAY(postgresql.UUID(as_uuid=True))),
        sa.Column('greeting_templates', postgresql.ARRAY(sa.Text)),
        sa.Column('fallback_responses', postgresql.ARRAY(sa.Text)),
        sa.Column('status', sa.String(20), server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('created_by', sa.String(100)),
        sa.Column('updated_by', sa.String(100)),
    )
    op.create_index('ix_npcs_site_id', 'npcs', ['site_id'])
    op.create_index('ix_npcs_npc_type', 'npcs', ['npc_type'])

    # Quests 表
    op.create_table(
        'quests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('site_id', sa.String(50), sa.ForeignKey('sites.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('display_name', sa.String(200)),
        sa.Column('description', sa.Text),
        sa.Column('quest_type', sa.String(50)),
        sa.Column('config', postgresql.JSONB, server_default='{}'),
        sa.Column('rewards', postgresql.JSONB, server_default='{}'),
        sa.Column('prerequisites', postgresql.JSONB, server_default='{}'),
        sa.Column('scene_ids', postgresql.ARRAY(postgresql.UUID(as_uuid=True))),
        sa.Column('estimated_duration_minutes', sa.Integer),
        sa.Column('difficulty', sa.String(20)),
        sa.Column('category', sa.String(50)),
        sa.Column('tags', postgresql.ARRAY(sa.String)),
        sa.Column('sort_order', sa.Integer, server_default='0'),
        sa.Column('status', sa.String(20), server_default='draft'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('created_by', sa.String(100)),
        sa.Column('updated_by', sa.String(100)),
    )
    op.create_index('ix_quests_site_id', 'quests', ['site_id'])
    op.create_index('ix_quests_quest_type', 'quests', ['quest_type'])

    # Quest Steps 表
    op.create_table(
        'quest_steps',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('quest_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quests.id', ondelete='CASCADE'), nullable=False),
        sa.Column('step_number', sa.Integer, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('step_type', sa.String(50)),
        sa.Column('poi_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('pois.id')),
        sa.Column('npc_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('npcs.id')),
        sa.Column('validation', postgresql.JSONB, server_default='{}'),
        sa.Column('hints', postgresql.ARRAY(sa.Text)),
        sa.Column('rewards', postgresql.JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_quest_steps_quest_id', 'quest_steps', ['quest_id'])

    # Visitors 表
    op.create_table(
        'visitors',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('external_id', sa.String(200)),
        sa.Column('identity_provider', sa.String(50)),
        sa.Column('nickname', sa.String(100)),
        sa.Column('avatar_url', sa.String(500)),
        sa.Column('phone', sa.String(20)),
        sa.Column('profile', postgresql.JSONB, server_default='{}'),
        sa.Column('stats', postgresql.JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('last_active_at', sa.DateTime(timezone=True)),
    )
    op.create_index('ix_visitors_external_id', 'visitors', ['external_id'])
    op.create_unique_constraint('uq_visitors_external_id_provider', 'visitors', ['external_id', 'identity_provider'])

    # Visitor Quests 表
    op.create_table(
        'visitor_quests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('visitor_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('visitors.id', ondelete='CASCADE'), nullable=False),
        sa.Column('quest_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quests.id'), nullable=False),
        sa.Column('status', sa.String(20), server_default='in_progress'),
        sa.Column('current_step', sa.Integer, server_default='1'),
        sa.Column('progress', postgresql.JSONB, server_default='{}'),
        sa.Column('score', sa.Integer, server_default='0'),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_visitor_quests_visitor_id', 'visitor_quests', ['visitor_id'])
    op.create_index('ix_visitor_quests_quest_id', 'visitor_quests', ['quest_id'])
    op.create_unique_constraint('uq_visitor_quest', 'visitor_quests', ['visitor_id', 'quest_id'])


def downgrade() -> None:
    op.drop_table('visitor_quests')
    op.drop_table('visitors')
    op.drop_table('quest_steps')
    op.drop_table('quests')
    op.drop_table('npcs')
    op.drop_table('pois')
    op.drop_table('scenes')
    op.drop_table('sites')
