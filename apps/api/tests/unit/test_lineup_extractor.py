"""Unit tests for lineup extraction."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Settings
from src.research.lineup_extractor import LineupExtractor


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock(spec=Settings)
    settings.openrouter_api_key = "test-key"
    settings.openrouter_base_url = "https://api.openrouter.ai"
    settings.openrouter_model = "deepseek/deepseek-chat"
    settings.lineup_image_max_size = 2 * 1024 * 1024
    return settings


@pytest.fixture
async def extractor(mock_settings):
    """Create lineup extractor with mocked client."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        extractor = LineupExtractor(mock_settings)
        yield extractor


class TestLineupExtractor:
    """Test lineup extraction functionality."""

    @pytest.mark.asyncio
    async def test_extract_lineup_from_description(self, extractor):
        """Test extracting lineup from text description."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"artists": ["The Beatles", "Led Zeppelin", "Pink Floyd"]}
                        )
                    }
                }
            ]
        }
        extractor.client.post = AsyncMock(return_value=mock_response)

        result = await extractor.extract_lineup(
            description="Lineup: The Beatles, Led Zeppelin, Pink Floyd",
        )

        assert len(result) == 3
        assert "The Beatles" in result
        assert "Led Zeppelin" in result
        assert "Pink Floyd" in result

    @pytest.mark.asyncio
    async def test_extract_lineup_empty_response(self, extractor):
        """Test handling empty lineup response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps({"artists": []})}}]
        }
        extractor.client.post = AsyncMock(return_value=mock_response)

        result = await extractor.extract_lineup(
            description="No lineup announced yet",
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_extract_lineup_handles_duplicates(self, extractor):
        """Test that duplicate artists are removed."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"artists": ["Artist A", "Artist B", "Artist A", "Artist C"]}
                        )
                    }
                }
            ]
        }
        extractor.client.post = AsyncMock(return_value=mock_response)

        result = await extractor.extract_lineup(description="test")

        assert len(result) == 3
        assert result.count("Artist A") == 1

    @pytest.mark.asyncio
    async def test_extract_lineup_api_error(self, extractor):
        """Test handling API errors gracefully."""
        from httpx import HTTPError

        extractor.client.post = AsyncMock(side_effect=HTTPError("API Error"))

        result = await extractor.extract_lineup(description="test")

        assert result == []

    def test_clean_artists(self, extractor):
        """Test artist name cleaning."""
        raw_artists = [
            "  artist name  ",
            "ARTIST NAME",  # Should become title case
            "Artist (Live)",  # Should remove suffix
            "Artist (DJ Set)",
            "A",  # Too short, should be removed
            "Valid Artist",
        ]

        cleaned = extractor._clean_artists(raw_artists)

        assert "Artist Name" in cleaned
        assert "Artist" in cleaned  # Without suffix
        assert "A" not in cleaned
        assert "Valid Artist" in cleaned

    def test_build_prompt_with_description(self, extractor):
        """Test prompt building with description."""
        prompt = extractor._build_prompt("Festival description here")

        assert "Festival Description:" in prompt
        assert "Festival description here" in prompt
        assert "JSON" in prompt

    def test_build_prompt_without_description(self, extractor):
        """Test prompt building without description."""
        prompt = extractor._build_prompt(None)

        assert "Festival Description:" not in prompt
        assert "JSON" in prompt
