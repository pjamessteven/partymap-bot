"""Unit tests for PartyMap API client."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import respx
from httpx import Response

from src.config import Settings
from src.core.schemas import EventDateData, ResearchedFestival
from src.partymap.client import PartyMapClient


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock(spec=Settings)
    settings.partymap_api_key = "test-api-key"
    settings.partymap_base_url = "https://api.partymap.com"
    settings.sync_rate_limit_per_minute = 60
    return settings


@pytest.fixture
def client(mock_settings):
    """Create PartyMap client."""
    return PartyMapClient(mock_settings)


class TestPartyMapClient:
    """Test PartyMap API client."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_events_success(self, client):
        """Test successful event search."""
        route = respx.get("https://api.partymap.com/events").mock(
            return_value=Response(
                200,
                json={
                    "events": [
                        {"id": str(uuid4()), "name": "Test Festival"},
                        {"id": str(uuid4()), "name": "Another Festival"},
                    ]
                },
            )
        )

        result = await client.search_events("test festival")

        assert len(result) == 2
        assert route.called

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_events_error(self, client):
        """Test event search with error."""
        route = respx.get("https://api.partymap.com/events").mock(
            return_value=Response(500, text="Internal Server Error")
        )

        result = await client.search_events("test")

        assert result == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_existing_event_by_name(self, client):
        """Test finding existing event by name."""
        event_id = uuid4()
        route = respx.get("https://api.partymap.com/events").mock(
            return_value=Response(
                200,
                json={
                    "events": [
                        {
                            "id": str(event_id),
                            "name": "Test Festival 2026",
                            "location": {"description": "Berlin, Germany"},
                        }
                    ]
                },
            )
        )

        result = await client.find_existing_event(
            name="Test Festival",
            location="Berlin",
        )

        assert result is not None
        assert result["name"] == "Test Festival 2026"

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_existing_event_no_match(self, client):
        """Test when no existing event found."""
        route = respx.get("https://api.partymap.com/events").mock(
            return_value=Response(200, json={"events": []})
        )

        result = await client.find_existing_event(name="Nonexistent Festival")

        assert result is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_should_update_event_newer_timestamp(self, client):
        """Test update check when remote is newer."""
        event_id = uuid4()

        # Mock get_event response
        route = respx.get(f"https://api.partymap.com/events/{event_id}").mock(
            return_value=Response(
                200,
                json={
                    "id": str(event_id),
                    "settings": {"goabase_modified": "2024-01-01T00:00:00"},
                },
            )
        )

        result = await client.should_update_event(
            event_id,
            "goabase",
            datetime(2024, 1, 15, 0, 0, 0),
        )

        assert result is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_should_update_event_up_to_date(self, client):
        """Test update check when already up to date."""
        event_id = uuid4()

        route = respx.get(f"https://api.partymap.com/events/{event_id}").mock(
            return_value=Response(
                200,
                json={
                    "id": str(event_id),
                    "settings": {"goabase_modified": "2024-01-15T00:00:00"},
                },
            )
        )

        result = await client.should_update_event(
            event_id,
            "goabase",
            datetime(2024, 1, 1, 0, 0, 0),
        )

        assert result is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_event_success(self, client):
        """Test successful event creation."""
        new_event_id = uuid4()
        route = respx.post("https://api.partymap.com/events").mock(
            return_value=Response(201, json={"id": str(new_event_id)})
        )

        festival = ResearchedFestival(
            name="Test Festival",
            description="A test festival",
            full_description="Full description",
            event_dates=[
                EventDateData(
                    start=datetime(2026, 7, 15, 14, 0, 0),
                    end=datetime(2026, 7, 17, 23, 0, 0),
                    location_description="Berlin, Germany",
                    lineup=["Artist A", "Artist B"],
                )
            ],
            tags=["psytrance"],
        )

        result = await client.create_event(festival)

        assert result == new_event_id
        assert route.called

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_event_no_dates(self, client):
        """Test event creation without dates fails."""
        festival = ResearchedFestival(
            name="Test Festival",
            event_dates=[],
        )

        with pytest.raises(ValueError, match="event dates"):
            await client.create_event(festival)

    @respx.mock
    @pytest.mark.asyncio
    async def test_add_event_date_success(self, client):
        """Test adding event date."""
        event_id = uuid4()
        route = respx.post(f"https://api.partymap.com/api/date/event/{event_id}").mock(
            return_value=Response(201)
        )

        event_date = EventDateData(
            start=datetime(2027, 7, 15, 14, 0, 0),
            end=datetime(2027, 7, 17, 23, 0, 0),
            location_description="Berlin, Germany",
        )

        await client.add_event_date(event_id, event_date)

        assert route.called

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_event_success(self, client):
        """Test successful event update."""
        event_id = uuid4()
        route = respx.put(f"https://api.partymap.com/events/{event_id}").mock(
            return_value=Response(200)
        )

        festival = ResearchedFestival(
            name="Updated Festival Name",
            description="Updated description",
            event_dates=[
                EventDateData(
                    start=datetime(2026, 7, 15, 14, 0, 0),
                    location_description="Berlin, Germany",
                )
            ],
        )

        await client.update_event(event_id, festival)

        assert route.called

    def test_name_similarity_exact_match(self, client):
        """Test name similarity calculation."""
        similarity = client._name_similarity("Test Festival", "Test Festival")
        assert similarity > 0.9

    def test_name_similarity_partial_match(self, client):
        """Test name similarity with partial match."""
        similarity = client._name_similarity("Test Festival", "Test Festival 2026")
        assert similarity > 0.5

    def test_name_similarity_no_match(self, client):
        """Test name similarity with no match."""
        similarity = client._name_similarity("Test Festival", "Completely Different")
        assert similarity < 0.3

    def test_location_matches(self, client):
        """Test location matching."""
        assert client._location_matches("Berlin, Germany", {"description": "Berlin, Germany"})
        assert client._location_matches("Berlin", {"description": "Berlin, Germany"})
        assert not client._location_matches("Paris", {"description": "Berlin, Germany"})
