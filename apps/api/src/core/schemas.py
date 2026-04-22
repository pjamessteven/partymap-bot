"""Pydantic schemas for data validation."""

from datetime import datetime
from src.utils.utc_now import utc_now
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator


class MediaItem(BaseModel):
    """Media item with URL and optional caption/attribution."""

    url: HttpUrl
    caption: Optional[str] = None  # For attribution/credit, e.g., "Photo from {source_url}"
    media_type: Optional[str] = None  # "logo", "gallery", "lineup"


class RRuleData(BaseModel):
    """Recurrence rule for repeating events. Defaults to yearly recurrence."""

    recurringType: int = Field(default=3, description="0=daily, 1=weekly, 2=monthly, 3=yearly")
    separationCount: int = Field(default=1, description="Number of intervals between occurrences")
    dayOfWeek: Optional[int] = Field(default=None, description="Day of week (0-6, Sunday=0)")
    weekOfMonth: Optional[int] = Field(default=None, description="Week of month (1-5)")
    monthOfYear: Optional[int] = Field(default=None, description="Month of year (1-12)")
    dayOfMonth: Optional[int] = Field(default=None, description="Day of month (1-31)")
    exact: bool = Field(default=False, description="Whether to use exact dates or relative patterns")


class FestivalState(str, Enum):
    """State machine for festivals."""

    DISCOVERED = "discovered"
    RESEARCHING = "researching"
    RESEARCHED = "researched"
    RESEARCHED_PARTIAL = "researched_partial"
    SYNCING = "syncing"
    SYNCED = "synced"
    FAILED = "failed"
    SKIPPED = "skipped"
    NEEDS_REVIEW = "needs_review"


class TicketInfo(BaseModel):
    """Ticket information for an event date."""

    url: Optional[HttpUrl] = None
    description: Optional[str] = None
    price_min: Optional[Decimal] = None
    price_max: Optional[Decimal] = None
    price_currency_code: Optional[str] = Field(default="USD", pattern=r"^[A-Z]{3}$")


class EventDateData(BaseModel):
    """Data for a specific event date (goes to EventDate object)."""

    start: datetime
    end: Optional[datetime] = None
    location_description: str
    location_country: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    lineup: List[str] = Field(default_factory=list)
    ticket_url: Optional[HttpUrl] = None
    tickets: List[TicketInfo] = Field(default_factory=list)
    expected_size: Optional[int] = None
    source_url: Optional[str] = None  # URL specific to this date

    # Enhanced fields
    size: Optional[int] = None  # Expected attendance/capacity
    lineup_images: List[str] = Field(default_factory=list)  # URLs to lineup posters

    @field_validator("lineup", mode="before")
    @classmethod
    def clean_lineup(cls, v):
        """Clean and deduplicate lineup."""
        if not v:
            return []
        cleaned = [artist.strip().title() for artist in v if artist and artist.strip()]
        seen = set()
        return [a for a in cleaned if not (a in seen or seen.add(a))]


class ValidationResult(BaseModel):
    """Result of festival data validation."""
    is_valid: bool = False
    status: str = "invalid"  # "ready", "needs_review", "invalid"
    completeness_score: float = Field(0.0, ge=0.0, le=1.0)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[Dict[str, Any]] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)


class FestivalData(BaseModel):
    """
    Complete festival data split into:
    - General info (goes to Event object)
    - Event dates (go to EventDate objects)
    """

    # General info (Event object)
    name: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    full_description: Optional[str] = None
    website_url: Optional[HttpUrl] = None
    youtube_url: Optional[HttpUrl] = None

    # Media (Event object)
    logo_url: Optional[HttpUrl] = None  # Selected squarish logo/cover image
    media_items: List[MediaItem] = Field(default_factory=list)  # Gallery photos with captions

    # Classification (Event object)
    tags: List[str] = Field(default_factory=list, max_length=5)  # Max 5 tags from PartyMap
    category: Optional[str] = Field(default="music_festival")

    # Event dates (EventDate objects)
    event_dates: List[EventDateData] = Field(default_factory=list)

    # Recurrence (defaults to yearly if is_recurring detected)
    rrule: Optional[RRuleData] = None
    is_recurring: bool = False  # Detected from text like "annual", "yearly"

    # Source tracking
    source: Optional[str] = None
    source_url: Optional[str] = None
    source_modified: Optional[datetime] = None
    discovered_data: Dict[str, Any] = Field(
        default_factory=dict
    )  # Source-specific data like goabase_modified

    # Name normalization for deduplication
    clean_name: Optional[str] = Field(
        default=None,
        description="Canonical event name without year/number suffixes for deduplication",
    )
    raw_name: Optional[str] = Field(
        default=None, description="Original/raw name from discovery source"
    )

    # Validation tracking
    validation_status: str = Field(default="pending", description="pending, ready, needs_review, invalid")
    validation_errors: List[Dict[str, Any]] = Field(default_factory=list)
    validation_warnings: List[Dict[str, Any]] = Field(default_factory=list)

    @field_validator("event_dates")
    @classmethod
    def validate_event_dates(cls, v):
        """Ensure at least one event date."""
        if not v:
            raise ValueError("At least one event date is required")
        return v

    @field_validator("tags")
    @classmethod
    def limit_tags(cls, v):
        """Enforce max 5 tags."""
        if v and len(v) > 5:
            return v[:5]
        return v

    def validate_for_sync(self) -> ValidationResult:
        """
        Validate festival data before PartyMap sync.
        
        Returns ValidationResult with status, errors, warnings, and completeness score.
        """
        errors = []
        warnings = []
        missing_fields = []
        
        # Required field checks
        if not self.name or len(self.name.strip()) < 2:
            errors.append({"field": "name", "message": "Name is required and must be at least 2 characters"})
            missing_fields.append("name")
        
        if not self.description or len(self.description.strip()) < 10:
            errors.append({"field": "description", "message": "Description must be at least 10 characters"})
            missing_fields.append("description")
            
        if not self.full_description or len(self.full_description.strip()) < 20:
            errors.append({"field": "full_description", "message": "Full description must be at least 20 characters"})
            missing_fields.append("full_description")
        
        # Event dates validation
        if not self.event_dates:
            errors.append({"field": "event_dates", "message": "At least one event date is required"})
            missing_fields.append("dates")
        else:
            for idx, ed in enumerate(self.event_dates):
                # Check end_date > start_date
                if ed.end and ed.start and ed.end <= ed.start:
                    errors.append({
                        "field": f"event_dates[{idx}].end",
                        "message": "End date must be after start date"
                    })
                
                # Check dates are in the future
                from datetime import datetime
                if ed.start and ed.start < datetime.now():
                    warnings.append({
                        "field": f"event_dates[{idx}].start",
                        "message": "Event date is in the past"
                    })
                
                # Check location
                if not ed.location_description or len(ed.location_description.strip()) < 3:
                    errors.append({
                        "field": f"event_dates[{idx}].location",
                        "message": "Location description is required"
                    })
                    if "location" not in missing_fields:
                        missing_fields.append("location")
                
                # Ticket price validation
                if ed.tickets:
                    for t_idx, ticket in enumerate(ed.tickets):
                        if ticket.price_min is not None and ticket.price_max is not None:
                            if ticket.price_max < ticket.price_min:
                                errors.append({
                                    "field": f"event_dates[{idx}].tickets[{t_idx}].price_max",
                                    "message": "Maximum price must be greater than or equal to minimum price"
                                })
        
        # Media validation
        if not self.logo_url:
            warnings.append({"field": "logo_url", "message": "No logo image selected"})
        
        if not self.media_items:
            warnings.append({"field": "media_items", "message": "No gallery images"})
        
        # Tags validation
        if not self.tags:
            warnings.append({"field": "tags", "message": "No tags assigned"})
        elif len(self.tags) < 2:
            warnings.append({"field": "tags", "message": "Consider adding more tags for better discoverability"})
        
        # Calculate completeness score
        required_fields = ["name", "description", "full_description", "event_dates"]
        optional_fields = ["logo_url", "media_items", "tags", "youtube_url", "website_url"]
        
        required_score = sum(1 for f in required_fields if f not in missing_fields) / len(required_fields)
        optional_score = sum(1 for f in optional_fields if getattr(self, f, None)) / len(optional_fields)
        
        completeness_score = (required_score * 0.7) + (optional_score * 0.3)
        
        # Determine status
        if errors:
            status = "invalid"
        elif warnings or completeness_score < 0.8:
            status = "needs_review"
        else:
            status = "ready"
        
        return ValidationResult(
            is_valid=(status == "ready"),
            status=status,
            completeness_score=round(completeness_score, 2),
            errors=errors,
            warnings=warnings,
            missing_fields=missing_fields
        )


class DiscoveredFestival(BaseModel):
    """Raw festival data from discovery."""

    id: Optional[UUID] = None
    name: Optional[str] = None
    clean_name: Optional[str] = None
    source: str
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    location: Optional[str] = None  # Location from discovery
    
    # State and workflow
    state: FestivalState = FestivalState.DISCOVERED
    workflow_type: Optional[str] = None  # "new" or "update"
    
    # Deduplication info (NEW: integrated deduplication)
    partymap_event_id: Optional[int] = None  # Integer to match PartyMap API
    update_required: bool = False
    update_reasons: List[str] = Field(default_factory=list)
    existing_event_data: Optional[dict] = None
    
    discovered_data: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ResearchedFestival(BaseModel):
    """Enriched festival data after research."""

    id: Optional[UUID] = None
    festival_data: FestivalData  # Split into Event + EventDate data

    # Deduplication info (set before research or after check)
    is_duplicate: bool = False
    existing_event_id: Optional[UUID] = None
    is_new_event_date: bool = False
    date_confirmed: bool = True

    # PartyMap tracking
    partymap_event_id: Optional[UUID] = None
    partymap_status: Optional[str] = None

    # Cost tracking
    research_cost_cents: int = 0

    # Agent tracking
    research_decisions: List[Dict] = Field(default_factory=list)

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# PartyMap API Schemas


class PartyMapCreateEventRequest(BaseModel):
    """
    Request for POST /events
    Only includes general Event info, NOT date/location specific info.
    """

    name: str
    description: str
    description_attribute: Optional[str] = None
    full_description: str
    full_description_attribute: Optional[str] = None
    youtube_url: Optional[HttpUrl] = None
    url: Optional[HttpUrl] = None
    tags: List[str] = Field(default_factory=list)
    logo: Optional[Dict[str, Any]] = None  # {"url": "..."}
    media_items: Optional[List[Dict[str, Any]]] = None
    # Note: date_time, location, rrule intentionally omitted
    # Event dates will be added separately via POST /api/date/event/{id}


class PartyMapAddEventDateRequest(BaseModel):
    """
    Request for POST /api/date/event/{event_id}
    Date/location specific info goes here.
    """

    start: datetime
    end: Optional[datetime] = None
    description: Optional[str] = None  # Location description
    url: Optional[HttpUrl] = None
    ticket_url: Optional[HttpUrl] = None
    size: Optional[int] = None
    artists: Optional[List[Dict[str, str]]] = None  # [{"name": "Artist"}]
    tickets: Optional[List[Dict[str, Any]]] = None
    lineup_images: Optional[List[Dict[str, Any]]] = None


class PartyMapUpdateEventRequest(BaseModel):
    """
    Request for PUT /events/{id}
    ONLY update general info, NEVER date_time/location/rrule.
    """

    name: Optional[str] = None
    description: Optional[str] = None
    full_description: Optional[str] = None
    youtube_url: Optional[HttpUrl] = None
    url: Optional[HttpUrl] = None
    add_tags: Optional[List[str]] = None
    remove_tags: Optional[List[str]] = None
    logo: Optional[Dict[str, Any]] = None
    media_items: Optional[List[Dict[str, Any]]] = None
    message: Optional[str] = "Updated by festival bot"
    # Note: date_time, location, rrule intentionally omitted


class PartyMapUpdateEventDateRequest(BaseModel):
    """
    Request for PUT /api/date/event/{event_id}/{date_id}
    Update specific EventDate info.
    """

    start: Optional[datetime] = None
    end: Optional[datetime] = None
    description: Optional[str] = None
    url: Optional[HttpUrl] = None
    ticket_url: Optional[HttpUrl] = None
    size: Optional[int] = None
    artists: Optional[List[Dict[str, str]]] = None
    tickets: Optional[List[Dict[str, Any]]] = None


class DuplicateCheckResult(BaseModel):
    """Result of duplicate check."""

    is_duplicate: bool
    existing_event_id: Optional[int] = None
    is_new_event_date: bool = False
    date_confirmed: bool = True
    confidence: float = 0.0
    reason: str = ""


class AgentDecisionLog(BaseModel):
    """Agent decision for logging."""

    agent_type: str  # 'discovery', 'research'
    step_number: int
    thought: str
    action: str
    action_input: Dict
    observation: str
    next_step: str
    confidence: float
    cost_cents: int = 0


# System Settings Schemas


class SettingValueType(str, Enum):
    """Valid value types for system settings."""

    STRING = "string"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    FLOAT = "float"
    JSON = "json"


class SettingCategory(str, Enum):
    """Setting categories for grouping in UI."""

    PIPELINE = "pipeline"
    SCHEDULING = "scheduling"
    COST = "cost"
    GENERAL = "general"


class SystemSettingResponse(BaseModel):
    """System setting response schema.

    Used to return setting values with proper typing for UI display.
    """

    id: UUID = Field(..., description="Unique identifier for the setting")
    key: str = Field(..., description="Unique setting key (e.g., 'auto_process')")
    value: Any = Field(..., description="Setting value (parsed to proper type)")
    value_type: SettingValueType = Field(..., description="Data type of the value for UI rendering")
    description: Optional[str] = Field(
        None, description="Human-readable description of the setting"
    )
    editable: bool = Field(..., description="Whether this setting can be modified via API")
    category: SettingCategory = Field(..., description="Category for grouping in UI")
    created_at: datetime = Field(..., description="When the setting was created")
    updated_at: datetime = Field(..., description="When the setting was last updated")

    class Config:
        from_attributes = True


class SystemSettingUpdate(BaseModel):
    """System setting update request schema.

    Validates that the value matches the expected type.
    """

    value: Any = Field(..., description="New value for the setting")

    @field_validator("value")
    @classmethod
    def validate_value_not_none(cls, v):
        """Ensure value is not None."""
        if v is None:
            raise ValueError("Value cannot be None")
        return v


class AutoProcessSetting(BaseModel):
    """Auto-process setting response.

    Convenience schema for the commonly accessed auto_process setting.
    """

    enabled: bool = Field(
        ..., description="Whether festivals are automatically processed through the pipeline"
    )
    description: str = Field(
        default="Automatically process festivals through the pipeline (dedup → research → sync). When disabled, festivals stay in their current state until manually triggered.",
        description="What auto_process controls",
    )


class SettingsListResponse(BaseModel):
    """List of all system settings grouped by category."""

    settings: List[SystemSettingResponse] = Field(..., description="All system settings")
    by_category: Dict[str, List[SystemSettingResponse]] = Field(
        ..., description="Settings grouped by category"
    )


# Manual Action Schemas


class FestivalAction(str, Enum):
    """Available manual actions for a festival."""

    DEDUPLICATE = "deduplicate"
    RESEARCH = "research"
    SYNC = "sync"
    SKIP = "skip"
    RETRY = "retry"
    RESET = "reset"


class FestivalActionResult(str, Enum):
    """Possible results of a manual action."""

    QUEUED = "queued"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class FestivalPendingAction(BaseModel):
    """Represents a pending action for a festival in manual mode.

    This helps the UI show what action is suggested based on current state.
    """

    festival_id: UUID = Field(..., description="ID of the festival")
    name: str = Field(..., description="Festival name")
    state: FestivalState = Field(..., description="Current festival state")
    source: str = Field(..., description="Discovery source")
    suggested_action: FestivalAction = Field(
        ..., description="Recommended next action based on state"
    )
    action_description: str = Field(
        ..., description="Human-readable description of what the action does"
    )
    created_at: datetime = Field(..., description="When the festival was discovered")
    retry_count: int = Field(0, description="Number of retry attempts")
    last_error: Optional[str] = Field(None, description="Last error if failed")

    class Config:
        from_attributes = True


class FestivalActionRequest(BaseModel):
    """Request to perform a manual action on a festival."""

    action: FestivalAction = Field(
        ..., description="Action to perform", examples=["research", "sync"]
    )
    reason: Optional[str] = Field(
        None,
        description="Optional reason for performing this action (for audit log)",
        examples=["Testing research pipeline", "Manual retry after fix"],
    )


class FestivalActionResponse(BaseModel):
    """Response after performing a manual action on a festival."""

    festival_id: UUID = Field(..., description="ID of the festival")
    action: FestivalAction = Field(..., description="Action that was performed")
    result: FestivalActionResult = Field(..., description="Result of the action")
    message: str = Field(..., description="Human-readable result message")
    previous_state: FestivalState = Field(..., description="State before the action")
    new_state: Optional[FestivalState] = Field(
        None, description="State after the action (if changed)"
    )
    task_id: Optional[str] = Field(None, description="Celery task ID if action was queued")
    queued: bool = Field(..., description="Whether the action was queued for async processing")
    timestamp: datetime = Field(
        default_factory=utc_now, description="When the action was triggered"
    )


class DeduplicationResultResponse(BaseModel):
    """Result of manual deduplication check.

    Provides detailed information about what was determined and what will happen next.
    """

    festival_id: UUID = Field(..., description="ID of the festival")
    is_duplicate: bool = Field(..., description="Whether this is a duplicate event")
    existing_event_id: Optional[UUID] = Field(None, description="ID of existing event if duplicate")
    is_new_event_date: bool = Field(
        False, description="Whether this is a new date for an existing series"
    )
    date_confirmed: bool = Field(True, description="Whether the existing event dates are confirmed")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score of the duplicate check"
    )
    reason: str = Field(..., description="Explanation of the deduplication decision")
    action_taken: str = Field(
        ...,
        description="What action was taken (research queued, marked synced, etc.)",
    )
    auto_queued: bool = Field(
        ..., description="Whether next step was auto-queued (auto_process=true)"
    )


class ResearchFailure(BaseModel):
    """Structured failure information from research agent."""
    
    reason: str = Field(
        ...,
        description="Failure reason category",
        examples=["dates", "not_found", "logo", "description", "url", "location", "classification", "unknown"]
    )
    message: str = Field(
        ...,
        description="Human-readable failure message",
        examples=["Dates for this festival haven't been released yet", "Festival website not found"]
    )
    missing_fields: List[str] = Field(
        default_factory=list,
        description="Required fields that are missing"
    )
    collected_partial_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Partial data that was collected"
    )
    completeness_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="How complete the research is (0.0-1.0)"
    )
    cost_cents: int = Field(
        default=0,
        description="Cost incurred during research attempt (in cents)"
    )
    iterations: int = Field(
        default=0,
        description="Number of research iterations attempted"
    )
    
    class Config:
        from_attributes = True


class ResearchResult(BaseModel):
    """Structured result from research agent."""
    
    success: bool = Field(..., description="Whether research was successful")
    
    # For successful research
    festival_data: Optional[FestivalData] = Field(
        None,
        description="Complete festival data for successful research"
    )
    
    # For failed research
    failure: Optional[ResearchFailure] = Field(
        None,
        description="Failure information for unsuccessful research"
    )
    
    collected_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="All data collected during research"
    )
    cost_cents: int = Field(
        default=0,
        description="Total cost of research (in cents)"
    )
    iterations: int = Field(
        default=0,
        description="Number of iterations completed"
    )
    decisions: List[AgentDecisionLog] = Field(
        default_factory=list,
        description="Agent decisions during research"
    )
    
    class Config:
        from_attributes = True


class SchemaValidationResult(BaseModel):
    """Result of PartyMap schema validation."""
    
    is_valid: bool = Field(..., description="Whether data meets schema requirements")
    missing_fields: List[str] = Field(
        default_factory=list,
        description="Required fields that are missing"
    )
    failure_reason: str = Field(
        ...,
        description="Primary failure reason category"
    )
    completeness_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="How complete the data is (0.0-1.0)"
    )