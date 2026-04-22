# PartyMap Festival Bot

A comprehensive bot for discovering and researching music festivals worldwide for PartyMap.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         PARTYMAP FESTIVAL BOT v4                                    │
│                    (Pipeline with Agentic Stages + Manual Control)                  │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         DATABASE-DRIVEN SCHEDULING                          │   │
│  │                                                                             │   │
│  │  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐       │   │
│  │  │PipelineSchedule │     │ SystemSettings  │     │ DiscoveryQuery  │       │   │
│  │  │  (Celery Beat)  │     │ (Configuration) │     │  (28 queries)   │       │   │
│  │  │                 │     │                 │     │                 │       │   │
│  │  │• discovery      │     │• auto_process   │     │• Countries      │       │   │
│  │  │• goabase_sync   │     │• max_cost_*     │     │• Cities         │       │   │
│  │  │• cleanup_failed│     │• research_*     │     │• Genres         │       │   │
│  │  │                 │     │                 │     │                 │       │   │
│  │  │All DISABLED by  │     │auto_process=    │     │Rotates: 3/day   │       │   │
│  │  │default          │     │FALSE by default │     │                 │       │   │
│  │  └─────────────────┘     └─────────────────┘     └─────────────────┘       │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         CELERY TASK PIPELINE                                │   │
│  │                                                                             │   │
│  │   Celery Beat (DatabaseScheduler)                                           │   │
│  │        │                                                                    │   │
│  │        ▼                                                                    │   │
│  │   ┌─────────┐    ┌─────────────┐    ┌──────────────┐    ┌──────────┐       │   │
│  │   │Discovery│───►│ Deduplication│───►│   Research   │───►│   Sync   │       │   │
│  │   │ Pipeline│    │    Check     │    │   Pipeline   │    │ Pipeline │       │   │
│  │   │         │    │              │    │              │    │          │       │   │
│  │   │ Queue:  │    │  Queue: dedup│    │ Queue:research│   │ Queue:sync│      │   │
│  │   │discovery│    │              │    │              │    │          │       │   │
│  │   └────┬────┘    └──────┬───────┘    └──────┬───────┘    └────┬─────┘       │   │
│  │        │                │                   │                 │             │   │
│  │   ┌────┴────┐      ┌────┴────┐        ┌─────┴──────┐     ┌────┴────┐        │   │
│  │   │ Discovery│      │PartyMap │        │ Research   │     │PartyMap │        │   │
│  │   │  Agent   │      │  API    │        │  Agent     │     │  API    │        │   │
│  │   │          │      │(duplicate│       │ (ReAct)    │     │ (create/│        │   │
│  │   │• Exa     │      │ check)  │        │            │     │ update) │        │   │
│  │   │• Goabase │      │         │        │• Playwright│     │         │        │   │
│  │   │          │      │         │        │• DeepSeek  │     │         │        │   │
│  │   └──────────┘      └─────────┘        └────────────┘     └─────────┘        │   │
│  │                                                                             │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         MANUAL CONTROL LAYER                                │   │
│  │                                                                             │   │
│  │   When auto_process=false (Manual Mode):                                    │   │
│  │                                                                             │   │
│  │   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                 │   │
│  │   │  DISCOVERED  │───►│  RESEARCHING │───►│  RESEARCHED  │                 │   │
│  │   │              │    │              │    │              │                 │   │
│  │   │Manual trigger│    │Manual trigger│    │Manual trigger│                 │   │
│  │   │/deduplicate  │    │/research     │    │/sync         │                 │   │
│  │   └──────────────┘    └──────────────┘    └──────────────┘                 │   │
│  │          │                   │                   │                          │   │
│  │          ▼                   ▼                   ▼                          │   │
│  │   [No auto-queue]    [No auto-queue]     [No auto-queue]                    │   │
│  │                                                                             │   │
│  │   API Endpoints:                                                            │   │
│  │   • GET  /api/festivals/pending        - List festivals needing action      │   │
│  │   • POST /api/festivals/{id}/deduplicate - Run dedup check                  │   │
│  │   • POST /api/festivals/{id}/research    - Queue research                   │   │
│  │   • POST /api/festivals/{id}/sync        - Queue sync                       │   │
│  │   • POST /api/festivals/{id}/skip        - Skip festival                    │   │
│  │   • POST /api/festivals/{id}/reset       - Reset to earlier state           │   │
│  │                                                                             │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         AGENT ARCHITECTURE                                  │   │
│  │                                                                             │   │
│  │   DISCOVERY AGENT                           RESEARCH AGENT (ReAct)          │   │
│  │   ───────────────                           ────────────────────            │   │
│  │                                                                             │   │
│  │   Inputs:                                   Inputs:                         │   │
│  │   • Query rotation (28 queries)             • Festival name                 │   │
│  │   • Manual query override                   • source_url                    │   │
│  │   • Goabase/Exa sources                     • discovered_data               │   │
│  │                                                                             │   │
│  │   Cost: $2.00 max/run                       Cost: $0.50 max/festival        │   │
│  │                                                                             │   │
│  │   Outputs:                                  Outputs:                        │   │
│  │   • DiscoveredFestival[]                    • FestivalData                  │   │
│  │   • Decision logs                           • EventDateData[]               │   │
│  │   • Cost tracking                           • AgentDecisionLog[]            │   │
│  │                                             • Cost tracking                 │   │
│  │                                             • Required: name, date, loc     │   │
│  │                                                                             │   │
│  │   Tools:                                    Tools (ReAct loop):             │   │
│  │   • Exa search ($0.10)                      • navigate (free)               │   │
│  │   • Goabase fetch ($0.05)                   • extract_data ($0.05)          │   │
│  │   • Filter non-festivals                    • click_link (free)             │   │
│  │                                             • screenshot ($0.10)            │   │
│  │                                             • search_alternatives ($0.10)   │   │
│  │                                                                             │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                      FESTIVAL STATE MACHINE (PostgreSQL)                    │   │
│  │                                                                             │   │
│  │   [discovered] ──dedup──► [researching] ──research──► [researched]          │   │
│  │        │                       │                         │                   │   │
│  │        │ (if dup & up-to-date) │                         │ (validate)        │   │
│  │        └───────────────────────┴─────────────────────────┤                   │   │
│  │                                │                         ▼                   │   │
│  │                                │                  [validating]                │   │
│  │                                │                         │                   │   │
│  │                                │              ┌──────────┴──────────┐        │   │
│  │                                │              ▼                     ▼        │   │
│  │                                │    [validation_failed]      [syncing]       │   │
│  │                                │         (retry)                  │          │   │
│  │                                │              └────────► [synced] ◄──────────┘   │   │
│  │                                │                            │                   │   │
│  │                                ▼                            │ (error)          │   │
│  │                           [failed] ─────────────────────────┘                   │   │
│  │                              │                                                  │   │
│  │                    (5 retries)                                                  │   │
│  │                              ▼                                                  │   │
│  │                        [quarantined] ──► (30 days) ──► [purged]                │   │
│  │                              │                                                  │   │
│  │                              └───► [manual retry]                              │   │
│  │                                                                             │   │
│  │   Manual states:                                                             │   │
│  │   [skipped] - Manually excluded                                             │   │
│  │   [needs_review] - Requires human intervention                              │   │
│  │                                                                             │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## Core Strategy

### 1. Database-Driven Scheduling

**No hardcoded schedules!** All schedules stored in `pipeline_schedules` table:

```
┌────────────────────────────────────────────────────────────────┐
│                 PipelineSchedule Table                          │
├────────────────────────────────────────────────────────────────┤
│ task_type      │ enabled │ hour │ minute │ day_of_week         │
├────────────────────────────────────────────────────────────────┤
│ discovery      │ false   │ 2    │ 0      │ null (daily)        │
│ goabase_sync   │ false   │ 2    │ 0      │ 0 (Monday)          │
│ cleanup_failed │ false   │ 3    │ 0      │ null (daily)        │
└────────────────────────────────────────────────────────────────┘
```

**Features:**
- All schedules **disabled by default** (never runs until you enable)
- Configurable via API (`/api/schedule/*`)
- Custom `DatabaseScheduler` reads from database every 60 seconds
- Stores `last_run_at` and `next_run_at` for visibility

### 2. Auto vs Manual Mode

**Auto Mode** (`auto_process=true`):
```
Discovery → Deduplication → (auto-queue) → Research → (auto-queue) → Sync
```

**Manual Mode** (`auto_process=false`):
```
Discovery → Deduplication (stops) → [MANUAL TRIGGER] → Research (stops) → [MANUAL] → Sync
```

**Use Cases:**
- **Production**: Enable auto_process, enable schedules
- **Testing**: Disable auto_process, manually trigger each stage
- **Debugging**: Run deduplication only, inspect results, then decide on research

### 3. Event Series Model

**One Event = Festival Series** (e.g., "Boom Festival")
**Multiple EventDates = Specific Occurrences** (e.g., "Boom 2026, July 15-22, Portugal")

**Data Separation:**
- **Event object**: General info (name, description, images, website, YouTube, tags)
- **EventDate objects**: Date-specific info (start/end dates, location, lineup, tickets, size)

This allows a festival series to have multiple dates/locations without creating duplicate events.

### 4. Deduplication Strategy

**CRITICAL: Check for duplicates BEFORE researching!**

```
Discovery → Deduplication Check → Research → Sync
                ↓
    If duplicate found:
    - If new date for existing series → Add EventDate
    - If existing date but date_confirmed=false → Update
    - If up to date → Skip
```

**Duplicate Detection:**
1. Match by source URL (most reliable)
2. Match by name + location similarity
3. Check if same event series (different year/location = new EventDate)

**Update Strategy:**
- **General info** (description, images, URL) → `PUT /events/{id}`
- **Date-specific info** (dates, location, lineup, tickets) → `POST /api/date/event/{id}` or `PUT /api/date/event/{id}/{date_id}`
- **NEVER update date_time/location/rrule on main Event** (would delete future EventDates!)

### 5. Discovery Agent

**Rotating Query System:**
- 28 pre-populated queries (countries, cities, genres)
- Runs 3 queries per day (configurable)
- Remembers position in rotation via database
- Can be manually triggered with custom query

**Sources:**

**1. Exa API (Primary)**
- Neural search engine (semantic understanding, not keyword matching)
- Searches entire web for festival announcements
- Content extraction from result pages
- Cost: ~$0.10 per search
- Query rotation: 28 pre-populated queries (countries, cities, genres)
- Filters: Domain include/exclude, date ranges

**2. Goabase (Psytrance/Underground)**
[Goabase](https://www.goabase.net/) is the world's largest database for psychedelic and underground parties. Integration provides:

- **Event types**: Psytrance festivals, transformational gatherings, burner events, underground techno/house parties, Full Moon gatherings
- **Data format**: JSON-LD structured data with rich metadata
- **Sync modes**:
  - Scheduled sync (daily/weekly/monthly configurable)
  - Manual sync on demand
  - Incremental updates based on `goabase_modified` timestamps
- **Mapping**: Goabase fields → PartyMap schema (location, lineup, dates, tags)
- **Unique features**: 
  - GPS coordinates for outdoor events
  - Underground/alternative events not on mainstream platforms
  - Community-driven event quality ratings

**Cost Limit:** $2.00 per discovery run

**Filters:**
- Removes city names + year (e.g., "Miami 2026")
- Removes generic terms (e.g., "Party 2026")
- Deduplicates by source_url

### 6. Research Agent (ReAct Pattern)

**All-or-Nothing Approach:**
- Must fill ALL required fields or fail
- Required: name, description, start date, end date, location
- Max cost: $0.50 per festival
- Max 3 retries, then mark as FAILED

**ReAct Loop (Reasoning + Acting):**
```
1. Observe current state (collected data, missing fields)
2. Think - LLM decides next action
3. Execute tool action
4. Observe result
5. Repeat until complete (max 15 iterations)
```

**Tools:**
- `navigate` - Go to URL (free)
- `extract_data` - Parse HTML with LLM ($0.05)
- `click_link` - Navigate deeper (free)
- `screenshot` - Capture lineup images via vision LLM ($0.10)
- `search_alternatives` - Find other sources via Exa ($0.10)

**If incomplete:** Agent searches alternative sources before failing.

### 7. State Machine

Festivals progress through states:

```
discovered → researching → researched → syncing → synced
                ↓
            failed (30 days → purged)
                
Manual transitions:
- Skip (with reason)
- Force retry
- Force sync
- Reset to earlier state
```

Each transition is logged for audit trail.

### 8. Cost Tracking

**Budgets:**
- Per festival research: $0.50 max
- Per discovery run: $2.00 max  
- Per day: $10.00 max (configurable)

**Tracking:**
- Every API call logged with cost
- Can view costs per festival, per day, per agent
- Research agent tracks cumulative cost and stops if exceeded

### 9. Manual Control API

**Settings:**
```bash
# Check current mode
GET /api/settings/auto-process/status

# Enable auto mode (production)
PUT /api/settings/auto-process/enable

# Disable auto mode (manual testing)
PUT /api/settings/auto-process/disable
```

**Festival Actions:**
```bash
# List festivals needing action
GET /api/festivals/pending

# Run deduplication check
POST /api/festivals/{id}/deduplicate

# Queue research
POST /api/festivals/{id}/research

# Queue sync
POST /api/festivals/{id}/sync

# Skip festival
POST /api/festivals/{id}/skip?reason="Not a festival"

# Reset to earlier state
POST /api/festivals/{id}/reset?target_state=DISCOVERED
```

## Data Flow

### Phase 1: Discovery
```
Discovery Agent → Festival (state=discovered)
└─→ Save to DB with discovered_data
```

### Phase 2: Deduplication (before research!)
```
Check PartyMap API:
├─→ If exists + date_confirmed=false → Mark for update
├─→ If exists + new date → Mark as new EventDate
├─→ If exists + up to date → Skip
└─→ If new → Proceed to research
```

In **manual mode**, the festival stays in `RESEARCHING` state and waits for manual trigger.

### Phase 3: Research
```
Research Agent → Festival (state=researched)
├─→ Browser navigates to source_url
├─→ Extracts general info → festival_data.general
├─→ Extracts date info → festival_data.event_dates[]
└─→ Save to DB with research_data
```

In **manual mode**, the festival stays in `RESEARCHED` state and waits for manual sync.

### Phase 4: Validation & Sync
```
Pre-flight Validation → PartyMap Sync:
├─→ PartyMapSyncValidator.check()
│   ├─→ Required fields: name, description, full_description, event_dates, logo
│   ├─→ Date validation: end > start, dates in future
│   ├─→ Location validation
│   ├─→ Price validation
│   └─→ Completeness score (0.0 - 1.0)
│
├─→ If valid (status=ready):
│   ├─→ state → SYNCING
│   └─→ Sync to PartyMap
│
├─→ If warnings (status=needs_review):
│   ├─→ Auto-process: continue to sync
│   └─→ Manual mode: stop for review
│
└─→ If invalid (status=validation_failed):
    └─→ Store errors, wait for manual fix
```

### Phase 5: Error Handling
```
On Sync/Research Error:
├─→ ErrorClassifier.categorize(error)
│   ├─→ TRANSIENT: Rate limit, timeout, connection error → Retry with backoff
│   ├─→ PERMANENT: 4xx errors (except 429), auth failure → Mark FAILED
│   ├─→ VALIDATION: Schema mismatch, missing fields → Mark VALIDATION_FAILED
│   ├─→ EXTERNAL: PartyMap API down → Retry later
│   ├─→ BUDGET: Cost limit exceeded → Quarantine
│   └─→ UNKNOWN: Uncategorized → Retry once
│
├─→ CircuitBreaker.check()
│   ├─→ 5 failures in 60s → OPEN (fails fast)
│   └─→ 30s timeout → HALF_OPEN (test recovery)
│
├─→ Retry count >= 5:
│   ├─→ Move to QUARANTINED state
│   ├─→ Store in Dead Letter Queue
│   └─→ Manual retry only via Error Dashboard
│
└─→ Quarantine retention: 30 days → Auto-purge
```

## Error Resilience Architecture

### Circuit Breakers
Prevents cascading failures when external APIs are down or rate-limited.

**Configuration:**
- **Failure threshold**: 5 failures in 60-second window
- **Recovery timeout**: 30 seconds before attempting recovery
- **Half-open max calls**: 3 test calls in half-open state
- **Success threshold**: 2 successes to close from half-open

**Services protected:**
- PartyMap API (5 failures / 30s recovery)
- Exa API (5 failures / 30s recovery)
- LLM/OpenRouter (3 failures / 60s recovery - more cautious due to cost)

**States:**
```
CLOSED → (5 failures) → OPEN → (30s) → HALF_OPEN → (2 successes) → CLOSED
                            ↓
                    (failure in half-open) → OPEN
```

### Dead Letter Queue (DLQ)
Quarantines festivals that have failed repeatedly and cannot be processed automatically.

**Quarantine triggers:**
- 5 failed retry attempts
- Permanent error classification
- Budget limit exceeded

**DLQ features:**
- 30-day retention period
- Manual retry only (no automatic retry)
- Bulk retry capability
- Cleanup job removes expired entries
- Error categorization for debugging

**API endpoints:**
- `GET /api/errors/quarantined` - List quarantined festivals
- `POST /api/errors/quarantined/{id}/retry` - Retry single festival
- `POST /api/errors/quarantined/bulk-retry` - Bulk retry
- `POST /api/errors/cleanup` - Remove expired entries

### Error Classification
Automatic categorization enables smart retry decisions:

| Category | Examples | Retry Strategy |
|----------|----------|----------------|
| **TRANSIENT** | Rate limit (429), timeout, connection reset | Exponential backoff: 2min, 4min, 8min... |
| **PERMANENT** | 404, 401/403 auth, validation errors | Don't retry, mark FAILED |
| **VALIDATION** | Schema mismatch, missing required fields | Don't retry, mark VALIDATION_FAILED |
| **EXTERNAL** | PartyMap API 5xx errors | Retry with backoff |
| **BUDGET** | Cost limit, quota exceeded | Quarantine immediately |
| **UNKNOWN** | Uncategorized | Retry once, then quarantine |

### Validation System
Pre-flight validation prevents wasting API calls on data that will definitely fail.

**PartyMapSyncValidator checks:**
1. **Required fields**: name, description (≥10 chars), full_description (≥20 chars)
2. **Event dates**: At least one date, end > start, dates in future (warning)
3. **Location**: location_description required
4. **Media**: logo_url required for sync
5. **URLs**: Valid format for website_url, youtube_url
6. **Prices**: max >= min for ticket prices
7. **Tags**: Max 5 tags (PartyMap limit)

**Validation results:**
- `ready` - All checks pass, can sync
- `needs_review` - Warnings present but can proceed
- `invalid` - Errors present, cannot sync

**Completeness score:** 0.0-1.0 based on required vs optional fields present

## Refresh Pipeline

Monitors and updates existing PartyMap events with unconfirmed dates.

**When it runs:**
- Scheduled: Checks events 120 days ahead
- Manual: Trigger via `/api/refresh/trigger`

**What it does:**
1. Query PartyMap for events with `date_unconfirmed=true`
2. Re-research each event to verify/correct information
3. Queue changes for approval (human-in-the-loop)
4. Auto-cancel events that remain unconfirmed 30 days before start

**Approval workflow:**
```
Refresh Agent → Proposed Changes → Pending Approval
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    ▼                      ▼                      ▼
                [Approve]              [Reject]               [Auto]
                    │                      │                      │
                    ▼                      ▼                      ▼
            Apply changes           Discard changes          Auto-approved
            to PartyMap                                       (high confidence)
```

**API endpoints:**
- `GET /api/refresh/approvals` - List pending approvals
- `POST /api/refresh/approvals/{id}/approve` - Approve changes
- `POST /api/refresh/approvals/{id}/reject` - Reject changes
- `POST /api/refresh/trigger` - Manually trigger refresh

## Streaming Architecture (LangGraph Compatible)

Real-time streaming of AI agent progress using Server-Sent Events (SSE).

**Purpose:** Frontend uses LangGraph's `useStream()` hook which expects specific SSE format.

**Endpoint:** `GET /api/threads/{thread_id}/runs/stream?stream_mode=messages,custom,tools`

**SSE Event Format:**
```
event: metadata
data: {"thread_id": "research_abc123", "status": "running"}

event: messages
data: [{"type": "ai", "data": {"content": "Researching..."}}, {"run_id": "run_123"}]

event: custom
data: {"type": "reasoning", "data": {"step": "searching"}, "timestamp": "2026-01-01T00:00:00"}

event: tools
data: {"toolCallId": "call_123", "name": "web_search", "state": "starting", "input": "festival 2026"}

event: end
data: {"status": "success"}
```

**Critical format requirements for UseStream() compatibility:**
- `messages` event: data MUST be `[messageDict, metadataDict]` (array of 2 elements)
- `custom` event: data MUST have `type` and `data` fields
- `tools` event: data MUST have `toolCallId`, `name`, `state`
- `end` event: data MUST have `status: "success"` or `"completed"`
- `ping` event: sent every 30 seconds as keepalive

**Stream modes (query parameter):**
- `messages` - Agent messages and responses
- `updates` - State updates
- `custom` - Custom events (reasoning, evaluation, tool_progress)
- `tools` - Tool execution status
- `events` - All LangGraph events
- `debug` - Debug information

**Historical replay:**
- On connection: Replays all historical events from database
- Then bridges to live broadcaster for real-time updates
- Ensures no gap between history and live stream

## Unit Testing Strategy

Comprehensive test suite with 211+ tests covering all critical paths.

**Test organization:**
```
tests/
├── unit/                    # Fast unit tests (SQLite in-memory)
│   ├── test_errors_router.py       # DLQ, circuit breakers, validation
│   ├── test_festivals_router.py    # Festival CRUD, sync, research
│   ├── test_refresh_router.py      # Refresh approvals
│   ├── test_agents_router.py       # SSE streaming conformance
│   ├── test_schedule_router.py     # Schedule management
│   ├── test_settings_router.py     # System settings
│   ├── test_validators.py          # PartyMapSyncValidator
│   ├── test_dead_letter_queue.py   # DLQ operations
│   └── test_circuit_breaker.py     # Circuit breaker states
└── integration/             # Integration tests (PostgreSQL)
    └── test_integration.py
```

**Testing approach:**
- **Unit tests**: SQLite in-memory, mocked external APIs, 80%+ coverage requirement
- **Integration tests**: Real PostgreSQL + Redis via docker-compose.test.yml
- **Streaming tests**: Verify SSE format matches UseStream() expectations
- **Circuit breaker tests**: State machine transitions, timeout behavior

**Key fixtures:**
- `async_client` - HTTPX client for FastAPI testing
- `db_session` - Async SQLAlchemy session with rollback
- `mock_celery_tasks` - Mocked Celery task functions
- `mock_partymap_client` - Mocked PartyMap API client
- `mock_broadcaster` - Mocked StreamBroadcaster for streaming tests

**Coverage requirements:**
- New endpoints: 100% coverage
- Core services: 90% coverage
- Overall: 80% minimum (enforced in CI)

**Running tests:**
```bash
# Unit tests (SQLite, fast)
pytest tests/unit/ -v --cov=src --cov-fail-under=80

# Integration tests (PostgreSQL + Redis)
docker-compose -f docker-compose.test.yml up --abort-on-container-exit

# All tests during Docker build (fails build if tests fail)
docker build -t partymap-api apps/api/
```

## Tech Stack

- **Language**: Python 3.12
- **Web Framework**: FastAPI
- **Database**: PostgreSQL 15 + SQLAlchemy 2.0 (async + sync)
- **Task Queue**: Celery + Redis
- **Agents**: Custom ReAct implementation (no LangChain)
- **Browser**: Playwright (runs in Docker container)
- **LLM**: DeepSeek via OpenRouter
- **Search**: Exa API
- **Testing**: pytest + pytest-asyncio
- **Container**: Docker + docker-compose

## Project Structure

```
partymap-bot/
├── src/
│   ├── agents/           # DiscoveryAgent, ResearchAgent
│   ├── core/             # Database models, schemas, settings
│   ├── tasks/            # Celery tasks, custom scheduler
│   │   ├── scheduler.py  # DatabaseScheduler (custom Celery Beat)
│   │   ├── pipeline.py   # Main pipeline tasks
│   │   └── celery_app.py # Celery configuration
│   ├── partymap/         # API client, deduplication, sync
│   ├── dashboard/        # API routes
│   │   ├── router.py         # Main festival endpoints
│   │   ├── schedule_router.py # Schedule management
│   │   └── settings_router.py # System settings + manual actions
│   ├── services/         # LLM client, Exa client
│   ├── config.py         # Settings
│   └── main.py           # FastAPI entry
├── tests/                # Unit and integration tests
├── scripts/              # Database initialization
├── docker-compose.yml    # Services (app, db, redis, worker, scheduler)
├── Dockerfile            # App container with Playwright
└── pyproject.toml        # Dependencies
```

## Database Tables

### Core Tables

1. **festivals** - Core festival data with state machine and error tracking
   - `state` - Current state in lifecycle (discovered, researching, researched, validating, validation_failed, syncing, synced, failed, quarantined, skipped)
   - `research_data` - JSONB with full FestivalData from research agent
   - `validation_status` - Pre-sync validation result (pending, ready, needs_review, invalid)
   - `validation_errors` - JSONB array of validation errors
   - `validation_warnings` - JSONB array of validation warnings
   - `error_category` - Classification of last error (transient, permanent, validation, external, budget, unknown)
   - `error_context` - JSONB with detailed error info for debugging
   - `retry_count` - Number of retry attempts
   - `max_retries_reached` - Boolean flag for quarantine eligibility
   - `quarantined_at` - Timestamp when moved to DLQ
   - `quarantine_reason` - Why festival was quarantined
   - `first_error_at`, `last_retry_at` - Error tracking timestamps

2. **festival_event_dates** - Individual dates for festival series

3. **refresh_approvals** - Pending changes from refresh pipeline awaiting human approval
   - `event_id`, `event_date_id` - PartyMap IDs being updated
   - `proposed_changes` - JSONB with event and event_date changes
   - `change_summary` - Human-readable list of changes
   - `research_confidence` - AI confidence score (0.0-1.0)
   - `status` - pending, auto_approved, approved, rejected, applied

### Agent & Streaming Tables

4. **agent_threads** - Active and completed agent runs
   - `thread_id` - Unique identifier for streaming
   - `festival_id` - Associated festival
   - `agent_type` - discovery, research, refresh
   - `status` - running, completed, failed
   - `total_tokens`, `cost_cents` - Usage tracking

5. **agent_stream_events** - Persisted stream events for historical replay
   - `thread_id` - Parent thread
   - `event_type` - messages, custom, tools, error, etc.
   - `event_data` - JSONB payload
   - `event_index` - Ordering for replay

6. **agent_decisions** - Summarized agent decision logs

### Configuration & Control Tables

7. **discovery_queries** - Query rotation (28 pre-populated)

8. **pipeline_schedules** - Celery Beat schedule configuration
   - `task_type` - discovery, goabase_sync, cleanup_failed, refresh
   - `enabled` - Boolean flag
   - `hour`, `minute`, `day_of_week` - Cron-like scheduling
   - `last_run_at`, `next_run_at` - Execution tracking

9. **system_settings** - Global configuration
   - `auto_process` - Enable/disable automatic pipeline progression
   - `max_cost_per_day` - Daily budget limit
   - Various research/sync settings

### Supporting Tables

10. **state_transitions** - Complete audit trail of all state changes

11. **cost_logs** - Detailed cost tracking per API call

12. **job_activity** - Background job execution history

13. **name_mappings** - Raw→clean name mappings for deduplication

## Key Design Decisions

### Pipeline & Data Flow

1. **Deduplication Before Research**: Saves API costs by not researching known festivals
2. **Event/EventDate Split**: Supports festival series with multiple dates/locations
3. **All-or-Nothing Research**: Ensures data quality (no partial entries)
4. **No Main Event Date Updates**: Prevents accidental deletion of future EventDates
5. **State Machine**: Clear lifecycle with retry logic and audit trail
6. **Query Rotation**: Systematic coverage of countries, cities, genres
7. **Database-Driven Scheduling**: No hardcoded schedules, fully configurable via API
8. **Auto/Manual Mode**: Full control for testing individual pipeline stages

### Error Resilience

9. **Pre-flight Validation**: Validates festival data BEFORE attempting PartyMap sync (prevents wasting API calls)
10. **Circuit Breakers**: Prevents cascading failures when external APIs are down (5 failures/60s threshold)
11. **Dead Letter Queue**: Quarantines persistently failed festivals for manual review (30-day retention)
12. **Error Classification**: Automatic categorization enables smart retry decisions (transient/permanent/validation/external/budget)
13. **Exponential Backoff**: Retry delays increase with each attempt (2min, 4min, 8min...)

### Quality & Monitoring

14. **Cost Tracking**: Budget enforcement per festival, run, and day with detailed logs
15. **Completeness Scoring**: 0.0-1.0 score indicates data quality before sync
16. **Human-in-the-Loop**: Refresh pipeline requires approval for high-stakes changes
17. **Summarized Logs**: Agent decisions logged but condensed for readability
18. **Real-time Streaming**: SSE format compatible with LangGraph's UseStream() hook

### Testing & Reliability

19. **Comprehensive Test Suite**: 211+ unit tests with 80%+ coverage requirement
20. **Build-time Testing**: Docker build fails if tests fail (prevents bad deployments)
21. **CI/CD Integration**: GitHub Actions runs tests on every PR/push
22. **Swagger Documentation**: All endpoints documented with OpenAPI

## Environment Variables

See `.env.example` for full configuration.

Key variables:
- `PARTYMAP_API_KEY` - PartyMap API (mocked for now)
- `OPENROUTER_API_KEY` - DeepSeek LLM access
- `EXA_API_KEY` - Web search
- `DATABASE_URL` - PostgreSQL
- `REDIS_URL` - Celery broker
- `MAX_COST_*` - Budget limits in cents

## Running Locally

```bash
# Start services
docker-compose up -d

# Initialize database
docker-compose exec app python scripts/init_db.py

# Access Swagger docs (all endpoints documented)
open http://localhost:8000/docs

# View logs
docker-compose logs -f worker
docker-compose logs -f scheduler

# Enable auto-process (production mode)
curl -X PUT http://localhost:8000/api/settings/auto-process/enable

# Or stay in manual mode for testing
curl -X PUT http://localhost:8000/api/settings/auto-process/disable
```

## Testing Strategy

- **Unit tests**: Mocked LLM/tools, test agent logic
- **Integration tests**: Database operations, API client
- **Pipeline tests**: Full flow with test fixtures
- **Async testing**: pytest-asyncio
- **Manual testing**: Use manual mode to step through each stage

## Manual Testing Workflow

```bash
# 1. Ensure manual mode
curl -X PUT http://localhost:8000/api/settings/auto-process/disable

# 2. Run discovery
curl -X POST http://localhost:8000/api/discovery/run

# 3. Check pending festivals
curl http://localhost:8000/api/festivals/pending

# 4. Run deduplication for a specific festival
curl -X POST http://localhost:8000/api/festivals/{id}/deduplicate

# 5. Queue research
curl -X POST http://localhost:8000/api/festivals/{id}/research

# 6. Check status (repeat until researched)
curl http://localhost:8000/api/festivals/{id}

# 7. Queue sync
curl -X POST http://localhost:8000/api/festivals/{id}/sync
```

## Dashboard Features

- **Stats**: Festivals by state, today's cost, budget usage
- **Festival List**: Filter by state, source, search by name
- **Festival Details**: View data, agent decisions, cost breakdown
- **Manual Actions**: Deduplicate, Research, Sync, Skip, Retry, Reset
- **Schedule Management**: Enable/disable tasks, configure times
- **Settings**: Toggle auto/manual mode, view system config
- **Query Management**: Enable/disable/edit discovery queries
- **Cost Reports**: Daily/weekly cost tracking
- **Swagger UI**: Full API documentation at `/docs`

## Troubleshooting

**Festival stuck in researching:**
- Check worker logs: `docker-compose logs worker`
- May have hit cost limit or browser timeout
- Manually retry from dashboard

**Duplicate not detected:**
- Check if source_url matches
- Deduplication happens before research (by design)
- Can manually mark as duplicate in dashboard

**Cost overruns:**
- Check `cost_logs` table
- Adjust `MAX_COST_*` limits
- Review agent decisions for inefficiencies
- Use manual mode to control exactly what runs

**Schedule not running:**
- Check `pipeline_schedules` table - all disabled by default!
- Enable via API: `POST /api/schedule/discovery/enable`
- Check scheduler logs: `docker-compose logs scheduler`

**Manual action not working:**
- Ensure festival is in correct state for action
- Check `/api/festivals/pending` for suggested actions
- Verify auto_process is disabled for manual control

**Festival stuck in validation_failed:**
- Check validation errors: `GET /api/festivals/{id}`
- Fix missing required fields (name, description, dates, logo)
- Re-validate: `POST /api/errors/festivals/{id}/validate`
- Or force sync anyway: `POST /api/festivals/{id}/force-sync`

**Festival quarantined:**
- View in Error Dashboard at `/errors`
- Check error category and context for root cause
- Retry after fixing issue: `POST /api/errors/quarantined/{id}/retry`
- Or force retry: `POST /api/errors/quarantined/{id}/retry?force=true`

**Circuit breaker open:**
- Check circuit breaker status: `GET /api/errors/circuit-breakers`
- Wait 30 seconds for automatic recovery (half-open)
- Or manually reset: `POST /api/errors/circuit-breakers/{name}/reset`
- Check external API status (PartyMap, Exa, OpenRouter)

**Sync failing repeatedly:**
- Check error classification in festival.error_category
- TRANSIENT errors: Will retry automatically with backoff
- VALIDATION errors: Fix data quality issues before retry
- PERMANENT errors: Check API credentials and permissions
- EXTERNAL errors: PartyMap API may be down, wait and retry

**Tests failing in CI:**
- Run locally: `pytest tests/unit/ -v`
- Check coverage: `pytest tests/unit/ --cov=src --cov-report=term-missing`
- Ensure 80%+ coverage for new code
- Check for mocking issues with external APIs

## API Documentation

All endpoints are fully documented with Swagger/OpenAPI:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

Documentation includes:
- Request/response schemas with types
- Parameter descriptions and examples
- Error response documentation
- Authentication requirements

## Future Enhancements

- [ ] Add more discovery sources (Songkick, Resident Advisor)
- [ ] Machine learning for better duplicate detection
- [ ] Automatic query performance optimization
- [ ] Festival image/logo extraction
- [ ] Social media monitoring for lineup announcements
- [ ] Webhook notifications for state changes
- [ ] Festival similarity scoring
