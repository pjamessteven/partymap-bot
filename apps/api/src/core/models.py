"""SQLAlchemy database models for PartyMap Festival Bot."""

import uuid
from datetime import datetime, timedelta
from src.utils.utc_now import utc_now
from enum import Enum as PyEnum
from typing import List, Optional

from sqlalchemy import (
    JSON,
    ARRAY,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Enum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class FestivalState(str, PyEnum):
    """State machine for festivals."""

    # Discovery phase
    DISCOVERED = "discovered"
    
    # New workflow states (integrated deduplication)
    NEEDS_RESEARCH_NEW = "needs_research_new"      # New festival, needs full research
    NEEDS_RESEARCH_UPDATE = "needs_research_update"  # Existing event, needs update research
    
    # Research phase
    RESEARCHING = "researching"
    RESEARCHED = "researched"
    RESEARCHED_PARTIAL = "researched_partial"
    UPDATE_IN_PROGRESS = "update_in_progress"
    UPDATE_COMPLETE = "update_complete"
    
    # Sync phase
    SYNCING = "syncing"
    SYNCED = "synced"
    
    # Validation states (NEW)
    VALIDATING = "validating"
    VALIDATION_FAILED = "validation_failed"
    QUARANTINED = "quarantined"
    
    # End states
    FAILED = "failed"
    SKIPPED = "skipped"
    NEEDS_REVIEW = "needs_review"


class Festival(Base):
    """Core festival table with state machine."""

    __tablename__ = "festivals"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Basic info
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    clean_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, index=True)
    raw_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # 'exa', 'goabase', 'manual'
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # State machine
    state: Mapped[str] = mapped_column(
        String(50), default=FestivalState.DISCOVERED.value, index=True
    )
    state_changed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Data accumulates as we progress
    discovered_data: Mapped[dict] = mapped_column(JSON, default=dict)
    research_data: Mapped[dict] = mapped_column(JSON, default=dict)
    sync_data: Mapped[dict] = mapped_column(JSON, default=dict)

    # PartyMap tracking (using Integer to match PartyMap API)
    partymap_event_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True
    )
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    existing_event_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # For series: track if this is a new date for existing event
    is_new_event_date: Mapped[bool] = mapped_column(Boolean, default=False)
    date_confirmed: Mapped[bool] = mapped_column(Boolean, default=True)  # If False, need to update
    
    # Update workflow tracking (NEW: for integrated deduplication)
    update_required: Mapped[bool] = mapped_column(Boolean, default=False)
    update_reasons: Mapped[list] = mapped_column(JSON, default=list)  # ["missing_dates", "dates_unconfirmed", "location_change", "lineup_released", "event_cancelled"]
    existing_event_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Cached PartyMap event data
    
    # Workflow type tracking
    workflow_type: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, default=None
    )  # "new" or "update"

    # Cost tracking (in cents)
    discovery_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    research_cost_cents: Mapped[int] = mapped_column(Integer, default=0)

    # Retry handling
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    skip_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Research failure tracking
    failure_reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    failure_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    research_completeness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Validation tracking (NEW)
    validation_status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # "pending", "ready", "needs_review", "invalid"
    validation_errors: Mapped[list] = mapped_column(JSON, default=list)
    validation_warnings: Mapped[list] = mapped_column(JSON, default=list)
    validation_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Enhanced error tracking (NEW)
    error_category: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # "transient", "permanent", "validation", "external", "budget"
    error_context: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    first_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    max_retries_reached: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Quarantine tracking (NEW)
    quarantined_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    quarantine_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Retention
    purge_after: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    # Current thread tracking for live viewing
    current_thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    # Relationships
    event_dates: Mapped[List["FestivalEventDate"]] = relationship(
        back_populates="festival", cascade="all, delete-orphan"
    )
    decisions: Mapped[List["AgentDecision"]] = relationship(
        back_populates="festival", cascade="all, delete-orphan"
    )
    state_history: Mapped[List["StateTransition"]] = relationship(
        back_populates="festival", cascade="all, delete-orphan"
    )
    agent_threads: Mapped[List["AgentThread"]] = relationship(
        back_populates="festival", cascade="all, delete-orphan"
    )


class FestivalEventDate(Base):
    """Individual event dates for festival series."""

    __tablename__ = "festival_event_dates"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    festival_id: Mapped[UUID] = mapped_column(ForeignKey("festivals.id"), nullable=False)

    # Date/Location specific info
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    location_description: Mapped[str] = mapped_column(Text, nullable=False)
    location_country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    location_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # EventDate specific data
    lineup: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    ticket_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tickets: Mapped[dict] = mapped_column(JSON, default=dict)  # Ticket info
    expected_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Source tracking for this specific date
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # PartyMap tracking
    partymap_event_date_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    # Relationships
    festival: Mapped["Festival"] = relationship(back_populates="event_dates")


class DiscoveryQuery(Base):
    """Discovery query rotation tracking."""

    __tablename__ = "discovery_queries"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # 'country', 'city', 'genre'

    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )


class AgentDecision(Base):
    """DEPRECATED: Use AgentThread and AgentStreamEvent instead.

    Kept for historical data. New agent runs use the streaming tables.
    """

    __tablename__ = "agent_decisions"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    festival_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("festivals.id"), nullable=True)

    # Link to new stream format if migrated
    thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'discovery', 'research'
    step_number: Mapped[int] = mapped_column(Integer, default=0)

    # ReAct pattern (summarized)
    thought: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    action_input: Mapped[dict] = mapped_column(JSON, default=dict)
    observation: Mapped[str] = mapped_column(Text, nullable=False)
    next_step: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)

    # Cost
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    festival: Mapped[Optional["Festival"]] = relationship(back_populates="decisions")


class StateTransition(Base):
    """State transition audit trail."""

    __tablename__ = "state_transitions"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    festival_id: Mapped[UUID] = mapped_column(ForeignKey("festivals.id"), nullable=False)

    from_state: Mapped[str] = mapped_column(String(50), nullable=False)
    to_state: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    festival: Mapped["Festival"] = relationship(back_populates="state_history")


class CostLog(Base):
    """API cost tracking."""

    __tablename__ = "cost_logs"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    festival_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("festivals.id"), nullable=True)

    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    service: Mapped[str] = mapped_column(String(50), nullable=False)  # 'openrouter', 'exa', etc.
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Index for daily cost queries
    __table_args__ = (Index("idx_cost_logs_created_at", "created_at"),)


class NameMapping(Base):
    """Store raw->clean name mappings for learning and consistency."""

    __tablename__ = "name_mappings"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    raw_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    clean_name: Mapped[str] = mapped_column(String(500), nullable=False)

    # Normalized version for fuzzy matching
    normalized_raw: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, index=True)

    # Source that created this mapping
    source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Usage count - how many times this mapping has been used
    use_count: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    # Unique constraint on raw_name
    __table_args__ = (
        Index("idx_name_mappings_raw", "raw_name", unique=True),
        Index("idx_name_mappings_normalized", "normalized_raw"),
    )


class PipelineSchedule(Base):
    """Schedule configuration for pipeline tasks."""

    __tablename__ = "pipeline_schedules"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_type: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    # 'discovery', 'goabase_sync', 'cleanup_failed'

    enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Schedule fields (UTC)
    hour: Mapped[int] = mapped_column(Integer, default=2)
    minute: Mapped[int] = mapped_column(Integer, default=0)
    day_of_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0=Monday, 6=Sunday

    # Metadata
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    # Unique constraint on task_type
    __table_args__ = (Index("idx_pipeline_schedules_task_type", "task_type", unique=True),)


class SystemSettings(Base):
    """Global system settings for pipeline behavior."""

    __tablename__ = "system_settings"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Setting key (unique identifier)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)

    # Setting value (stored as string, parsed based on type)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    # Value type for proper parsing
    value_type: Mapped[str] = mapped_column(String(20), default="string")
    # 'string', 'boolean', 'integer', 'float', 'json'

    # Human-readable description
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Whether this setting can be modified via API
    editable: Mapped[bool] = mapped_column(Boolean, default=True)

    # Category for grouping in UI
    category: Mapped[str] = mapped_column(String(50), default="general")
    # 'pipeline', 'scheduling', 'cost', 'general'

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    # Unique constraint on key
    __table_args__ = (Index("idx_system_settings_key", "key", unique=True),)


class JobActivity(Base):
    """Job activity log for 90-day retention."""

    __tablename__ = "job_activity"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Job identification
    job_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # 'discovery', 'research', 'sync', 'goabase_sync'

    # Activity type
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # 'started', 'progress', 'completed', 'failed', 'stopped', 'festival_started', 'festival_completed'

    # Activity details
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # For progress: {current: 4, total: 10, festival_id: "...", festival_name: "..."}

    # Optional reference to festival being processed
    festival_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("festivals.id", ondelete="SET NULL"), nullable=True
    )

    # Task ID from Celery
    task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    # Relationships
    festival: Mapped[Optional["Festival"]] = relationship()

    # Indexes
    __table_args__ = (
        Index("idx_job_activity_type", "job_type", "activity_type"),
        Index("idx_job_activity_created", "created_at"),
    )


class AgentThread(Base):
    """Agent thread tracking for LangGraph checkpointing and streaming."""

    __tablename__ = "agent_threads"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    festival_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("festivals.id", ondelete="CASCADE"), nullable=True
    )
    thread_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'research', 'discovery'
    status: Mapped[str] = mapped_column(String(50), default="running")  # 'running', 'completed', 'failed', 'stopped'

    # Checkpoint for resumability
    checkpoint_ns: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    checkpoint_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Cost tracking (from OpenRouter response)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)  # Calculated from token usage

    # Result
    result_data: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    festival: Mapped[Optional["Festival"]] = relationship(back_populates="agent_threads")
    events: Mapped[List["AgentStreamEvent"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("idx_agent_threads_festival", "festival_id"),
        Index("idx_agent_threads_status", "status"),
    )


class AgentStreamEvent(Base):
    """Individual stream events for real-time display and historical loading."""

    __tablename__ = "agent_stream_events"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("agent_threads.thread_id", ondelete="CASCADE"), nullable=False
    )

    # Event categorization (LangGraph stream modes)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # 'messages', 'updates', 'values', 'tools', 'custom', 'reasoning', 'error', 'complete'

    # Event data (LangGraph native format)
    event_data: Mapped[dict] = mapped_column(JSON, default=dict)

    # LangGraph metadata
    node_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    step_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    run_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # For tool events
    tool_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tool_call_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # For LLM events with token tracking
    model_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    usage: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # {prompt_tokens, completion_tokens, total_tokens}

    # Timing
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    thread: Mapped["AgentThread"] = relationship(back_populates="events")

    # Indexes
    __table_args__ = (
        Index("idx_stream_events_thread", "thread_id"),
        Index("idx_stream_events_timestamp", "timestamp"),
        Index("idx_stream_events_type", "event_type"),
    )


class RefreshApproval(Base):
    """Queue for refresh pipeline changes awaiting human approval."""

    __tablename__ = "refresh_approvals"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # PartyMap references
    event_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    event_date_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    event_name: Mapped[str] = mapped_column(String(500), nullable=False)

    # Current data (snapshot)
    current_data: Mapped[dict] = mapped_column(JSON, default=dict)
    # {start, end, description, lineup, ticket_url, ...}

    # Proposed changes
    proposed_changes: Mapped[dict] = mapped_column(JSON, default=dict)
    # {start, end, description, lineup, ticket_url, ...}

    # Change summary for display
    change_summary: Mapped[List[str]] = mapped_column(JSON, default=list)
    # ["Date confirmed: 2025-04-12", "Lineup added: 45 artists", ...]

    # Status
    status: Mapped[str] = mapped_column(
        String(50), default="pending", index=True
    )  # 'pending', 'approved', 'rejected', 'auto_approved'

    # Research metadata
    research_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    research_sources: Mapped[List[str]] = mapped_column(JSON, default=list)
    # URLs that were used for research

    # Approval metadata
    approved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Auto-approve if confidence > threshold
    auto_approve_threshold: Mapped[float] = mapped_column(Float, default=0.85)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: utc_now() + timedelta(days=7)
    )  # Expire after 7 days

    # Indexes
    __table_args__ = (
        Index("idx_refresh_approvals_status", "status"),
        Index("idx_refresh_approvals_event_date", "event_date_id"),
        Index("idx_refresh_approvals_created", "created_at"),
    )