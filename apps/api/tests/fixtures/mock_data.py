"""Simplified mock data for API tests."""

from datetime import datetime, timedelta
from uuid import uuid4

VALID_FESTIVAL_DATA = {
    "name": "Summer Music Festival 2026",
    "description": "An unforgettable weekend of live music and entertainment",
    "full_description": "Join us for three days of incredible performances from world-class artists across multiple stages.",
    "event_dates": [
        {
            "start": datetime(2026, 7, 15, 14, 0, 0).isoformat(),
            "end": datetime(2026, 7, 17, 23, 0, 0).isoformat(),
            "location_description": "Central Park, New York, NY",
            "lineup": ["Artist A", "Artist B", "Artist C"],
            "tickets": [
                {
                    "url": "https://tickets.example.com/ga",
                    "description": "General Admission",
                    "price_min": 199.99,
                    "price_max": 249.99,
                    "price_currency_code": "USD",
                }
            ],
        }
    ],
    "tags": ["music", "festival", "outdoor"],
    "logo_url": "https://example.com/logo.jpg",
    "website_url": "https://example.com",
    "youtube_url": "https://youtube.com/watch?v=123",
}

INVALID_FESTIVAL_DATA = {
    "name": "",  # Fails min length (2)
    "description": "Short",  # Fails min length (10)
    "full_description": "Also short",  # Fails min length (20)
    "event_dates": [],  # Missing required
}

PARTIALLY_VALID_FESTIVAL_DATA = {
    "name": "Test Festival",
    "description": "A great festival description that is long enough",
    "full_description": "A full description that meets the minimum length requirement for PartyMap sync",
    "event_dates": [
        {
            "start": datetime(2026, 7, 15, 14, 0, 0).isoformat(),
            "end": datetime(2026, 7, 17, 23, 0, 0).isoformat(),
            "location_description": "NYC",
        }
    ],
    # Missing logo_url - will be invalid for sync
}

PARTYMAP_EVENT_RESPONSE = {
    "id": 12345,
    "name": "Summer Music Festival 2026",
    "description": "An unforgettable weekend",
    "location": {"description": "Central Park, New York, NY"},
    "event_dates": [
        {
            "id": 67890,
            "start": "2026-07-15T14:00:00",
            "end": "2026-07-17T23:00:00",
            "date_unconfirmed": False,
        }
    ],
}

PARTYMAP_SEARCH_RESPONSE = {
    "events": [
        {"id": 12345, "name": "Summer Music Festival 2026", "location": {"description": "New York, NY"}},
        {"id": 12346, "name": "Winter Festival 2026", "location": {"description": "Berlin, Germany"}},
    ]
}

PARTYMAP_EMPTY_SEARCH = {"events": []}

REFRESH_APPROVAL_DATA = {
    "event_id": 12345,
    "event_date_id": 67890,
    "event_name": "Test Festival",
    "status": "pending",
    "change_summary": ["Updated dates", "Added lineup"],
    "research_confidence": 0.95,
    "current_data": {
        "event": {"name": "Test Festival", "description": "Old desc"},
        "event_date": {"start": "2026-07-15T14:00:00", "end": "2026-07-17T23:00:00"},
    },
    "proposed_changes": {
        "event": {"name": "Test Festival Updated", "description": "New desc"},
        "event_date": {"start": "2026-07-16T14:00:00", "end": "2026-07-18T23:00:00"},
    },
    "research_sources": ["https://example.com"],
}

STREAMING_EVENTS = {
    "metadata": {
        "event": "metadata",
        "data": {"thread_id": "research_test_123", "status": "running"},
    },
    "messages": {
        "event": "messages",
        "data": [
            {"type": "ai", "data": {"content": "Researching festival...", "id": "run-abc-123"}},
            {"run_id": "run-abc-123", "tags": []},
        ],
    },
    "custom_reasoning": {
        "event": "custom",
        "data": {"type": "reasoning", "data": {"step": "searching"}, "timestamp": "2026-04-22T12:00:00.000000"},
    },
    "custom_tool_progress": {
        "event": "custom",
        "data": {"type": "tool_progress", "data": {"tool": "web_search", "progress": 0.5}, "timestamp": "2026-04-22T12:00:01.000000"},
    },
    "tools": {
        "event": "tools",
        "data": {"toolCallId": "call-123", "name": "web_search", "state": "starting", "input": "festival 2026"},
    },
    "end": {
        "event": "end",
        "data": {"status": "success"},
    },
    "error": {
        "event": "error",
        "data": {"error": "Something went wrong"},
    },
    "ping": {
        "event": "ping",
        "data": {"timestamp": "2026-04-22T12:00:30.000000"},
    },
}
