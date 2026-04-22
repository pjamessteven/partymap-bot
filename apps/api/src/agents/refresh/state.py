"""State definition for Refresh Agent."""

from typing import Annotated, Optional, Any, List
from datetime import datetime
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field


class RefreshState(BaseModel):
    """State for the refresh agent that updates existing PartyMap events."""

    # Input - PartyMap data
    event_id: int
    event_date_id: int
    event_name: str

    # Current Event data (general info)
    current_event_data: dict = Field(default_factory=dict)
    # {name, description, full_description, url, youtube_url, tags, ...}

    # Current EventDate data
    current_event_date: dict = Field(default_factory=dict)
    # {start, end, description, lineup, ticket_url, tickets, ...}

    # Research search query
    search_query: str = ""  # e.g., "Coachella 2025 festival"

    # Research results
    search_results: List[dict] = Field(default_factory=list)
    official_url: Optional[str] = None

    # Proposed changes
    proposed_event_changes: dict = Field(default_factory=dict)  # Changes to main Event
    proposed_date_changes: dict = Field(default_factory=dict)  # Changes to EventDate

    # Change confidence
    date_confidence: float = 0.0
    lineup_confidence: float = 0.0
    description_confidence: float = 0.0

    # What we found
    found_official_site: bool = False
    date_verified: bool = False
    lineup_found: bool = False
    tickets_found: bool = False

    # Change summary for human review
    change_summary: List[str] = Field(default_factory=list)

    # For high-confidence auto-approval
    should_auto_approve: bool = False

    # Output
    needs_approval: bool = True
    approval_id: Optional[str] = None
    error: Optional[str] = None

    # Messages for LLM
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)

    # Iteration control
    iteration: int = 0
    max_iterations: int = 10

    class Config:
        arbitrary_types_allowed = True
