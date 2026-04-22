# Comprehensive Implementation Summary

## Overview
Implemented a complete festival discovery and research system with integrated PartyMap deduplication and separate Goabase sync pipeline.

## Phase 1: Database Schema Updates ✅

### New Festival States
```python
class FestivalState(str, PyEnum):
    # Discovery phase
    DISCOVERED = "discovered"
    NEEDS_RESEARCH_NEW = "needs_research_new"      # New festival
    NEEDS_RESEARCH_UPDATE = "needs_research_update"  # Existing event needs update
    
    # Research phase
    RESEARCHING = "researching"
    RESEARCHED = "researched"
    RESEARCHED_PARTIAL = "researched_partial"
    UPDATE_IN_PROGRESS = "update_in_progress"
    UPDATE_COMPLETE = "update_complete"
    
    # Sync phase
    SYNCING = "syncing"
    SYNCED = "synced"
    FAILED = "failed"
    SKIPPED = "skipped"
    NEEDS_REVIEW = "needs_review"
```

### New Fields in Festival Model
- `partymap_event_id: Optional[int]` - Changed from UUID to Integer (matching PartyMap API)
- `update_required: bool` - Whether festival needs updating
- `update_reasons: List[str]` - Reasons for update: ["missing_dates", "dates_unconfirmed", "location_change", "lineup_released", "event_cancelled"]
- `existing_event_data: Optional[dict]` - Cached PartyMap event data
- `workflow_type: Optional[str]` - "new" or "update"

### Migration
- File: `apps/api/migrations/versions/0003_add_update_workflow_fields.py`
- Changes partymap_event_id from UUID to Integer
- Adds new workflow fields
- Migrates existing festivals to new states

## Phase 2: Enhanced PartyMapClient ✅

### New Methods Added
```python
async def get_next_event_dates(self, event_id: int) -> List[dict]
async def update_event_partial(self, event_id: int, updates: dict, update_reasons: List[str]) -> bool
async def add_event_date_to_existing(self, event_id: int, event_date: EventDateData) -> Optional[int]
```

## Phase 3: Discovery Agent with Deduplication ✅

### Architecture
- **Exa Discovery**: Uses LLM-based deduplication with PartyMap search
- **Goabase**: Simple URL+modified_date deduplication (Phase 5)

### DeduplicationAgent
```python
class DeduplicationAgent:
    async def check_duplicate(
        self,
        discovered_name: str,
        discovered_location: str,
        discovered_dates: Optional[str],
        discovered_description: Optional[str],
        clean_name: Optional[str],
    ) -> DeduplicationResult
```

### LLM Prompt for Duplicate Detection
- Compares discovered festival with existing PartyMap events
- Returns: is_duplicate, confidence, update_reasons, reasoning
- Update reasons: missing_dates, dates_unconfirmed, location_change, lineup_released, event_cancelled, description_update, media_update, url_update

### Enhanced DiscoveryAgent
```python
async def discover_with_deduplication(
    self, 
    manual_query: Optional[str] = None,
    enable_deduplication: bool = True
) -> List[DiscoveredFestival]
```

## Phase 4: Research Agent Dual Workflow ✅

### ResearchState Enhancements
```python
class ResearchState:
    workflow_type: str = "new"  # or "update"
    partymap_event_id: Optional[int] = None
    update_reasons: List[str] = []
    existing_event_data: Optional[dict] = None
```

### Dual Planner Prompts
- `PLANNER_SYSTEM_PROMPT_NEW` - For new festivals (complete research)
- `PLANNER_SYSTEM_PROMPT_UPDATE` - For updates (focus on changed fields)

### Evaluator Node Updates
- Returns `workflow_info` with workflow_type, partymap_event_id, update_reasons
- Pipeline uses this to determine CREATE vs UPDATE action

## Phase 5: Goabase Sync Pipeline ✅

### Simple Deduplication Strategy
```python
# URL matching for duplicates
existing = await get_festival_by_url(url)

if not existing:
    # NEW festival
    create_festival(workflow_type="new")
elif modified_date > existing.modified_date:
    # UPDATE needed
    mark_for_update(workflow_type="update", update_reasons=["goabase_modified"])
else:
    # Unchanged, skip
    pass
```

### Features
- **Automatic sync**: Weekly (configurable: daily/weekly/monthly)
- **Manual trigger**: Start/Stop buttons in UI
- **Real-time progress**: Polling every 2 seconds when running
- **Full payload storage**: Goabase data stored in `discovered_data`

### Settings (in init_db.py)
```python
goabase_sync_enabled: bool = True
goabase_sync_frequency: str = "weekly"  # daily, weekly, monthly
goabase_sync_day: str = "sunday"  # monday-sunday
goabase_sync_hour: int = 2  # 0-23
```

### Files Created
- `apps/api/src/sources/goabase_sync.py` - Core sync logic
- `apps/api/src/tasks/goabase_tasks.py` - Celery tasks
- `apps/api/src/api/goabase.py` - API endpoints

### API Endpoints
```
POST /api/goabase/sync/start    # Manual trigger
POST /api/goabase/sync/stop     # Request stop
GET  /api/goabase/sync/status   # Get progress
GET  /api/goabase/settings      # Get settings
PUT  /api/goabase/settings      # Update settings
```

## Phase 6: Frontend Updates ✅

### GoabaseSyncPanel Component
Location: `apps/web/components/GoabaseSyncPanel.tsx`

Features:
- **Status Badge**: Shows "Running" or "Idle"
- **Progress Bar**: Real-time progress with percentage
- **Control Buttons**: Start/Stop sync
- **Results Display**: New, Updates, Unchanged, Errors counts
- **Settings Panel**: Enable/disable, frequency, day, hour
- **Auto-polling**: Updates every 2 seconds when running

### Integration with Settings Page
- Added to `apps/web/app/settings/page.tsx`
- Shows below Auto-Process card
- Uses React Query for data fetching
- Mutations for start/stop/settings updates

### API Library Updates
Added to `apps/web/lib/api.ts`:
```typescript
export async function startGoabaseSync()
export async function stopGoabaseSync()
export async function getGoabaseSyncStatus()
export async function getGoabaseSettings()
export async function updateGoabaseSettings()
```

### Type Definitions
Added to `apps/web/types/index.ts`:
```typescript
interface GoabaseSyncStatus {
  is_running: boolean
  progress_percentage: number
  total_found: number
  new_count: number
  update_count: number
  // ... etc
}

interface GoabaseSettings {
  goabase_sync_enabled: boolean
  goabase_sync_frequency: 'daily' | 'weekly' | 'monthly'
  goabase_sync_day: string
  goabase_sync_hour: number
}
```

## Files Created/Modified

### Backend
1. `apps/api/migrations/versions/0003_add_update_workflow_fields.py` - Database migration
2. `apps/api/src/agents/deduplication.py` - LLM-based deduplication agent
3. `apps/api/src/sources/goabase_sync.py` - Goabase sync logic
4. `apps/api/src/tasks/goabase_tasks.py` - Celery tasks
5. `apps/api/src/api/goabase.py` - API endpoints
6. `apps/api/scripts/init_db.py` - Added Goabase settings
7. `apps/api/src/partymap/client.py` - Enhanced with new methods
8. `apps/api/src/agents/discovery.py` - Refactored, removed Goabase
9. `apps/api/src/agents/research/state.py` - Added workflow fields
10. `apps/api/src/agents/research/nodes.py` - Dual workflow support
11. `apps/api/src/core/models.py` - New states and fields
12. `apps/api/src/core/schemas.py` - Updated DiscoveredFestival
13. `apps/api/src/main.py` - Added goabase router

### Frontend
1. `apps/web/components/GoabaseSyncPanel.tsx` - New component
2. `apps/web/app/settings/page.tsx` - Integrated Goabase panel
3. `apps/web/lib/api.ts` - Added Goabase API functions
4. `apps/web/types/index.ts` - Added Goabase types

## How It Works

### Discovery Flow (Exa)
1. DiscoveryAgent searches Exa for festivals
2. For each festival:
   - Searches PartyMap for potential matches
   - Uses LLM to determine if duplicate
   - If duplicate: Sets `workflow_type="update"`, `partymap_event_id`, `update_reasons`
   - If new: Sets `workflow_type="new"`
3. Stores in DB with appropriate state (NEEDS_RESEARCH_NEW or NEEDS_RESEARCH_UPDATE)

### Goabase Flow
1. GoabaseSync fetches all parties from Goabase API
2. For each party:
   - Checks if URL exists in DB
   - Compares modified_date with stored date
   - If new URL: Creates with `workflow_type="new"`
   - If modified_date newer: Updates with `workflow_type="update"`
3. Skips LLM deduplication (already deduplicated by URL)

### Research Flow
1. Research pipeline picks up festival from DB
2. Checks `workflow_type`:
   - If "new": Full research → Create in PartyMap
   - If "update": Research changes → Update existing PartyMap event
3. Uses `update_reasons` to focus on specific fields

### Sync Flow
1. After successful research
2. If `workflow_type="new"`: POST /api/event/ to create
3. If `workflow_type="update"`: PUT /api/event/{id} to update

## Cost Estimates

| Operation | Cost |
|-----------|------|
| Exa search | $0.10 |
| LLM deduplication | ~$0.05 per festival |
| Goabase fetch | $0.05 (API call) |
| Research (DeepSeek) | ~$0.02-0.10 |
| Vision (GPT-4o-mini) | ~$0.01-0.03 |

At 100 festivals/day:
- Exa + deduplication: ~$15/day
- Goabase (weekly): ~$0.01/day average
- Research: ~$5-10/day
- **Total: ~$20-25/day**

## Next Steps

1. **Run migrations**: `alembic upgrade head`
2. **Test Goabase sync**: Use UI to trigger manual sync
3. **Test discovery**: Run discovery pipeline with deduplication
4. **Monitor costs**: Check daily cost logs
5. **Tune LLM prompts**: Based on deduplication accuracy
6. **Add tests**: Unit tests for deduplication logic

## Architecture Diagram

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Exa Search     │────▶│  Deduplication   │────▶│  Store in DB    │
│  (Discovery)    │     │  (LLM + PartyMap)│     │  (new/update)   │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
┌─────────────────┐     ┌──────────────────┐              │
│  Goabase API    │────▶│  URL+Date Check  │──────────────┘
│  (Sync Weekly)  │     │  (Simple)        │
└─────────────────┘     └──────────────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Create in      │◄────│  Research Agent  │◄────│  Pick up from   │
│  PartyMap       │     │  (Dual Workflow) │     │  DB             │
│  (POST /event)  │     │                  │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │
                               │ workflow_type="update"
                               ▼
                        ┌──────────────────┐
                        │  Update PartyMap │
                        │  (PUT /event/id) │
                        └──────────────────┘
```

All implementations complete! 🚀
