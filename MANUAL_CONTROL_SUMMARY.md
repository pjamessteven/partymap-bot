# Manual Pipeline Control Implementation

## Overview
Added comprehensive manual control for all pipelines and services with real-time status tracking.

## Features

### 1. Pipeline Control Manager (`apps/api/src/pipeline_control.py`)

Central manager for controlling all services:

```python
class PipelineControlManager:
    - get_all_statuses()  # Get status of all pipelines
    - start_pipeline(key)  # Start a specific pipeline
    - stop_pipeline(key)   # Request graceful stop
    - update_progress()    # Update progress during run
```

### 2. Controlled Pipelines

| Pipeline | Key | Description |
|----------|-----|-------------|
| Discovery | `discovery` | Exa search for new festivals |
| Goabase Sync | `goabase_sync` | Sync from Goabase API |
| Research | `research` | Research agent execution |
| PartyMap Sync | `sync` | Sync to PartyMap |
| Deduplication | `deduplication` | Duplicate checking |

### 3. API Endpoints (`apps/api/src/api/pipelines.py`)

```
GET  /api/pipelines/status              # All pipeline statuses
GET  /api/pipelines/{key}/status        # Specific pipeline status
POST /api/pipelines/{key}/start         # Start pipeline
POST /api/pipelines/{key}/stop          # Stop pipeline
POST /api/pipelines/stop-all            # Emergency stop all
```

### 4. React Component (`apps/web/components/PipelineControlPanel.tsx`)

Features:
- **Visual Status Cards**: Each pipeline with status badge
- **Progress Bars**: Real-time progress when running
- **Start/Stop Buttons**: Manual control
- **Live Stats**: Processed items, errors, percentages
- **Auto-polling**: Updates every 2 seconds
- **Error Display**: Shows last error if any

### 5. Integration with Settings Page

Pipeline Control Panel added to Settings page above Goabase Sync panel.

## Usage

### Start a Pipeline
```javascript
await startPipeline('discovery')
```

### Stop a Pipeline
```javascript
await stopPipeline('discovery')
```

### Get Status
```javascript
const { pipelines } = await getAllPipelineStatuses()
// pipelines.discovery.status = 'running' | 'idle' | 'error'
// pipelines.discovery.progress_percentage = 45
```

## Status States

- `idle` - Ready to start
- `running` - Currently active
- `stopping` - Stop requested, finishing work
- `error` - Failed with error

## Database Migration (Manual)

Created SQL file: `apps/api/migrations/manual_migration_0003.sql`

Run this in PostgreSQL:
```bash
psql -U partymap -d partymap_bot -f apps/api/migrations/manual_migration_0003.sql
```

Or connect to your database and execute the SQL commands.

## UI Location

Settings page: http://localhost:3000/settings

Shows:
1. Pipeline Control Panel (all services)
2. Goabase Sync Panel (detailed Goabase control)
3. General Settings

## Next Steps

1. Run database migration
2. Start API server
3. Open settings page
4. Test manual pipeline controls
5. Set up scheduled runs via settings
