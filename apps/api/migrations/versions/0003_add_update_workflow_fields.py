"""Add update workflow fields to festivals table

Revision ID: 0003
Revises: 0002
Create Date: 2025-04-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to festivals table
    
    # Change partymap_event_id from UUID to Integer
    op.alter_column('festivals', 'partymap_event_id',
                    existing_type=postgresql.UUID(as_uuid=True),
                    type_=sa.Integer(),
                    existing_nullable=True,
                    postgresql_using='partymap_event_id::text::integer')
    
    # Add update workflow columns
    op.add_column('festivals', sa.Column('update_required', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('festivals', sa.Column('update_reasons', postgresql.JSONB(), server_default='[]', nullable=False))
    op.add_column('festivals', sa.Column('existing_event_data', postgresql.JSONB(), nullable=True))
    op.add_column('festivals', sa.Column('workflow_type', sa.String(length=20), nullable=True))
    
    # Create indexes for new columns
    op.create_index('ix_festivals_update_required', 'festivals', ['update_required'])
    op.create_index('ix_festivals_workflow_type', 'festivals', ['workflow_type'])
    
    # Migrate existing festivals to new state system
    # DISCOVERED → NEEDS_RESEARCH_NEW (assume all existing need research)
    op.execute("""
        UPDATE festivals 
        SET state = 'needs_research_new',
            workflow_type = 'new'
        WHERE state = 'discovered'
    """)


def downgrade() -> None:
    # Remove indexes
    op.drop_index('ix_festivals_workflow_type', table_name='festivals')
    op.drop_index('ix_festivals_update_required', table_name='festivals')
    
    # Remove columns
    op.drop_column('festivals', 'workflow_type')
    op.drop_column('festivals', 'existing_event_data')
    op.drop_column('festivals', 'update_reasons')
    op.drop_column('festivals', 'update_required')
    
    # Revert partymap_event_id back to UUID
    op.alter_column('festivals', 'partymap_event_id',
                    existing_type=sa.Integer(),
                    type_=postgresql.UUID(as_uuid=True),
                    existing_nullable=True,
                    postgresql_using='partymap_event_id::text::uuid')
    
    # Revert state changes
    op.execute("""
        UPDATE festivals 
        SET state = 'discovered'
        WHERE state IN ('needs_research_new', 'needs_research_update', 'update_in_progress', 'update_complete')
    """)
