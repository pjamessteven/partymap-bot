"""Initial migration - create all tables

Revision ID: 0001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create festivals table
    op.create_table(
        'festivals',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(500), nullable=False),
        sa.Column('clean_name', sa.String(500), nullable=True),
        sa.Column('raw_name', sa.String(500), nullable=True),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('source_id', sa.String(255), nullable=True),
        sa.Column('state', sa.String(50), server_default='discovered'),
        sa.Column('state_changed_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('discovered_data', postgresql.JSONB(), server_default='{}'),
        sa.Column('research_data', postgresql.JSONB(), server_default='{}'),
        sa.Column('sync_data', postgresql.JSONB(), server_default='{}'),
        sa.Column('partymap_event_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_duplicate', sa.Boolean(), server_default='false'),
        sa.Column('existing_event_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_new_event_date', sa.Boolean(), server_default='false'),
        sa.Column('date_confirmed', sa.Boolean(), server_default='true'),
        sa.Column('discovery_cost_cents', sa.Integer(), server_default='0'),
        sa.Column('research_cost_cents', sa.Integer(), server_default='0'),
        sa.Column('retry_count', sa.Integer(), server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('skip_reason', sa.Text(), nullable=True),
        sa.Column('purge_after', sa.DateTime(), nullable=True),
        sa.Column('current_thread_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()'), onupdate=sa.text('NOW()')),
    )
    
    # Create indexes for festivals
    op.create_index('idx_festivals_name', 'festivals', ['name'])
    op.create_index('idx_festivals_clean_name', 'festivals', ['clean_name'])
    op.create_index('idx_festivals_source', 'festivals', ['source'])
    op.create_index('idx_festivals_state', 'festivals', ['state'])
    op.create_index('idx_festivals_partymap_event', 'festivals', ['partymap_event_id'])
    op.create_index('idx_festivals_current_thread', 'festivals', ['current_thread_id'])
    op.create_index('idx_festivals_created', 'festivals', ['created_at'])

    # Create festival_event_dates table
    op.create_table(
        'festival_event_dates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('festival_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('festivals.id', ondelete='CASCADE'), nullable=False),
        sa.Column('start_date', sa.DateTime(), nullable=False),
        sa.Column('end_date', sa.DateTime(), nullable=True),
        sa.Column('location_description', sa.Text(), nullable=False),
        sa.Column('location_country', sa.String(100), nullable=True),
        sa.Column('location_lat', sa.Float(), nullable=True),
        sa.Column('location_lng', sa.Float(), nullable=True),
        sa.Column('lineup', postgresql.ARRAY(sa.String()), server_default='{}'),
        sa.Column('ticket_url', sa.Text(), nullable=True),
        sa.Column('tickets', postgresql.JSONB(), server_default='{}'),
        sa.Column('expected_size', sa.Integer(), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('partymap_event_date_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()'), onupdate=sa.text('NOW()')),
    )
    op.create_index('idx_event_dates_festival', 'festival_event_dates', ['festival_id'])

    # Create discovery_queries table
    op.create_table(
        'discovery_queries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('last_run_at', sa.DateTime(), nullable=True),
        sa.Column('run_count', sa.Integer(), server_default='0'),
        sa.Column('enabled', sa.Boolean(), server_default='true'),
        sa.Column('priority', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()'), onupdate=sa.text('NOW()')),
    )
    op.create_index('idx_discovery_queries_category', 'discovery_queries', ['category'])

    # Create agent_decisions table
    op.create_table(
        'agent_decisions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('festival_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('festivals.id'), nullable=True),
        sa.Column('thread_id', sa.String(255), nullable=True),
        sa.Column('agent_type', sa.String(50), nullable=False),
        sa.Column('step_number', sa.Integer(), server_default='0'),
        sa.Column('thought', sa.Text(), nullable=False),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('action_input', postgresql.JSONB(), server_default='{}'),
        sa.Column('observation', sa.Text(), nullable=False),
        sa.Column('next_step', sa.String(100), nullable=False),
        sa.Column('confidence', sa.Float(), server_default='0.0'),
        sa.Column('cost_cents', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_agent_decisions_festival', 'agent_decisions', ['festival_id'])
    op.create_index('idx_agent_decisions_thread', 'agent_decisions', ['thread_id'])

    # Create state_transitions table
    op.create_table(
        'state_transitions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('festival_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('festivals.id', ondelete='CASCADE'), nullable=False),
        sa.Column('from_state', sa.String(50), nullable=False),
        sa.Column('to_state', sa.String(50), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_state_transitions_festival', 'state_transitions', ['festival_id'])

    # Create cost_logs table
    op.create_table(
        'cost_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('festival_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('agent_type', sa.String(50), nullable=False),
        sa.Column('service', sa.String(50), nullable=False),
        sa.Column('cost_cents', sa.Integer(), server_default='0'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_cost_logs_created', 'cost_logs', ['created_at'])

    # Create name_mappings table
    op.create_table(
        'name_mappings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('raw_name', sa.String(500), nullable=False, unique=True),
        sa.Column('clean_name', sa.String(500), nullable=False),
        sa.Column('normalized_raw', sa.String(500), nullable=True),
        sa.Column('source', sa.String(50), nullable=True),
        sa.Column('use_count', sa.Integer(), server_default='1'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()'), onupdate=sa.text('NOW()')),
    )
    op.create_index('idx_name_mappings_raw', 'name_mappings', ['raw_name'], unique=True)
    op.create_index('idx_name_mappings_normalized', 'name_mappings', ['normalized_raw'])

    # Create pipeline_schedules table
    op.create_table(
        'pipeline_schedules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('task_type', sa.String(50), nullable=False, unique=True),
        sa.Column('enabled', sa.Boolean(), server_default='false'),
        sa.Column('hour', sa.Integer(), server_default='2'),
        sa.Column('minute', sa.Integer(), server_default='0'),
        sa.Column('day_of_week', sa.Integer(), nullable=True),
        sa.Column('last_run_at', sa.DateTime(), nullable=True),
        sa.Column('next_run_at', sa.DateTime(), nullable=True),
        sa.Column('run_count', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()'), onupdate=sa.text('NOW()')),
    )
    op.create_index('idx_pipeline_schedules_task_type', 'pipeline_schedules', ['task_type'], unique=True)

    # Create system_settings table
    op.create_table(
        'system_settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('key', sa.String(100), nullable=False, unique=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('value_type', sa.String(20), server_default='string'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('editable', sa.Boolean(), server_default='true'),
        sa.Column('category', sa.String(50), server_default='general'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()'), onupdate=sa.text('NOW()')),
    )
    op.create_index('idx_system_settings_key', 'system_settings', ['key'], unique=True)

    # Create agent_threads table
    op.create_table(
        'agent_threads',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('festival_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('festivals.id', ondelete='CASCADE'), nullable=True),
        sa.Column('thread_id', sa.String(255), nullable=False, unique=True),
        sa.Column('agent_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), server_default='running'),
        sa.Column('checkpoint_ns', sa.String(255), nullable=True),
        sa.Column('checkpoint_id', sa.String(255), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), server_default='0'),
        sa.Column('completion_tokens', sa.Integer(), server_default='0'),
        sa.Column('total_tokens', sa.Integer(), server_default='0'),
        sa.Column('cost_cents', sa.Integer(), server_default='0'),
        sa.Column('result_data', postgresql.JSONB(), server_default='{}'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_agent_threads_festival', 'agent_threads', ['festival_id'])
    op.create_index('idx_agent_threads_status', 'agent_threads', ['status'])

    # Create agent_stream_events table
    op.create_table(
        'agent_stream_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('thread_id', sa.String(255), sa.ForeignKey('agent_threads.thread_id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('event_data', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('node_name', sa.String(100), nullable=True),
        sa.Column('step_number', sa.Integer(), nullable=True),
        sa.Column('run_id', sa.String(255), nullable=True),
        sa.Column('tool_name', sa.String(100), nullable=True),
        sa.Column('tool_call_id', sa.String(100), nullable=True),
        sa.Column('model_name', sa.String(100), nullable=True),
        sa.Column('usage', postgresql.JSONB(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_stream_events_thread', 'agent_stream_events', ['thread_id'])
    op.create_index('idx_stream_events_timestamp', 'agent_stream_events', ['timestamp'])
    op.create_index('idx_stream_events_type', 'agent_stream_events', ['event_type'])

    # Create job_activity table
    op.create_table(
        'job_activity',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('job_type', sa.String(50), nullable=False),
        sa.Column('activity_type', sa.String(50), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.Column('festival_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('festivals.id', ondelete='SET NULL'), nullable=True),
        sa.Column('task_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_job_activity_type', 'job_activity', ['job_type', 'activity_type'])
    op.create_index('idx_job_activity_created', 'job_activity', ['created_at'])

    # Create refresh_approvals table
    op.create_table(
        'refresh_approvals',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('event_date_id', sa.Integer(), nullable=False),
        sa.Column('event_name', sa.String(500), nullable=False),
        sa.Column('current_data', postgresql.JSONB(), server_default='{}'),
        sa.Column('proposed_changes', postgresql.JSONB(), server_default='{}'),
        sa.Column('change_summary', postgresql.JSONB(), server_default='[]'),
        sa.Column('status', sa.String(50), server_default='pending'),
        sa.Column('research_confidence', sa.Float(), server_default='0.0'),
        sa.Column('research_sources', postgresql.JSONB(), server_default='[]'),
        sa.Column('approved_by', sa.String(255), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('auto_approve_threshold', sa.Float(), server_default='0.85'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.DateTime(), server_default=sa.text("NOW() + INTERVAL '7 days'")),
    )
    op.create_index('idx_refresh_approvals_status', 'refresh_approvals', ['status'])
    op.create_index('idx_refresh_approvals_event_date', 'refresh_approvals', ['event_date_id'])
    op.create_index('idx_refresh_approvals_created', 'refresh_approvals', ['created_at'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('refresh_approvals')
    op.drop_table('job_activity')
    op.drop_table('agent_stream_events')
    op.drop_table('agent_threads')
    op.drop_table('system_settings')
    op.drop_table('pipeline_schedules')
    op.drop_table('name_mappings')
    op.drop_table('cost_logs')
    op.drop_table('state_transitions')
    op.drop_table('agent_decisions')
    op.drop_table('discovery_queries')
    op.drop_table('festival_event_dates')
    op.drop_table('festivals')
