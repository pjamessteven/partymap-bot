"""Unit tests for deduplication engine."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.config import Settings
from src.core.schemas import EventDate, ResearchedFestival
from src.partymap.client import PartyMapClient
from src.partymap.deduplication import DeduplicationEngine


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    return MagicMock(spec=Settings)


@pytest.fixture
def mock_client(mock_settings):
    """Create mock PartyMap client."""
    client = MagicMock(spec=PartyMapClient)
    return client


@pytest.fixture
def dedup_engine(mock_client, mock_settings):
    """Create deduplication engine."""
    return DeduplicationEngine(mock_client, mock_settings)


class TestDeduplicationEngine:
    """Test deduplication logic."""

    @pytest.mark.asyncio
    async def test_process_new_festival(self, dedup_engine, mock_client):
        """Test processing a completely new festival."""
        mock_client.find_existing_event = AsyncMock(return_value=None)

        festival = ResearchedFestival(
            name="Brand New Festival",
            event_dates=[
                EventDate(
                    start=datetime(2026, 7, 15),
                    location_description="Berlin",
                )
            ],
        )

        is_dup, existing_id, action = await dedup_engine.process_festival(festival)

        assert is_dup is False
        assert existing_id is None
        assert action == "new"

    @pytest.mark.asyncio
    async def test_process_duplicate_skip(self, dedup_engine, mock_client):
        """Test processing duplicate that's up to date."""
        existing_id = uuid4()
        mock_client.find_existing_event = AsyncMock(
            return_value={
                "id": str(existing_id),
                "name": "Existing Festival",
                "event_dates": [
                    {
                        "start": "2026-07-15T00:00:00",
                        "location": {"description": "Berlin"},
                    }
                ],
            }
        )
        mock_client.should_update_event = AsyncMock(return_value=False)

        festival = ResearchedFestival(
            name="Existing Festival",
            event_dates=[
                EventDate(
                    start=datetime(2026, 7, 15),
                    location_description="Berlin",
                )
            ],
            source_modified=datetime(2024, 1, 1),
        )

        is_dup, found_id, action = await dedup_engine.process_festival(festival)

        assert is_dup is True
        assert found_id == existing_id
        assert action == "skip"

    @pytest.mark.asyncio
    async def test_process_duplicate_update(self, dedup_engine, mock_client):
        """Test processing duplicate that needs update."""
        existing_id = uuid4()
        mock_client.find_existing_event = AsyncMock(
            return_value={
                "id": str(existing_id),
                "name": "Existing Festival",
                "event_dates": [
                    {
                        "start": "2026-07-15T00:00:00",
                        "location": {"description": "Berlin"},
                    }
                ],
            }
        )
        mock_client.should_update_event = AsyncMock(return_value=True)

        festival = ResearchedFestival(
            name="Existing Festival",
            event_dates=[
                EventDate(
                    start=datetime(2026, 7, 15),
                    location_description="Berlin",
                )
            ],
            source_modified=datetime(2024, 6, 1),
        )

        is_dup, found_id, action = await dedup_engine.process_festival(festival)

        assert is_dup is True
        assert found_id == existing_id
        assert action == "update"

    @pytest.mark.asyncio
    async def test_process_new_event_date(self, dedup_engine, mock_client):
        """Test processing new date for existing festival."""
        existing_id = uuid4()
        mock_client.find_existing_event = AsyncMock(
            return_value={
                "id": str(existing_id),
                "name": "Festival Series",
                "event_dates": [
                    {
                        "start": "2026-07-15T00:00:00",
                        "location": {"description": "Berlin"},
                    }
                ],
            }
        )

        # Same festival but different date
        festival = ResearchedFestival(
            name="Festival Series",
            event_dates=[
                EventDate(
                    start=datetime(2027, 7, 15),  # Different year
                    location_description="Berlin",
                )
            ],
        )

        is_dup, found_id, action = await dedup_engine.process_festival(festival)

        assert is_dup is True
        assert found_id == existing_id
        assert action == "add_date"

    def test_is_new_event_date_same_date(self, dedup_engine):
        """Test checking if same event date."""
        existing_event = {
            "event_dates": [
                {
                    "start": "2026-07-15T14:00:00",
                    "location": {"description": "Berlin, Germany"},
                }
            ]
        }

        festival = ResearchedFestival(
            name="Test",
            event_dates=[
                EventDate(
                    start=datetime(2026, 7, 15, 14, 0, 0),
                    location_description="Berlin",
                )
            ],
        )

        result = dedup_engine._is_new_event_date(existing_event, festival)
        assert result is False  # Same date, not new

    def test_is_new_event_date_different_location(self, dedup_engine):
        """Test checking different location same date."""
        existing_event = {
            "event_dates": [
                {
                    "start": "2026-07-15T14:00:00",
                    "location": {"description": "Berlin, Germany"},
                }
            ]
        }

        festival = ResearchedFestival(
            name="Test",
            event_dates=[
                EventDate(
                    start=datetime(2026, 7, 15, 14, 0, 0),
                    location_description="Hamburg, Germany",
                )
            ],
        )

        result = dedup_engine._is_new_event_date(existing_event, festival)
        assert result is True  # Different location = new event date

    def test_is_new_event_date_different_year(self, dedup_engine):
        """Test checking different year."""
        existing_event = {
            "event_dates": [
                {
                    "start": "2026-07-15T14:00:00",
                    "location": {"description": "Berlin, Germany"},
                }
            ]
        }

        festival = ResearchedFestival(
            name="Test",
            event_dates=[
                EventDate(
                    start=datetime(2027, 7, 15, 14, 0, 0),  # Next year
                    location_description="Berlin, Germany",
                )
            ],
        )

        result = dedup_engine._is_new_event_date(existing_event, festival)
        assert result is True  # Different year = new event date

    def test_locations_similar(self, dedup_engine):
        """Test location similarity matching."""
        assert dedup_engine._locations_similar("Berlin", "Berlin, Germany")
        assert dedup_engine._locations_similar("Berlin, Germany", "Berlin")
        assert not dedup_engine._locations_similar("Berlin", "Hamburg")
        assert not dedup_engine._locations_similar(None, "Berlin")

    @pytest.mark.asyncio
    async def test_sync_new_festival(self, dedup_engine, mock_client):
        """Test syncing new festival."""
        new_id = uuid4()
        mock_client.create_event = AsyncMock(return_value=new_id)

        festival = ResearchedFestival(
            name="New Festival",
            event_dates=[EventDate(start=datetime(2026, 7, 15), location_description="Berlin")],
        )

        result = await dedup_engine.sync_festival(festival, False, None, "new")

        assert result == new_id
        mock_client.create_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_update_festival(self, dedup_engine, mock_client):
        """Test syncing update to existing festival."""
        existing_id = uuid4()
        mock_client.update_event = AsyncMock()

        festival = ResearchedFestival(
            name="Updated Festival",
            event_dates=[EventDate(start=datetime(2026, 7, 15), location_description="Berlin")],
        )

        result = await dedup_engine.sync_festival(festival, True, existing_id, "update")

        assert result == existing_id
        mock_client.update_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_add_date(self, dedup_engine, mock_client):
        """Test syncing new event date."""
        existing_id = uuid4()
        mock_client.add_event_date = AsyncMock()

        festival = ResearchedFestival(
            name="Festival",
            event_dates=[EventDate(start=datetime(2027, 7, 15), location_description="Berlin")],
        )

        result = await dedup_engine.sync_festival(festival, True, existing_id, "add_date")

        assert result == existing_id
        mock_client.add_event_date.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_skip(self, dedup_engine, mock_client):
        """Test skipping up-to-date festival."""
        existing_id = uuid4()

        festival = ResearchedFestival(name="Festival", event_dates=[])

        result = await dedup_engine.sync_festival(festival, True, existing_id, "skip")

        assert result == existing_id
        mock_client.create_event.assert_not_called()
        mock_client.update_event.assert_not_called()
