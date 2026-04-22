"""State definition for Research Agent."""

from typing import Annotated, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field


class ResearchState(BaseModel):
    """State for the research agent graph."""

    # Input
    festival_name: str
    source_url: str
    discovered_data: Optional[dict] = None

    # Workflow type (NEW: dual workflow support)
    workflow_type: str = Field(default="new", description="'new' or 'update'")
    partymap_event_id: Optional[int] = Field(default=None, description="Existing PartyMap event ID (for updates)")
    update_reasons: list[str] = Field(default_factory=list, description="Reasons for update (for updates)")
    existing_event_data: Optional[dict] = Field(default=None, description="Cached PartyMap event data (for updates)")

    # Browser state
    current_url: Optional[str] = None
    page_html: Optional[str] = None
    visited_urls: list[str] = Field(default_factory=list)

    # Collected data
    collected_data: dict = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)

    # Iteration control
    iteration: int = 0
    max_iterations: int = 15

    # Messages for LLM conversation
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)

    # Output
    final_result: Optional[dict] = None
    error: Optional[str] = None

    # Cost tracking and budget
    budget_cents: int = Field(default=50, description="Maximum research budget in cents")
    cost_tracker: dict = Field(default_factory=dict, description="Cost breakdown per tool")
    total_cost_cents: int = Field(default=0, description="Total cost spent")
    budget_exceeded: bool = Field(default=False, description="Whether budget was exceeded")

    # Token tracking
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ToolProgress(BaseModel):
    """Progress update for long-running tools."""

    tool_name: str
    tool_call_id: str
    progress: float  # 0.0 to 1.0
    message: str
    data: Optional[dict] = None
