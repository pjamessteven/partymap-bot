"""Unit tests for deduplication engine."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.deduplication import DeduplicationAgent, DeduplicationResult


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    return MagicMock()


@pytest.fixture
def mock_llm():
    """Create mock LLM client."""
    llm = MagicMock()
    llm.chat_completion = AsyncMock()
    return llm


@pytest.fixture
def mock_partymap():
    """Create mock PartyMap client."""
    client = MagicMock()
    client.search_events = AsyncMock(return_value=[])
    return client


@pytest.fixture
def dedup_agent(mock_settings, mock_llm, mock_partymap):
    """Create deduplication agent."""
    return DeduplicationAgent(mock_settings, mock_llm, mock_partymap)


class TestCheckDuplicate:
    """Tests for check_duplicate method."""

    @pytest.mark.asyncio
    async def test_no_matches_found(self, dedup_agent, mock_partymap):
        """No potential matches → not duplicate with 1.0 confidence."""
        mock_partymap.search_events.return_value = []

        result = await dedup_agent.check_duplicate(
            discovered_name="Brand New Festival",
            discovered_location="Berlin",
        )

        assert result.is_duplicate is False
        assert result.confidence == 1.0
        assert "No events found" in result.reasoning

    @pytest.mark.asyncio
    async def test_llm_says_duplicate(self, dedup_agent, mock_partymap, mock_llm):
        """LLM determines it's a duplicate."""
        mock_partymap.search_events.return_value = [
            {"id": 123, "name": "Existing Festival", "location": {"description": "Berlin"}}
        ]
        mock_llm.chat_completion.return_value = json.dumps({
            "is_duplicate": True,
            "confidence": 0.95,
            "update_reasons": ["missing_dates"],
            "reasoning": "Same festival",
        })

        result = await dedup_agent.check_duplicate(
            discovered_name="Existing Festival",
            discovered_location="Berlin",
        )

        assert result.is_duplicate is True
        assert result.confidence == 0.95
        assert result.event_id == 123
        assert "missing_dates" in result.update_reasons
        mock_llm.chat_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_says_not_duplicate(self, dedup_agent, mock_partymap, mock_llm):
        """LLM determines it's NOT a duplicate → default not-duplicate result."""
        mock_partymap.search_events.return_value = [
            {"id": 123, "name": "Different Festival", "location": {"description": "Hamburg"}}
        ]
        mock_llm.chat_completion.return_value = json.dumps({
            "is_duplicate": False,
            "confidence": 0.1,
            "update_reasons": [],
            "reasoning": "Different location and name",
        })

        result = await dedup_agent.check_duplicate(
            discovered_name="My Festival",
            discovered_location="Berlin",
        )

        assert result.is_duplicate is False
        # When no match is found, check_duplicate returns default confidence=1.0
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_uses_clean_name_for_search(self, dedup_agent, mock_partymap):
        """When clean_name provided, it's used as search query."""
        mock_partymap.search_events.return_value = []

        await dedup_agent.check_duplicate(
            discovered_name="Festival 2026",
            discovered_location="Berlin",
            clean_name="Festival",
        )

        mock_partymap.search_events.assert_awaited_once_with("Festival", limit=10)

    @pytest.mark.asyncio
    async def test_llm_error_defaults_to_not_duplicate(self, dedup_agent, mock_partymap, mock_llm):
        """LLM failure defaults to not duplicate to be safe."""
        mock_partymap.search_events.return_value = [
            {"id": 123, "name": "Existing", "location": {"description": "Berlin"}}
        ]
        mock_llm.chat_completion.side_effect = Exception("LLM timeout")

        result = await dedup_agent.check_duplicate(
            discovered_name="Existing",
            discovered_location="Berlin",
        )

        assert result.is_duplicate is False
        # When all evaluations fail, check_duplicate returns default confidence=1.0
        assert result.confidence == 1.0


class TestEvaluateMatchWithLLM:
    """Tests for _evaluate_match_with_llm method."""

    @pytest.mark.asyncio
    async def test_builds_prompt_with_event_data(self, dedup_agent, mock_llm):
        """Prompt includes discovered and existing event details."""
        mock_llm.chat_completion.return_value = json.dumps({
            "is_duplicate": True,
            "confidence": 0.9,
            "update_reasons": [],
            "reasoning": "Match",
        })

        existing_event = {
            "name": "Test Fest",
            "location": {"description": "Berlin"},
            "next_date": {"start": "2026-07-15", "end": "2026-07-17", "confirmed": True},
        }

        result = await dedup_agent._evaluate_match_with_llm(
            discovered_name="Test Fest",
            discovered_location="Berlin",
            discovered_dates="2026-07-15",
            discovered_description="A festival",
            existing_event=existing_event,
        )

        assert result.is_duplicate is True
        # Verify prompt was built with key info
        call_args = mock_llm.chat_completion.call_args
        messages = call_args.kwargs["messages"]
        prompt = messages[1]["content"]
        assert "Test Fest" in prompt
        assert "Berlin" in prompt
        assert "2026-07-15" in prompt

    @pytest.mark.asyncio
    async def test_handles_no_next_dates(self, dedup_agent, mock_llm):
        """Existing event without next_date doesn't crash."""
        mock_llm.chat_completion.return_value = json.dumps({
            "is_duplicate": False,
            "confidence": 0.5,
            "update_reasons": [],
            "reasoning": "No dates",
        })

        existing_event = {
            "name": "Old Fest",
            "location": {"description": "Berlin"},
        }

        result = await dedup_agent._evaluate_match_with_llm(
            discovered_name="Old Fest",
            discovered_location="Berlin",
            discovered_dates=None,
            discovered_description=None,
            existing_event=existing_event,
        )

        assert result.confidence == 0.5


class TestBatchCheckDuplicates:
    """Tests for batch_check_duplicates method."""

    @pytest.mark.asyncio
    async def test_processes_multiple_festivals(self, dedup_agent, mock_partymap, mock_llm):
        """Batch processes multiple festivals."""
        mock_partymap.search_events.return_value = []

        festivals = [
            {"name": "Fest A", "location": "Berlin"},
            {"name": "Fest B", "location": "Hamburg"},
        ]

        results = await dedup_agent.batch_check_duplicates(festivals)

        assert len(results) == 2
        assert all(not r.is_duplicate for r in results)
        assert mock_partymap.search_events.await_count == 2

    @pytest.mark.asyncio
    async def test_calls_progress_callback(self, dedup_agent, mock_partymap):
        """Progress callback is called for each festival."""
        mock_partymap.search_events.return_value = []
        progress = AsyncMock()

        festivals = [
            {"name": "Fest A", "location": "Berlin"},
            {"name": "Fest B", "location": "Hamburg"},
        ]

        await dedup_agent.batch_check_duplicates(festivals, progress_callback=progress)

        assert progress.await_count == 2


class TestDeduplicationResult:
    """Tests for DeduplicationResult dataclass."""

    def test_defaults(self):
        """Default values are sensible."""
        result = DeduplicationResult(is_duplicate=False, confidence=0.0)
        assert result.event_id is None
        assert result.event_data is None
        assert result.update_reasons == []
        assert result.reasoning == ""

    def test_update_reasons_initialization(self):
        """Update reasons can be provided."""
        result = DeduplicationResult(
            is_duplicate=True,
            confidence=0.9,
            update_reasons=["missing_dates", "lineup_released"],
        )
        assert len(result.update_reasons) == 2
