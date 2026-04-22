"""Add LangGraph checkpoint tables

Revision ID: 0002
Revises: 0001
Create Date: 2025-04-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create checkpoints table for LangGraph persistence
    op.create_table(
        'checkpoints',
        sa.Column('thread_id', sa.String(255), nullable=False),
        sa.Column('checkpoint_ns', sa.String(255), nullable=False, server_default=''),
        sa.Column('checkpoint_id', sa.String(255), nullable=False),
        sa.Column('parent_checkpoint_id', sa.String(255), nullable=True),
        sa.Column('type', sa.String(50), nullable=True),
        sa.Column('checkpoint', postgresql.JSONB(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.PrimaryKeyConstraint('thread_id', 'checkpoint_ns', 'checkpoint_id')
    )
    
    # Create indexes for checkpoints
    op.create_index('idx_checkpoints_thread', 'checkpoints', ['thread_id'])
    op.create_index('idx_checkpoints_thread_ns', 'checkpoints', ['thread_id', 'checkpoint_ns'])
    
    # Create checkpoint_writes table for pending writes
    op.create_table(
        'checkpoint_writes',
        sa.Column('thread_id', sa.String(255), nullable=False),
        sa.Column('checkpoint_ns', sa.String(255), nullable=False, server_default=''),
        sa.Column('checkpoint_id', sa.String(255), nullable=False),
        sa.Column('task_id', sa.String(255), nullable=False),
        sa.Column('idx', sa.Integer(), nullable=False),
        sa.Column('channel', sa.String(255), nullable=False),
        sa.Column('type', sa.String(50), nullable=True),
        sa.Column('value', postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint('thread_id', 'checkpoint_ns', 'checkpoint_id', 'task_id', 'idx')
    )
    
    # Create indexes for checkpoint_writes
    op.create_index('idx_checkpoint_writes_thread', 'checkpoint_writes', ['thread_id'])
    op.create_index(
        'idx_checkpoint_writes_lookup', 
        'checkpoint_writes', 
        ['thread_id', 'checkpoint_ns', 'checkpoint_id']
    )
    
    # Create checkpoint_migrations table for tracking migrations
    op.create_table(
        'checkpoint_migrations',
        sa.Column('v', sa.Integer(), primary_key=True)
    )
    
    # Add cost_breakdown column to agent_threads table
    op.add_column(
        'agent_threads',
        sa.Column('cost_breakdown', postgresql.JSONB(), server_default='{}', nullable=False)
    )
    
    # Add research_budget_cents to system_settings via insert
    op.execute("""
        INSERT INTO system_settings (key, value, value_type, description, editable, category)
        VALUES (
            'research_budget_cents',
            '50',
            'integer',
            'Maximum cost in cents allowed per festival research. Research will stop when this budget is exceeded.',
            true,
            'cost'
        )
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    # Remove cost_breakdown column
    op.drop_column('agent_threads', 'cost_breakdown')
    
    # Remove research_budget_cents setting
    op.execute("DELETE FROM system_settings WHERE key = 'research_budget_cents'")
    
    # Drop checkpoint tables
    op.drop_table('checkpoint_migrations')
    op.drop_table('checkpoint_writes')
    op.drop_table('checkpoints')
