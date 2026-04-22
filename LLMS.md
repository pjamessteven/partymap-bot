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
│  │        │ (if dup & up-to-date) │                         │                   │   │
│  │        └───────────────────────┴─────────────────────────┤                   │   │
│  │                                │                         ▼                   │   │
│  │                                │                   [syncing] ──► [synced]     │   │
│  │                                │                                             │   │
│  │                                ▼                                             │   │
│  │                           [failed] ──► (30 days) ──► [purged]                │   │
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
1. Exa API (primary)
2. Goabase API (for psytrance)

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

### Phase 4: Sync
```
Sync to PartyMap:
├─→ If new event:
│   ├─→ POST /events (general info only)
│   └─→ POST /api/date/event/{id} for each date
├─→ If new EventDate:
│   └─→ POST /api/date/event/{existing_id}
├─→ If update general:
│   └─→ PUT /events/{id} (NO date/location fields!)
└─→ If update EventDate:
    └─→ PUT /api/date/event/{id}/{date_id}
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

1. **festivals** - Core data + state machine + PartyMap tracking
2. **festival_event_dates** - Individual dates for series
3. **discovery_queries** - Query rotation (28 pre-populated)
4. **agent_decisions** - Summarized decision logs
5. **state_transitions** - Audit trail
6. **cost_logs** - Budget tracking
7. **pipeline_schedules** - **Celery Beat schedule configuration**
8. **system_settings** - **Global settings (auto_process, etc.)**
9. **name_mappings** - Raw→clean name mappings for deduplication

## Key Design Decisions

1. **Deduplication Before Research**: Saves API costs by not researching known festivals
2. **Event/EventDate Split**: Supports festival series with multiple dates/locations
3. **All-or-Nothing Research**: Ensures data quality (no partial entries)
4. **No Main Event Date Updates**: Prevents accidental deletion of future EventDates
5. **State Machine**: Clear lifecycle with retry logic and audit trail
6. **Cost Tracking**: Budget enforcement per festival, run, and day
7. **Query Rotation**: Systematic coverage of countries, cities, genres
8. **Summarized Logs**: Agent decisions logged but condensed for readability
9. **Database-Driven Scheduling**: No hardcoded schedules, fully configurable via API
10. **Auto/Manual Mode**: Full control for testing individual pipeline stages
11. **Swagger Documentation**: All endpoints documented with OpenAPI

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
