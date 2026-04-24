"""Unit tests for Goabase source adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Settings
from src.core.schemas import DiscoveredFestival
from src.sources.goabase import GoabaseSource


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock(spec=Settings)
    settings.goabase_base_url = "https://www.goabase.net/api/party/"
    settings.openrouter_api_key = "test-key"
    settings.openrouter_base_url = "https://api.openrouter.ai"
    settings.openrouter_model = "deepseek/deepseek-chat"
    settings.lineup_image_max_size = 2 * 1024 * 1024
    return settings


@pytest.fixture
async def goabase_source(mock_settings):
    """Create Goabase source with mocked HTTP client."""
    source = GoabaseSource(mock_settings)
    source.client = AsyncMock()
    yield source


class TestGoabaseSource:
    """Test Goabase source functionality."""

    @pytest.mark.asyncio
    async def test_discover_success(self, goabase_source):
        """Test successful discovery."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "partylist": [
                {
                    "id": 12345,
                    "name": "Psy Festival 2026",
                    "urlPartyJson": "https://www.goabase.net/api/party/12345/json",
                },
                {
                    "id": 12346,
                    "name": "Another Festival",
                    "urlPartyJson": "https://www.goabase.net/api/party/12346/json",
                },
            ]
        }
        goabase_source.client.get = AsyncMock(return_value=mock_response)

        result = await goabase_source.discover()

        assert len(result) == 2
        assert result[0].source == "goabase"
        assert result[0].source_id == "12345"
        assert result[0].name == "Psy Festival 2026"

    @pytest.mark.asyncio
    async def test_discover_empty_list(self, goabase_source):
        """Test discovery with empty list."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"partylist": []}
        goabase_source.client.get = AsyncMock(return_value=mock_response)

        result = await goabase_source.discover()

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_research_success(self, goabase_source):
        """Test successful research."""
        discovered = DiscoveredFestival(
            source="goabase",
            source_id="12345",
            source_url="https://www.goabase.net/api/party/12345/json",
            name="Test Festival",
        )

        # Mock JSON response
        json_response = MagicMock()
        json_response.json.return_value = {"party": {"dateModified": "2024-01-15T10:00:00"}}

        # Mock JSON-LD response
        jsonld_response = MagicMock()
        jsonld_response.json.return_value = {
            "name": "Test Psytrance Festival",
            "description": "An amazing festival",
            "startDate": "2026-07-15T14:00:00",
            "endDate": "2026-07-17T23:00:00",
            "location": {
                "name": "Mystic Woods",
                "address": {
                    "addressLocality": "Berlin",
                    "addressCountry": "Germany",
                },
            },
            "url": "https://example.com/festival",
            "performers": "Artist A, Artist B, Artist C",
            "image": {"url": "https://example.com/logo.jpg"},
        }

        goabase_source.client.get = AsyncMock(side_effect=[json_response, jsonld_response])

        result = await goabase_source.research(discovered)

        fd = result.festival_data
        assert fd.name == "Test Psytrance Festival"
        assert len(fd.event_dates) == 1
        assert fd.event_dates[0].location_description == "Mystic Woods, Berlin, Germany"
        assert len(fd.event_dates[0].lineup) == 3
        assert "goabase" in fd.tags
        assert "psytrance" in fd.tags

    @pytest.mark.asyncio
    async def test_research_missing_url(self, goabase_source):
        """Test research with missing URL."""
        discovered = DiscoveredFestival(
            source="goabase",
            source_id="12345",
            source_url=None,
            name="Test Festival",
        )

        with pytest.raises(ValueError, match="missing source_url"):
            await goabase_source.research(discovered)

    @pytest.mark.asyncio
    async def test_health_check_success(self, goabase_source):
        """Test health check when API is available."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        goabase_source.client.get = AsyncMock(return_value=mock_response)

        result = await goabase_source.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, goabase_source):
        """Test health check when API is down."""
        goabase_source.client.get = AsyncMock(side_effect=Exception("Connection error"))

        result = await goabase_source.health_check()

        assert result is False
