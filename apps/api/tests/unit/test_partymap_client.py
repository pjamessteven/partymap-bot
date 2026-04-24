"""Unit tests for PartyMap API client.

Uses respx to mock HTTP requests so we can assert on actual request payloads
sent to the PartyMap API. This is critical for catching schema mismatches.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
import respx
from httpx import Response

from src.config import Settings
from src.core.schemas import (
    DuplicateCheckResult,
    EventDateData,
    FestivalData,
    MediaItem,
    RRuleData,
    TicketInfo,
)
from src.partymap.client import PartyMapAPIError, PartyMapClient


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock(spec=Settings)
    settings.partymap_api_key = "test-api-key"
    settings.partymap_base_url = "https://api.partymap.com"
    settings.effective_partymap_base_url = "https://api.partymap.com"
    settings.sync_rate_limit_per_minute = 60
    return settings


@pytest.fixture
def client(mock_settings):
    """Create PartyMap client."""
    return PartyMapClient(mock_settings)


@pytest.fixture(autouse=True)
def fast_retry(monkeypatch):
    """Patch asyncio.sleep to make tenacity retries instant in tests."""
    import asyncio
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())


def make_festival_data(**kwargs):
    """Build a FestivalData with sensible defaults for testing."""
    defaults = {
        "name": "Test Festival",
        "description": "A great festival description",
        "full_description": "A full description that is definitely long enough",
        "event_dates": [
            EventDateData(
                start=datetime(2026, 7, 15, 14, 0, 0),
                end=datetime(2026, 7, 17, 23, 0, 0),
                location_description="Berlin, Germany",
                lineup=["Artist A", "Artist B"],
                tickets=[
                    TicketInfo(
                        url="https://tickets.example.com/ga",
                        description="General Admission",
                        price_min=199.99,
                        price_max=249.99,
                        price_currency_code="USD",
                    )
                ],
            )
        ],
        "logo_url": "https://example.com/logo.jpg",
        "tags": ["music", "festival"],
        "website_url": "https://example.com",
        "youtube_url": "https://youtube.com/watch?v=123",
        "source_url": "https://example.com/source",
    }
    defaults.update(kwargs)
    return FestivalData(**defaults)


# ── _request helper ──


class TestRequestHelper:
    """Tests for the internal _request method."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_successful_request(self, client):
        """200 response returns parsed JSON."""
        route = respx.post("https://api.partymap.com/api/event/").mock(
            return_value=Response(200, json={"id": 12345})
        )

        response = await client._request("POST", "/api/event/", json={"name": "Test"})
        assert response.json()["id"] == 12345
        assert route.called

    @respx.mock
    @pytest.mark.asyncio
    async def test_400_raises_party_map_api_error_with_json_body(self, client):
        """400 error raises PartyMapAPIError with parsed JSON body."""
        respx.post("https://api.partymap.com/api/event/").mock(
            return_value=Response(400, json={"error": "Invalid name"})
        )

        with pytest.raises(PartyMapAPIError) as exc_info:
            await client._request("POST", "/api/event/", json={"name": ""})

        assert exc_info.value.status_code == 400
        assert exc_info.value.response == {"error": "Invalid name"}

    @respx.mock
    @pytest.mark.asyncio
    async def test_500_raises_party_map_api_error_with_text_body(self, client):
        """500 with HTML body still raises PartyMapAPIError gracefully."""
        respx.post("https://api.partymap.com/api/event/").mock(
            return_value=Response(500, text="<html>Server Error</html>")
        )

        with pytest.raises(PartyMapAPIError) as exc_info:
            await client._request("POST", "/api/event/", json={"name": "Test"})

        assert exc_info.value.status_code == 500
        assert "raw" in exc_info.value.response

    @respx.mock
    @pytest.mark.asyncio
    async def test_retry_on_500_then_success(self, client):
        """Tenacity retries on 500 and succeeds on second attempt."""
        call_count = 0

        def handler(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return Response(500, text="error")
            return Response(200, json={"id": 12345})

        respx.post("https://api.partymap.com/api/event/").mock(side_effect=handler)

        # _raw_request has @retry, so it should retry on HTTPStatusError
        response = await client._raw_request(
            "POST", "https://api.partymap.com/api/event/", json={"name": "Test"}
        )
        assert response.json()["id"] == 12345
        assert call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_rate_limiting_via_redis(self, client):
        """Rate limiting sleeps between requests."""
        redis_mock = AsyncMock()
        redis_mock.get.return_value = None
        redis_mock.set.return_value = None

        with patch("src.partymap.client.get_async_redis_client", return_value=redis_mock):
            respx.get("https://api.partymap.com/api/event/").mock(
                return_value=Response(200, json={"items": []})
            )

            await client._request("GET", "/api/event/")
            # Should have set Redis key
            redis_mock.set.assert_called_once()

    @respx.mock
    @pytest.mark.asyncio
    async def test_rate_limiting_redis_failure_fallback(self, client):
        """Redis failure falls back to sleep."""
        with patch(
            "src.partymap.client.get_async_redis_client",
            side_effect=ConnectionError("Redis down"),
        ), patch("asyncio.sleep") as mock_sleep:
            respx.get("https://api.partymap.com/api/event/").mock(
                return_value=Response(200, json={"items": []})
            )

            await client._request("GET", "/api/event/")
            mock_sleep.assert_called_once()


# ── Event Operations ──


class TestCreateEvent:
    """Tests for create_event."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_event_success(self, client):
        """Successful creation returns event ID."""
        route = respx.post("https://api.partymap.com/api/event/").mock(
            return_value=Response(200, json={"id": 12345})
        )

        festival = make_festival_data()
        event_id = await client.create_event(festival)

        assert event_id == 12345
        assert route.called

        # Verify payload structure
        payload = route.calls.last.request.content
        import json
        data = json.loads(payload)
        assert data["name"] == "Test Festival"
        assert data["description"] == "A great festival description"
        assert data["full_description"] == "A full description that is definitely long enough"
        assert data["logo"]["url"] == "https://example.com/logo.jpg"
        assert data["tags"] == ["music", "festival"]
        assert data["youtube_url"] == "https://youtube.com/watch?v=123"
        assert data["url"].startswith("https://example.com")
        # Event + first event_date combined
        assert "date_time" in data
        assert data["date_time"]["start"] == "2026-07-15T14:00:00"
        assert data["date_time"]["end"] == "2026-07-17T23:00:00"
        assert data["location"]["description"] == "Berlin, Germany"
        assert data["next_event_date_artists"] == [{"name": "Artist A"}, {"name": "Artist B"}]
        # Tickets as full objects (NOT ticket_url)
        assert "tickets" in data
        assert data["tickets"][0]["url"] == "https://tickets.example.com/ga"
        assert data["tickets"][0]["price_currency_code"] == "USD"
        # Must NOT contain ticket_url (PartyMap schema doesn't support it)
        assert "ticket_url" not in data

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_event_no_logo(self, client):
        """Event without logo omits logo field."""
        route = respx.post("https://api.partymap.com/api/event/").mock(
            return_value=Response(200, json={"id": 12345})
        )

        festival = make_festival_data(logo_url=None)
        await client.create_event(festival)

        payload = json.loads(route.calls.last.request.content)
        assert "logo" not in payload

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_event_with_rrule(self, client):
        """Recurring event includes rrule in payload."""
        route = respx.post("https://api.partymap.com/api/event/").mock(
            return_value=Response(200, json={"id": 12345})
        )

        festival = make_festival_data(
            is_recurring=True,
            rrule=RRuleData(recurringType=3, separationCount=1),
        )
        await client.create_event(festival)

        payload = json.loads(route.calls.last.request.content)
        assert payload["rrule"]["recurringType"] == 3
        assert payload["rrule"]["separationCount"] == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_event_500_returns_none(self, client):
        """500/503 known bug: returns None so caller can search."""
        respx.post("https://api.partymap.com/api/event/").mock(
            return_value=Response(500, text="Internal Server Error")
        )

        festival = make_festival_data()
        result = await client.create_event(festival)

        assert result is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_event_503_returns_none(self, client):
        """503 also returns None for known bug."""
        respx.post("https://api.partymap.com/api/event/").mock(
            return_value=Response(503, text="Service Unavailable")
        )

        festival = make_festival_data()
        result = await client.create_event(festival)

        assert result is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_event_400_raises(self, client):
        """Non-500/503 errors are re-raised."""
        respx.post("https://api.partymap.com/api/event/").mock(
            return_value=Response(400, json={"error": "Bad Request"})
        )

        with pytest.raises(PartyMapAPIError):
            await client.create_event(make_festival_data())

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_event_no_event_id_in_response(self, client):
        """Response without 'id' field raises PartyMapAPIError."""
        respx.post("https://api.partymap.com/api/event/").mock(
            return_value=Response(200, json={"message": "OK"})
        )

        with pytest.raises(PartyMapAPIError, match="No event ID"):
            await client.create_event(make_festival_data())


class TestUpdateEvent:
    """Tests for update_event — CRITICAL: must never include date_time/location/rrule."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_event_payload_excludes_date_fields(self, client):
        """Payload NEVER contains date_time, location, or rrule."""
        route = respx.put("https://api.partymap.com/api/event/12345").mock(
            return_value=Response(200)
        )

        festival = make_festival_data()
        await client.update_event(12345, festival)

        payload = json.loads(route.calls.last.request.content)
        # Critical guardrails
        assert "date_time" not in payload, "date_time would DELETE EventDates!"
        assert "location" not in payload, "location would DELETE EventDates!"
        assert "rrule" not in payload, "rrule would affect recurrence!"
        # General info should be present
        assert payload["name"] == "Test Festival"
        assert payload["description"] == "A great festival description"
        assert payload["message"] == "Updated by festival bot"

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_event_only_includes_present_fields(self, client):
        """Omitted fields are not included in payload."""
        route = respx.put("https://api.partymap.com/api/event/12345").mock(
            return_value=Response(200)
        )

        festival = make_festival_data(
            youtube_url=None,
            website_url=None,
            tags=[],
            logo_url=None,
            media_items=[],
        )
        await client.update_event(12345, festival)

        payload = json.loads(route.calls.last.request.content)
        assert "youtube_url" not in payload
        assert "url" not in payload
        assert "add_tags" not in payload
        assert "logo" not in payload
        assert "media_items" not in payload

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_event_with_media_items(self, client):
        """Media items are serialized as dicts with url and caption."""
        route = respx.put("https://api.partymap.com/api/event/12345").mock(
            return_value=Response(200)
        )

        festival = make_festival_data(
            media_items=[
                MediaItem(url="https://example.com/photo1.jpg", caption="Photo 1"),
                MediaItem(url="https://example.com/photo2.jpg", caption=None),
            ]
        )
        await client.update_event(12345, festival)

        payload = json.loads(route.calls.last.request.content)
        assert payload["media_items"][0]["url"] == "https://example.com/photo1.jpg"
        assert payload["media_items"][0]["caption"] == "Photo 1"
        assert "Photo from" in payload["media_items"][1]["caption"]


# ── EventDate Operations ──


class TestEventDatePayload:
    """Tests for _event_date_to_payload conversion."""

    def test_basic_event_date(self, client):
        """Minimal event date produces correct payload."""
        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            end=datetime(2026, 7, 17, 23, 0, 0),
            location_description="Berlin, Germany",
        )
        payload = client._event_date_to_payload(ed)

        assert payload["date_time"]["start"] == "2026-07-15T14:00:00"
        assert payload["date_time"]["end"] == "2026-07-17T23:00:00"
        assert payload["location"]["description"] == "Berlin, Germany"
        # Must NOT contain ticket_url (PartyMap schema doesn't support it)
        assert "ticket_url" not in payload

    def test_event_date_with_tickets(self, client):
        """Full ticket objects are included, not ticket_url."""
        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin, Germany",
            tickets=[
                TicketInfo(
                    url="https://tickets.example.com/ga",
                    description="GA",
                    price_min=100,
                    price_max=200,
                    price_currency_code="EUR",
                )
            ],
        )
        payload = client._event_date_to_payload(ed)

        assert "tickets" in payload
        assert payload["tickets"][0]["url"] == "https://tickets.example.com/ga"
        assert payload["tickets"][0]["price_min"] == 100.0
        assert payload["tickets"][0]["price_currency_code"] == "EUR"
        assert "ticket_url" not in payload

    def test_event_date_with_lineup(self, client):
        """Lineup is converted to artists array."""
        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin, Germany",
            lineup=["Artist A", "Artist B"],
        )
        payload = client._event_date_to_payload(ed)

        assert payload["artists"] == [{"name": "Artist A"}, {"name": "Artist B"}]

    def test_event_date_source_url(self, client):
        """source_url becomes url in payload."""
        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin, Germany",
            source_url="https://example.com/event",
        )
        payload = client._event_date_to_payload(ed)

        assert payload["url"] == "https://example.com/event"

    def test_event_date_size(self, client):
        """expected_size becomes size in payload."""
        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin, Germany",
            expected_size=5000,
        )
        payload = client._event_date_to_payload(ed)

        assert payload["size"] == 5000


class TestAddEventDate:
    """Tests for add_event_date."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_add_event_date_success(self, client):
        """Successful add returns date ID."""
        route = respx.post("https://api.partymap.com/api/date/event/12345").mock(
            return_value=Response(200, json={"id": 67890})
        )

        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            end=datetime(2026, 7, 17, 23, 0, 0),
            location_description="Berlin, Germany",
        )
        date_id = await client.add_event_date(12345, ed)

        assert date_id == 67890
        assert route.called

    @respx.mock
    @pytest.mark.asyncio
    async def test_add_event_date_no_id_raises(self, client):
        """Response without 'id' raises PartyMapAPIError."""
        respx.post("https://api.partymap.com/api/date/event/12345").mock(
            return_value=Response(200, json={"message": "OK"})
        )

        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin, Germany",
        )
        with pytest.raises(PartyMapAPIError, match="No event date ID"):
            await client.add_event_date(12345, ed)


class TestUpdateEventDate:
    """Tests for update_event_date."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_event_date_success(self, client):
        """Successful update."""
        route = respx.put("https://api.partymap.com/api/date/67890").mock(
            return_value=Response(200)
        )

        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin, Germany",
        )
        await client.update_event_date(67890, ed)

        assert route.called


# ── Search & Discovery ──


class TestSearchEvents:
    """Tests for search_events."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_events_items_wrapper(self, client):
        """Handles {items: [...]} response format."""
        respx.get("https://api.partymap.com/api/event/").mock(
            return_value=Response(
                200,
                json={
                    "items": [
                        {"id": 1, "name": "Festival A"},
                        {"id": 2, "name": "Festival B"},
                    ]
                },
            )
        )

        results = await client.search_events("test")
        assert len(results) == 2
        assert results[0]["name"] == "Festival A"

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_events_direct_array(self, client):
        """Handles direct array response format."""
        respx.get("https://api.partymap.com/api/event/").mock(
            return_value=Response(
                200,
                json=[{"id": 1, "name": "Festival A"}],
            )
        )

        results = await client.search_events("test")
        assert len(results) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_events_error_returns_empty(self, client):
        """API errors return empty list, don't raise."""
        respx.get("https://api.partymap.com/api/event/").mock(
            return_value=Response(500, text="Error")
        )

        results = await client.search_events("test")
        assert results == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_events_respects_limit(self, client):
        """Limit parameter is passed and results are truncated."""
        route = respx.get("https://api.partymap.com/api/event/").mock(
            return_value=Response(
                200,
                json={"items": [{"id": i} for i in range(10)]},
            )
        )

        results = await client.search_events("test", limit=5)
        assert len(results) == 5
        request = route.calls[0].request
        assert request.url.params["per_page"] == "5"


class TestGetEvent:
    """Tests for get_event."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_event_success(self, client):
        """Successful fetch returns event dict."""
        respx.get("https://api.partymap.com/api/event/12345").mock(
            return_value=Response(200, json={"id": 12345, "name": "Test"})
        )

        result = await client.get_event(12345)
        assert result["name"] == "Test"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_event_404_returns_none(self, client):
        """404 returns None instead of raising."""
        respx.get("https://api.partymap.com/api/event/12345").mock(
            return_value=Response(404)
        )

        result = await client.get_event(12345)
        assert result is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_event_500_raises(self, client):
        """Non-404 errors are re-raised."""
        respx.get("https://api.partymap.com/api/event/12345").mock(
            return_value=Response(500)
        )

        with pytest.raises(PartyMapAPIError):
            await client.get_event(12345)


class TestGetEventByUrl:
    """Tests for get_event_by_url."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_by_event_url(self, client):
        """Matches event-level URL."""
        respx.get("https://api.partymap.com/api/event/").mock(
            return_value=Response(
                200,
                json={
                    "items": [
                        {"id": 1, "name": "Test", "url": "https://example.com/event"}
                    ]
                },
            )
        )

        result = await client.get_event_by_url("https://example.com/event")
        assert result["id"] == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_by_event_date_url(self, client):
        """Matches event_dates-level URL."""
        respx.get("https://api.partymap.com/api/event/").mock(
            return_value=Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Test",
                            "event_dates": [
                                {"url": "https://example.com/date"}
                            ],
                        }
                    ]
                },
            )
        )

        result = await client.get_event_by_url("https://example.com/date")
        assert result["id"] == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_match_returns_none(self, client):
        """No URL match returns None."""
        respx.get("https://api.partymap.com/api/event/").mock(
            return_value=Response(200, json={"items": [{"id": 1, "name": "Test"}]})
        )

        result = await client.get_event_by_url("https://example.com/other")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_url_returns_none(self, client):
        """Empty URL returns None without making request."""
        result = await client.get_event_by_url("")
        assert result is None


# ── Duplicate Checking ──


class TestCalculateSimilarity:
    """Tests for _calculate_similarity."""

    def test_exact_match(self, client):
        assert client._calculate_similarity("Test Festival", "Test Festival") == 1.0

    def test_substring_match(self, client):
        assert client._calculate_similarity("Test Festival", "Test Festival 2026") == 0.9
        assert client._calculate_similarity("Test Festival 2026", "Test Festival") == 0.9

    def test_word_overlap(self, client):
        score = client._calculate_similarity("Boom Festival", "Boom Festival Portugal")
        assert score > 0.5

    def test_no_match(self, client):
        score = client._calculate_similarity("Test Festival", "Completely Different")
        assert score < 0.3

    def test_empty_strings(self, client):
        assert client._calculate_similarity("", "Test") == 0.0


class TestLocationSimilarity:
    """Tests for _location_similarity."""

    def test_exact_match(self, client):
        assert client._location_similarity("Berlin, Germany", "Berlin, Germany") == 1.0

    def test_substring_match(self, client):
        assert client._location_similarity("Berlin", "Berlin, Germany") == 1.0

    def test_partial_overlap(self, client):
        score = client._location_similarity("Berlin, Germany", "Munich, Germany")
        assert 0 < score < 1.0

    def test_no_match(self, client):
        assert client._location_similarity("Paris, France", "Berlin, Germany") == 0.0

    def test_empty_location(self, client):
        assert client._location_similarity("", "Berlin") == 0.0


class TestIsNewEventDate:
    """Tests for _is_new_event_date."""

    @pytest.mark.asyncio
    async def test_same_date_same_location_is_existing(self, client):
        """Same date + similar location = existing."""
        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin, Germany",
        )
        existing = [{"start": "2026-07-15T14:00:00", "location": {"description": "Berlin, Germany"}}]
        result = await client._is_new_event_date(12345, ed, existing)
        assert result is False

    @pytest.mark.asyncio
    async def test_same_date_different_location_is_new(self, client):
        """Same date + different location = new."""
        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin, Germany",
        )
        existing = [{"start": "2026-07-15T14:00:00", "location": {"description": "Paris, France"}}]
        result = await client._is_new_event_date(12345, ed, existing)
        assert result is True

    @pytest.mark.asyncio
    async def test_within_tolerance_same_location_is_existing(self, client):
        """Within 2-day tolerance + same location = existing."""
        ed = EventDateData(
            start=datetime(2026, 7, 16, 14, 0, 0),  # 1 day difference
            location_description="Berlin, Germany",
        )
        existing = [{"start": "2026-07-15T14:00:00", "location": {"description": "Berlin, Germany"}}]
        result = await client._is_new_event_date(12345, ed, existing)
        assert result is False

    @pytest.mark.asyncio
    async def test_beyond_tolerance_is_new(self, client):
        """Beyond 2-day tolerance = new even with same location."""
        ed = EventDateData(
            start=datetime(2026, 7, 20, 14, 0, 0),  # 5 days difference
            location_description="Berlin, Germany",
        )
        existing = [{"start": "2026-07-15T14:00:00", "location": {"description": "Berlin, Germany"}}]
        result = await client._is_new_event_date(12345, ed, existing)
        assert result is True


class TestCheckDateConfirmed:
    """Tests for _check_date_confirmed."""

    def test_confirmed_with_lineup_and_tickets(self, client):
        """Has lineup + tickets = confirmed."""
        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin, Germany",
        )
        existing = [{
            "start": "2026-07-15T14:00:00",
            "artists": [{"name": "Artist A"}],
            "tickets": [{"url": "https://tickets.example.com"}],
        }]
        assert client._check_date_confirmed(existing, ed) is True

    def test_not_confirmed_no_tickets(self, client):
        """Has lineup but no tickets = not confirmed."""
        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin, Germany",
        )
        existing = [{
            "start": "2026-07-15T14:00:00",
            "artists": [{"name": "Artist A"}],
        }]
        assert client._check_date_confirmed(existing, ed) is False

    def test_not_confirmed_no_lineup(self, client):
        """Has tickets but no lineup = not confirmed."""
        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin, Germany",
        )
        existing = [{
            "start": "2026-07-15T14:00:00",
            "tickets": [{"url": "https://tickets.example.com"}],
        }]
        assert client._check_date_confirmed(existing, ed) is False

    def test_date_not_found(self, client):
        """Date not in existing list = not confirmed."""
        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin, Germany",
        )
        existing = [{"start": "2026-08-01T14:00:00", "artists": [], "tickets": []}]
        assert client._check_date_confirmed(existing, ed) is False


class TestCheckDuplicate:
    """Tests for check_duplicate."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_exact_source_url_match(self, client):
        """Exact source URL match = duplicate with confidence 1.0."""
        respx.get("https://api.partymap.com/api/event/").mock(
            return_value=Response(
                200,
                json={
                    "items": [
                        {
                            "id": 12345,
                            "name": "Test Festival",
                            "event_dates": [{"url": "https://example.com/event"}],
                        }
                    ]
                },
            )
        )

        result = await client.check_duplicate(
            name="Test Festival",
            source_url="https://example.com/event",
        )

        assert result.is_duplicate is True
        assert result.confidence == 1.0
        assert result.existing_event_id == 12345
        assert "Exact source URL match" in result.reason

    @respx.mock
    @pytest.mark.asyncio
    async def test_name_substring_match(self, client):
        """Name substring match with location = duplicate."""
        respx.get("https://api.partymap.com/api/event/").mock(
            return_value=Response(
                200,
                json={
                    "items": [
                        {
                            "id": 12345,
                            "name": "Test Festival 2026",
                            "location": {"description": "Berlin, Germany"},
                            "event_dates": [],
                        }
                    ]
                },
            )
        )

        result = await client.check_duplicate(
            name="Test Festival",
            location="Berlin, Germany",
        )

        assert result.is_duplicate is True
        assert result.existing_event_id == 12345

    @respx.mock
    @pytest.mark.asyncio
    async def test_clean_name_fallback(self, client):
        """If clean_name yields no results, falls back to raw name."""
        route = respx.get("https://api.partymap.com/api/event/")
        route.side_effect = [
            Response(200, json={"items": []}),  # clean_name search: no results
            Response(
                200,
                json={
                    "items": [
                        {
                            "id": 12345,
                            "name": "Test Festival",
                            "location": {"description": "Berlin"},
                            "event_dates": [],
                        }
                    ]
                },
            ),
        ]

        result = await client.check_duplicate(
            name="Test Festival 2026",
            clean_name="Test Festival",
            location="Berlin",
        )

        assert result.is_duplicate is True
        assert result.existing_event_id == 12345

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_match(self, client):
        """No similar events found = not duplicate."""
        respx.get("https://api.partymap.com/api/event/").mock(
            return_value=Response(200, json={"items": []})
        )

        result = await client.check_duplicate(name="Completely Unknown Festival")

        assert result.is_duplicate is False
        assert result.confidence == 1.0

    @respx.mock
    @pytest.mark.asyncio
    async def test_new_event_date_for_existing(self, client):
        """Existing event but new date = is_duplicate + is_new_event_date."""
        respx.get("https://api.partymap.com/api/event/").mock(
            return_value=Response(
                200,
                json={
                    "items": [
                        {
                            "id": 12345,
                            "name": "Test Festival",
                            "location": {"description": "Berlin, Germany"},
                            "event_dates": [
                                {"start": "2025-07-15T14:00:00", "location": {"description": "Berlin, Germany"}}
                            ],
                        }
                    ]
                },
            )
        )

        result = await client.check_duplicate(
            name="Test Festival",
            location="Berlin, Germany",
            event_date=EventDateData(
                start=datetime(2026, 7, 15, 14, 0, 0),
                location_description="Berlin, Germany",
            ),
        )

        assert result.is_duplicate is True
        assert result.is_new_event_date is True
        assert result.existing_event_id == 12345

    @respx.mock
    @pytest.mark.asyncio
    async def test_existing_date_needs_update(self, client):
        """Existing date without lineup/tickets = needs update."""
        respx.get("https://api.partymap.com/api/event/").mock(
            return_value=Response(
                200,
                json={
                    "items": [
                        {
                            "id": 12345,
                            "name": "Test Festival",
                            "location": {"description": "Berlin, Germany"},
                            "event_dates": [
                                {
                                    "start": "2026-07-15T14:00:00",
                                    "location": {"description": "Berlin, Germany"},
                                    "artists": [],
                                }
                            ],
                        }
                    ]
                },
            )
        )

        result = await client.check_duplicate(
            name="Test Festival",
            location="Berlin, Germany",
            event_date=EventDateData(
                start=datetime(2026, 7, 15, 14, 0, 0),
                location_description="Berlin, Germany",
            ),
        )

        assert result.is_duplicate is True
        assert result.is_new_event_date is False
        assert result.date_confirmed is False
        assert "needs update" in result.reason

    @respx.mock
    @pytest.mark.asyncio
    async def test_exception_returns_not_duplicate(self, client):
        """Exception during check returns not_duplicate with confidence 0."""
        respx.get("https://api.partymap.com/api/event/").mock(
            side_effect=Exception("Network error")
        )

        result = await client.check_duplicate(name="Test")

        assert result.is_duplicate is False
        assert result.confidence == 0.0
        assert "Check failed" in result.reason


# ── Sync Strategy ──


class TestSyncFestival:
    """Tests for sync_festival orchestration."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_sync_new_event(self, client):
        """New festival: create event + add event dates."""
        respx.post("https://api.partymap.com/api/event/").mock(
            return_value=Response(200, json={"id": 12345})
        )
        respx.post("https://api.partymap.com/api/date/event/12345").mock(
            return_value=Response(200, json={"id": 67890})
        )

        result = await client.sync_festival(
            make_festival_data(),
            DuplicateCheckResult(is_duplicate=False),
        )

        assert result["action"] == "created"
        assert result["event_id"] == 12345
        assert result["event_date_ids"] == ["67890"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_sync_new_event_date_for_existing(self, client):
        """Duplicate with new date: add event dates only."""
        respx.post("https://api.partymap.com/api/date/event/12345").mock(
            return_value=Response(200, json={"id": 67890})
        )

        result = await client.sync_festival(
            make_festival_data(),
            DuplicateCheckResult(
                is_duplicate=True,
                existing_event_id=12345,
                is_new_event_date=True,
            ),
        )

        assert result["action"] == "added_event_date"
        assert result["event_id"] == 12345
        # Should NOT have called create_event
        assert result["event_date_ids"] == ["67890"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_sync_update_existing(self, client):
        """Duplicate needing update: update general info + add dates."""
        respx.put("https://api.partymap.com/api/event/12345").mock(
            return_value=Response(200)
        )
        respx.post("https://api.partymap.com/api/date/event/12345").mock(
            return_value=Response(200, json={"id": 67890})
        )

        result = await client.sync_festival(
            make_festival_data(),
            DuplicateCheckResult(
                is_duplicate=True,
                existing_event_id=12345,
                is_new_event_date=False,
                date_confirmed=False,
            ),
        )

        assert result["action"] == "updated"
        assert result["event_id"] == 12345

    @respx.mock
    @pytest.mark.asyncio
    async def test_sync_up_to_date_skips(self, client):
        """Up to date: skip without API calls."""
        result = await client.sync_festival(
            make_festival_data(),
            DuplicateCheckResult(
                is_duplicate=True,
                existing_event_id=12345,
                is_new_event_date=False,
                date_confirmed=True,
            ),
        )

        assert result["action"] == "skipped"
        assert result["event_id"] == 12345


# ── Refresh Pipeline Methods ──


class TestGetUnconfirmedEventDates:
    """Tests for get_unconfirmed_event_dates."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_success(self, client):
        """Returns list of unconfirmed event dates."""
        respx.get("https://api.partymap.com/api/event_date/").mock(
            return_value=Response(
                200,
                json={
                    "items": [
                        {"id": 1, "start": "2026-07-15T14:00:00", "date_unconfirmed": True}
                    ]
                },
            )
        )

        results = await client.get_unconfirmed_event_dates()
        assert len(results) == 1
        assert results[0]["id"] == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        """API error returns empty list."""
        respx.get("https://api.partymap.com/api/event_date/").mock(
            return_value=Response(500)
        )

        results = await client.get_unconfirmed_event_dates()
        assert results == []


class TestMarkEventDateCancelled:
    """Tests for mark_event_date_cancelled."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_success(self, client):
        """Successful cancellation."""
        route = respx.put("https://api.partymap.com/api/date/67890").mock(
            return_value=Response(200)
        )

        result = await client.mark_event_date_cancelled(67890, "Date not confirmed")

        assert result is True
        payload = json.loads(route.calls.last.request.content)
        assert payload["cancelled"] is True
        assert "Date not confirmed" in payload["cancellation_reason"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_failure_returns_false(self, client):
        """API error returns False."""
        respx.put("https://api.partymap.com/api/date/67890").mock(
            return_value=Response(500)
        )

        result = await client.mark_event_date_cancelled(67890)
        assert result is False


class TestAddEventDateToExisting:
    """Tests for add_event_date_to_existing."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_success(self, client):
        """Successful add returns event_date_id."""
        respx.post("https://api.partymap.com/api/date/event/12345").mock(
            return_value=Response(200, json={"id": 67890})
        )

        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            end=datetime(2026, 7, 17, 23, 0, 0),
            location_description="Berlin, Germany",
            lineup=["Artist A"],
        )
        result = await client.add_event_date_to_existing(12345, ed)

        assert result == 67890

    @respx.mock
    @pytest.mark.asyncio
    async def test_failure_returns_none(self, client):
        """API error returns None."""
        respx.post("https://api.partymap.com/api/date/event/12345").mock(
            return_value=Response(500)
        )

        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin, Germany",
        )
        result = await client.add_event_date_to_existing(12345, ed)

        assert result is None


class TestUpdateEventDateFields:
    """Tests for update_event_date_fields."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_success(self, client):
        """Successful update."""
        route = respx.put("https://api.partymap.com/api/date/67890").mock(
            return_value=Response(200)
        )

        result = await client.update_event_date_fields(
            67890, {"lineup": ["Artist A"]}, message="Updated lineup"
        )

        assert result is True
        payload = json.loads(route.calls.last.request.content)
        assert payload["message"] == "Updated lineup"
        assert payload["lineup"] == ["Artist A"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_failure_returns_false(self, client):
        """API error returns False."""
        respx.put("https://api.partymap.com/api/date/67890").mock(
            return_value=Response(500)
        )

        result = await client.update_event_date_fields(67890, {})
        assert result is False


# ── Context Manager ──


class TestContextManager:
    """Tests for async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self, mock_settings):
        """Client is closed when exiting context."""
        async with PartyMapClient(mock_settings) as client:
            assert client.client is not None

        # After exit, client should be closed
        # (httpx.AsyncClient.aclose is idempotent, so we just verify no error)
