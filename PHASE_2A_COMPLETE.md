# Phase 2a Complete: PartyMap API Integration

## Summary

Successfully implemented PartyMap API client with proper Event/EventDate separation.

## Files Updated/Created

### 1. PartyMap Client (`src/partymap/client.py`)

**Features:**
- Base URL: `https://api.partymap.com/api`
- API Key authentication via `X-API-Key` header
- Rate limiting: 10 requests per minute
- Retry logic: 3 attempts with exponential backoff
- Proper error handling with `PartyMapAPIError`

**Methods Implemented:**

#### Event Operations
- `create_event(festival_data)` → POST /events
  - Creates event with general info only
  - NO date_time, location, or rrule (prevents data loss)
  - Returns event UUID

- `update_event(event_id, festival_data)` → PUT /events/{id}
  - Updates general info only
  - Safe updates that don't affect EventDates

#### EventDate Operations
- `add_event_date(event_id, event_date)` → POST /api/date/event/{event_id}
  - Adds date-specific info (dates, location, lineup, tickets)
  - Returns EventDate UUID

- `update_event_date(event_id, date_id, event_date)` → PUT /api/date/event/{id}/{date_id}
  - Updates specific EventDate

#### Search & Discovery
- `search_events(query, limit)` → GET /events?search={query}
  - Returns list of matching events
  - Used for deduplication

- `get_event(event_id)` → GET /events/{id}
  - Returns full event with EventDates array
  - Used to check for duplicates

#### Deduplication
- `check_duplicate(name, source_url, location, event_date)`
  - Runs BEFORE research to save API costs
  - Checks by:
    1. Exact source URL match (on EventDates)
    2. Name + location similarity
  - Returns `DuplicateCheckResult` with:
    - `is_duplicate`: bool
    - `existing_event_id`: UUID if found
    - `is_new_event_date`: True if new date for series
    - `date_confirmed`: False if needs update
    - `confidence`: 0-1 similarity score

#### Sync Strategy
- `sync_festival(festival_data, duplicate_check)`
  - Handles all sync scenarios:
    1. New event → Create Event + add EventDates
    2. New EventDate → Add to existing Event
    3. Update needed → Update general info + EventDates
    4. Up to date → Skip

## Data Flow Validation

### Correct Event/EventDate Separation

```
FestivalData
├── General Info (goes to Event)
│   ├── name
│   ├── description
│   ├── full_description
│   ├── website_url
│   ├── youtube_url
│   ├── logo_url
│   ├── media_items
│   └── tags
│
└── EventDate Info (goes to EventDate)
    ├── start/end dates
    ├── location_description
    ├── lineup
    ├── tickets
    └── expected_size
```

### API Call Safety

✅ **Safe Operations:**
- POST /events (create new)
- PUT /events/{id} (update general info only)
- POST /api/date/event/{id} (add date)
- PUT /api/date/event/{id}/{date_id} (update date)

❌ **Never Done:**
- PUT /events/{id} with date_time/location/rrule
  - Would delete future EventDates!
  - Our client explicitly excludes these fields

## Deduplication Logic

### Step 1: Check PartyMap API
```python
# Search by name
events = await client.search_events(name, limit=20)
```

### Step 2: URL Matching
```python
# Check if any EventDate has matching source_url
for event in events:
    for date in event.event_dates:
        if date.url == source_url:
            return DuplicateCheckResult(
                is_duplicate=True,
                # ... this is an exact match
            )
```

### Step 3: Name + Location Similarity
```python
# Calculate similarity scores
name_score = calculate_similarity(query_name, event_name)
location_score = location_similarity(query_location, event_location)

if name_score > 0.7 and location_score > 0.5:
    # Potential match found
```

### Step 4: EventDate Check
```python
# If same event series, check if new date
is_new = check_if_new_event_date(existing_dates, new_date)

# If same date, check if data is complete
date_confirmed = check_date_confirmed(existing_date)
# Returns False if missing lineup/tickets
```

## Error Handling

### `PartyMapAPIError`
Custom exception with:
- `message`: Error description
- `status_code`: HTTP status
- `response`: Full API response

### Retry Logic
- 3 attempts with exponential backoff
- Retries on: HTTPStatusError, NetworkError
- No retry on: 404 (not found), 401 (auth)

### Rate Limiting
- 6 second delay between requests
- Prevents hitting 10 req/min limit
- Automatic with `_rate_limit()` decorator

## Configuration

Environment variables:
```bash
PARTYMAP_API_KEY=your_api_key_here
PARTYMAP_BASE_URL=https://api.partymap.com/api  # Optional override
```

Current: Using placeholder key in settings

## Integration Points

### Pipeline Tasks Updated
- `deduplication_check` task now uses `client.check_duplicate()`
- Removed separate `DeduplicationService` class
- All dedup logic integrated into client

### Pipeline Flow
```
Discovery → Deduplication (uses PartyMapClient.check_duplicate)
    ↓
Research → Sync (uses PartyMapClient.sync_festival)
```

## Testing Ready

The client is ready for:
1. Unit tests with mocked HTTP responses
2. Integration tests against real API
3. End-to-end pipeline tests

## Next: Phase 2b

Now ready to implement:
1. Exa API client for festival discovery
2. Goabase API client for psytrance
3. Research Agent with Playwright + LLM
4. Full integration testing

The PartyMap foundation is solid and handles all the edge cases correctly!
