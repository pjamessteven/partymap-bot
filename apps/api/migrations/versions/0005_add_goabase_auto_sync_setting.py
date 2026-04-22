"""Add auto_goabase_sync_enabled setting

Revision ID: 0005
Revises: 0004
Create Date: 2025-04-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add auto_goabase_sync_enabled setting
    op.execute("""
        INSERT INTO system_settings (key, value, value_type, description, editable, category)
        VALUES (
            'auto_goabase_sync_enabled',
            'false',
            'boolean',
            'Automatically run Goabase sync once per week when enabled',
            true,
            'goabase'
        )
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    # Remove auto_goabase_sync_enabled setting
    op.execute("DELETE FROM system_settings WHERE key = 'auto_goabase_sync_enabled'")
