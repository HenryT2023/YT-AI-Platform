"""add embedding_usage table

Revision ID: 007
Revises: 006
Create Date: 2025-12-14

新增 embedding_usage 表用于 embedding 调用审计、成本监控和去重统计
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'embedding_usage',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('site_id', sa.String(50), sa.ForeignKey('sites.id', ondelete='CASCADE'), nullable=True, index=True),
        
        # 对象信息
        sa.Column('object_type', sa.String(50), nullable=False, index=True),
        sa.Column('object_id', sa.String(100), nullable=False, index=True),
        
        # Embedding 提供者信息
        sa.Column('provider', sa.String(50), nullable=False, index=True),
        sa.Column('model', sa.String(100), nullable=False),
        sa.Column('embedding_dim', sa.Integer, nullable=False),
        
        # 输入统计
        sa.Column('input_chars', sa.Integer, nullable=False),
        sa.Column('estimated_tokens', sa.Integer, nullable=False),
        
        # 成本估算 (USD)
        sa.Column('cost_estimate', sa.Float, server_default='0', nullable=False),
        
        # 性能指标
        sa.Column('latency_ms', sa.Integer, nullable=False),
        
        # 状态
        sa.Column('status', sa.String(20), nullable=False, index=True),
        
        # 错误信息（可选）
        sa.Column('error_type', sa.String(100), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        
        # 限流信息（可选）
        sa.Column('backoff_seconds', sa.Integer, nullable=True),
        sa.Column('retry_count', sa.Integer, nullable=True),
        
        # 关联信息（可选）
        sa.Column('trace_id', sa.String(100), nullable=True, index=True),
        sa.Column('job_id', sa.String(100), nullable=True, index=True),
        
        # 内容 hash（用于去重追溯）
        sa.Column('content_hash', sa.String(64), nullable=True),
        
        # 时间
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, index=True),
    )
    
    # 创建复合索引用于查询优化
    op.create_index(
        'ix_embedding_usage_tenant_created',
        'embedding_usage',
        ['tenant_id', 'created_at']
    )
    op.create_index(
        'ix_embedding_usage_provider_model',
        'embedding_usage',
        ['provider', 'model']
    )


def downgrade() -> None:
    op.drop_index('ix_embedding_usage_provider_model', table_name='embedding_usage')
    op.drop_index('ix_embedding_usage_tenant_created', table_name='embedding_usage')
    op.drop_table('embedding_usage')
