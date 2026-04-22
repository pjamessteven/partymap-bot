"""Tests for critical bug fixes in core utilities and services."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestUtcNow:
    """Test utc_now helper replaces deprecated datetime.utcnow()."""

    def test_returns_naive_datetime(self):
        """utc_now() returns a naive datetime in UTC."""
        from src.utils.utc_now import utc_now
        result = utc_now()
        assert isinstance(result, datetime)
        assert result.tzinfo is None
        # Should be very close to current UTC time
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        assert abs((now_utc - result).total_seconds()) < 1

    def test_different_calls_differ(self):
        """Multiple calls should reflect time passing."""
        from src.utils.utc_now import utc_now
        t1 = utc_now()
        import time
        time.sleep(0.01)
        t2 = utc_now()
        assert t2 >= t1


class TestPartyMapClientContextManager:
    """Test PartyMapClient supports async context manager protocol."""

    @pytest.mark.asyncio
    async def test_aenter_returns_self(self):
        """__aenter__ should return the client instance."""
        from src.partymap.client import PartyMapClient
        settings = MagicMock()
        settings.effective_partymap_base_url = "https://test.com"
        settings.partymap_api_key = "test"
        client = PartyMapClient(settings)
        result = await client.__aenter__()
        assert result is client
        await client.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_aexit_closes_client(self):
        """__aexit__ should close the HTTP client."""
        from src.partymap.client import PartyMapClient
        settings = MagicMock()
        settings.effective_partymap_base_url = "https://test.com"
        settings.partymap_api_key = "test"
        client = PartyMapClient(settings)
        client.client = MagicMock()
        client.client.aclose = AsyncMock()

        async with client:
            pass

        client.client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_with_syntax(self):
        """Can use 'async with' syntax without errors."""
        from src.partymap.client import PartyMapClient
        settings = MagicMock()
        settings.effective_partymap_base_url = "https://test.com"
        settings.partymap_api_key = "test"

        async with PartyMapClient(settings) as client:
            assert isinstance(client, PartyMapClient)


class TestBrowserServiceDoubleStart:
    """Test BrowserService guards against double-start."""

    @pytest.mark.asyncio
    async def test_start_skips_if_already_started(self):
        """start() should be a no-op if browser already exists."""
        from src.services.browser_service import BrowserService
        settings = MagicMock()
        settings.browser_headless = True
        service = BrowserService(settings)
        service.browser = MagicMock()  # Simulate already started

        # Should not raise or create new browser
        await service.start()
        assert service.browser is not None

    @pytest.mark.asyncio
    async def test_navigate_uses_timeout(self):
        """navigate() should pass browser_timeout to page.goto()."""
        from src.services.browser_service import BrowserService
        settings = MagicMock()
        settings.browser_headless = True
        settings.browser_timeout = 12345
        service = BrowserService(settings)
        service.page = MagicMock()
        service.page.goto = AsyncMock()

        await service.navigate("https://example.com")

        service.page.goto.assert_awaited_once_with(
            "https://example.com",
            wait_until="networkidle",
            timeout=12345,
        )

    @pytest.mark.asyncio
    async def test_close_nulls_references(self):
        """close() should null out references after closing."""
        from src.services.browser_service import BrowserService
        settings = MagicMock()
        service = BrowserService(settings)

        page = MagicMock()
        browser = MagicMock()
        playwright = MagicMock()
        service.page = page
        service.browser = browser
        service._playwright = playwright

        page.close = AsyncMock()
        browser.close = AsyncMock()
        playwright.stop = AsyncMock()

        await service.close()

        assert service.page is None
        assert service.browser is None
        assert service._playwright is None


class TestStreamBroadcasterListener:
    """Test StreamBroadcaster listener task lifecycle."""

    @pytest.mark.asyncio
    async def test_single_listener_task(self):
        """Multiple subscriptions should share one listener task."""
        from src.agents.streaming.broadcaster import StreamBroadcaster

        broadcaster = StreamBroadcaster()
        broadcaster.redis = AsyncMock()
        broadcaster._pubsub = AsyncMock()
        broadcaster._pubsub.subscribe = AsyncMock()
        broadcaster._pubsub.listen = AsyncMock(return_value=[])

        # First subscription creates listener
        await broadcaster.subscribe("thread-1", lambda x: None)
        assert broadcaster._listener_task is not None
        task1 = broadcaster._listener_task

        # Second subscription should reuse same listener
        await broadcaster.subscribe("thread-2", lambda x: None)
        assert broadcaster._listener_task is task1

        # Cancel to clean up
        if task1 and not task1.done():
            task1.cancel()
            try:
                await task1
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_listener_cancelled_when_no_subscribers(self):
        """Listener should be cancelled when all subscribers unsubscribe."""
        from src.agents.streaming.broadcaster import StreamBroadcaster

        # Reset singleton state
        StreamBroadcaster._instance = None
        StreamBroadcaster._initialized = False

        broadcaster = StreamBroadcaster()
        broadcaster.redis = AsyncMock()
        broadcaster._pubsub = AsyncMock()
        broadcaster._pubsub.subscribe = AsyncMock()
        broadcaster._pubsub.unsubscribe = AsyncMock()

        async def _fake_listen():
            """Fake async generator that yields once then exits cleanly."""
            yield {"type": "message", "channel": "stream:test", "data": "{}"}

        broadcaster._pubsub.listen = _fake_listen

        callback = lambda x: None
        await broadcaster.subscribe("thread-1", callback)
        task = broadcaster._listener_task
        assert task is not None

        # Wait for generator to finish naturally
        await task
        assert task.done()

        # Unsubscribe should clean up even if task already finished
        await broadcaster.unsubscribe("thread-1", callback)
        assert broadcaster._listener_task is None

        # Reset singleton for other tests
        StreamBroadcaster._instance = None
        StreamBroadcaster._initialized = False


class TestClosePostgresCheckpointer:
    """Test Postgres checkpointer cleanup."""

    def test_close_postgres_checkpointer(self):
        """close_postgres_checkpointer should close connection and reset globals."""
        from src.core.database import close_postgres_checkpointer, _postgres_conn, _postgres_checkpointer

        # Set up fake globals
        import src.core.database as db_module
        mock_conn = MagicMock()
        db_module._postgres_conn = mock_conn
        db_module._postgres_checkpointer = MagicMock()

        # Run (it's async but just calls .close() synchronously on psycopg conn)
        asyncio.run(close_postgres_checkpointer())

        mock_conn.close.assert_called_once()
        assert db_module._postgres_conn is None
        assert db_module._postgres_checkpointer is None


class TestPydanticConfigDictMigration:
    """Verify Pydantic models use ConfigDict instead of deprecated class Config."""

    def test_discovered_festival_uses_configdict(self):
        """DiscoveredFestival should accept from_attributes via ConfigDict."""
        from src.core.schemas import DiscoveredFestival
        assert hasattr(DiscoveredFestival, 'model_config')
        # Should not have old class Config
        assert 'Config' not in DiscoveredFestival.__dict__

    def test_researched_festival_uses_configdict(self):
        """ResearchedFestival should accept from_attributes via ConfigDict."""
        from src.core.schemas import ResearchedFestival
        assert hasattr(ResearchedFestival, 'model_config')
        assert 'Config' not in ResearchedFestival.__dict__

    def test_research_state_uses_configdict(self):
        """ResearchState should allow arbitrary types via ConfigDict."""
        from src.agents.research.state import ResearchState
        assert hasattr(ResearchState, 'model_config')
        assert 'Config' not in ResearchState.__dict__
        # BaseMessage should be allowed
        assert ResearchState.model_config.get('arbitrary_types_allowed') is True

    def test_refresh_state_uses_configdict(self):
        """RefreshState should allow arbitrary types via ConfigDict."""
        from src.agents.refresh.state import RefreshState
        assert hasattr(RefreshState, 'model_config')
        assert 'Config' not in RefreshState.__dict__
        assert RefreshState.model_config.get('arbitrary_types_allowed') is True
