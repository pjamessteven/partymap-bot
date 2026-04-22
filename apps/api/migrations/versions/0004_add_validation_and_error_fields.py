"""Add validation and enhanced error tracking fields to festivals table

Revision ID: 0004
Revises: 0003
Create Date: 2025-04-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add validation tracking columns
    op.add_column('festivals', sa.Column('validation_status', sa.String(length=20), server_default='pending', nullable=False))
    op.add_column('festivals', sa.Column('validation_errors', postgresql.JSONB(), server_default='[]', nullable=False))
    op.add_column('festivals', sa.Column('validation_warnings', postgresql.JSONB(), server_default='[]', nullable=False))
    op.add_column('festivals', sa.Column('validation_checked_at', sa.DateTime(), nullable=True))
    
    # Add enhanced error tracking columns
    op.add_column('festivals', sa.Column('error_category', sa.String(length=50), nullable=True))
    op.add_column('festivals', sa.Column('error_context', postgresql.JSONB(), nullable=True))
    op.add_column('festivals', sa.Column('first_error_at', sa.DateTime(), nullable=True))
    op.add_column('festivals', sa.Column('last_retry_at', sa.DateTime(), nullable=True))
    op.add_column('festivals', sa.Column('max_retries_reached', sa.Boolean(), server_default='false', nullable=False))
    
    # Add quarantine tracking columns
    op.add_column('festivals', sa.Column('quarantined_at', sa.DateTime(), nullable=True))
    op.add_column('festivals', sa.Column('quarantine_reason', sa.Text(), nullable=True))
    
    # Create indexes for new columns
    op.create_index('ix_festivals_validation_status', 'festivals', ['validation_status'])
    op.create_index('ix_festivals_error_category', 'festivals', ['error_category'])
    op.create_index('ix_festivals_quarantined_at', 'festivals', ['quarantined_at'])
    op.create_index('ix_festivals_validation_checked_at', 'festivals', ['validation_checked_at'])
    op.create_index('ix_festivals_retry_count', 'festivals', ['retry_count'])


def downgrade() -> None:
    # Remove indexes
    op.drop_index('ix_festivals_retry_count', table_name='festivals')
    op.drop_index('ix_festivals_validation_checked_at', table_name='festivals')
    op.drop_index('ix_festivals_quarantined_at', table_name='festivals')
    op.drop_index('ix_festivals_error_category', table_name='festivals')
    op.drop_index('ix_festivals_validation_status', table_name='festivals')
    
    # Remove columns
    op.drop_column('festivals', 'quarantine_reason')
    op.drop_column('festivals', 'quarantined_at')
    op.drop_column('festivals', 'max_retries_reached')
    op.drop_column('festivals', 'last_retry_at')
    op.drop_column('festivals', 'first_error_at')
    op.drop_column('festivals', 'error_context')
    op.drop_column('festivals', 'error_category')
    op.drop_column('festivals', 'validation_checked_at')
    op.drop_column('festivals', 'validation_warnings')
    op.drop_column('festivals', 'validation_errors')
    op.drop_column('festivals', 'validation_status')
