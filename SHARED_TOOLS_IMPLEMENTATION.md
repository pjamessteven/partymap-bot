# Shared Playwright Tools Implementation

## Summary

This implementation creates a shared module for Playwright browser tools to reduce code duplication across all agents in the PartyMap Festival Bot.

## Files Created

### 1. `apps/api/src/agents/shared/browser_tools.py`
A shared module providing reusable browser automation tools:

- **NavigateTool**: Navigate to URLs with progress tracking
- **ClickTool**: Click elements by selector or text
- **ExtractContentTool**: Extract text/HTML from pages
- **ScreenshotTool**: Take screenshots (full page or element)
- **GetImagesTool**: Extract all images from page with metadata
- **create_browser_tools()**: Factory function to create all tools at once

### 2. `apps/api/src/services/musicbrainz_client.py`
MusicBrainz API client with rate limiting (1.1s between requests):

- **MusicBrainzClient**: Handles artist lookups with MBID
- **ArtistMatch**: Structured result with confidence scoring
- Rate limiting to comply with MusicBrainz API requirements

### 3. `apps/api/src/agents/research/cost_tracker.py`
Cost tracking system for budget enforcement:

- **CostTracker**: Tracks per-tool costs
- **CostBreakdown**: Detailed cost reporting
- Budget checking and enforcement
- Support for OpenRouter cost extraction

### 4. `apps/api/src/agents/research/tools_lineup.py`
Lineup extraction tool with MusicBrainz integration:

- **ExtractLineupTool**: Extracts artists from images
- Uses LLM vision for name extraction
- MusicBrainz MBID lookup for each artist
- Progress tracking and structured results

### 5. `apps/api/migrations/versions/0002_add_langgraph_checkpoints.py`
Alembic migration for LangGraph checkpoint tables:

- `checkpoints` table for state persistence
- `checkpoint_writes` table for pending writes
- `checkpoint_migrations` table for migration tracking
- Adds `cost_breakdown` column to `agent_threads`
- Adds `research_budget_cents` setting

## Files Modified

### 1. `apps/api/pyproject.toml`
Added dependencies:
- `langgraph-checkpoint-postgres>=2.0.0`
- `musicbrainzngs>=0.7.1`

### 2. `apps/api/src/agents/research/tools.py`
- Removed duplicate NavigateTool, ClickLinkTool, ScreenshotTool
- Imported shared tools from `browser_tools`
- Renamed specialized ScreenshotTool to ScreenshotLineupTool
- Added image URL validation to MediaSelectionTool
- Added cost_tracker support to tools

### 3. `apps/api/src/agents/research/nodes.py`
- Updated imports to use shared browser tools
- Added budget enforcement in tools_node
- Updated get_tools() to use create_browser_tools()

### 4. `apps/api/src/agents/research/state.py`
- Added cost tracking fields (budget_cents, cost_tracker, total_cost_cents, budget_exceeded)

### 5. `apps/api/src/api/agents.py`
- Added PartyMapClient and MusicBrainzClient to LangGraph config
- Added proper cleanup in finally block

## Benefits

1. **Reduced Duplication**: Common browser tools now live in one place
2. **Consistent Interface**: All tools use same progress tracking and error handling
3. **Easier Maintenance**: Changes to browser logic only needed in one place
4. **Better Testing**: Shared tools can be tested independently
5. **Cost Control**: Budget enforcement prevents runaway costs
6. **Artist Identification**: MusicBrainz integration provides canonical artist IDs

## Usage Example

```python
from src.agents.shared.browser_tools import create_browser_tools
from src.services.browser_service import BrowserService

# Create browser instance
browser = BrowserService(settings)
await browser.start()

# Create all shared tools
tools = create_browser_tools(browser, writer=callback)

# Use tools in agent
for tool in tools:
    result = await tool.ainvoke({"url": "https://example.com"})
```

## Next Steps

1. Migrate pipeline from old ResearchAgent to use LangGraph (pending)
2. Delete old ResearchAgent after migration (pending)
3. Update BrowserAgent/ExaBrowserSource to use shared tools (pending)
4. Run Alembic migration to create checkpoint tables
5. Test complete workflow end-to-end
