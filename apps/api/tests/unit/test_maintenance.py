"""Tests for maintenance tasks."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.models import FestivalState
from src.tasks.maintenance import cleanup_failed, retry_failed


class FakeResult:
    """Fake SQLAlchemy result with rowcount."""

    def __init__(self, rowcount):
        self.rowcount = rowcount


class FakeSession:
    """Fake async DB session for maintenance task tests."""

    def __init__(self):
        self.committed = False
        self.execute_calls = []

    async def execute(self, stmt):
        self.execute_calls.append(stmt)
        return FakeResult(rowcount=3)

    async def commit(self):
        self.committed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


def _make_fake_session_factory(session):
    """Return an async context manager class that yields the given session."""
    class FakeSessionFactory:
        async def __aenter__(self):
            return session
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return False
    return FakeSessionFactory()


class TestCleanupFailed:
    """Tests for cleanup_failed Celery task."""

    @patch("src.tasks.maintenance.AsyncSessionLocal")
    @patch("src.tasks.maintenance.utc_now")
    @patch("src.tasks.maintenance.settings")
    def test_deletes_old_failed_festivals(
        self, mock_settings, mock_utc_now, mock_session_local
    ):
        """Task deletes festivals past purge date."""
        now = datetime(2026, 6, 1, 12, 0, 0)
        mock_utc_now.return_value = now
        mock_settings.failed_festival_retention_days = 30

        session = FakeSession()
        mock_session_local.return_value = _make_fake_session_factory(session)

        result = cleanup_failed()

        assert result == {"deleted": 3}
        assert session.committed is True
        assert len(session.execute_calls) == 1

    @patch("src.tasks.maintenance.AsyncSessionLocal")
    @patch("src.tasks.maintenance.utc_now")
    @patch("src.tasks.maintenance.settings")
    def test_zero_deleted(
        self, mock_settings, mock_utc_now, mock_session_local
    ):
        """Task handles zero deletions gracefully."""
        now = datetime(2026, 6, 1, 12, 0, 0)
        mock_utc_now.return_value = now
        mock_settings.failed_festival_retention_days = 30

        session = FakeSession()
        # Override execute to return 0 rowcount for this test
        async def zero_execute(stmt):
            session.execute_calls.append(stmt)
            return FakeResult(rowcount=0)

        session.execute = zero_execute
        mock_session_local.return_value = _make_fake_session_factory(session)

        result = cleanup_failed()

        assert result == {"deleted": 0}


class TestRetryFailed:
    """Tests for retry_failed Celery task."""

    @patch("src.tasks.maintenance.AsyncSessionLocal")
    @patch("src.tasks.maintenance.utc_now")
    @patch("src.tasks.pipeline.research_pipeline")
    def test_retries_failed_festivals(
        self, mock_research_pipeline, mock_utc_now, mock_session_local
    ):
        """Task resets failed festivals and queues research."""
        now = datetime(2026, 6, 1, 12, 0, 0)
        mock_utc_now.return_value = now

        # Create fake festival objects
        fake_festival_1 = MagicMock()
        fake_festival_1.id = "f1"
        fake_festival_1.state = FestivalState.FAILED
        fake_festival_1.retry_count = 2
        fake_festival_1.last_error = "Previous error"

        fake_festival_2 = MagicMock()
        fake_festival_2.id = "f2"
        fake_festival_2.state = FestivalState.FAILED
        fake_festival_2.retry_count = 1
        fake_festival_2.last_error = "Another error"

        # Mock session.execute to return festivals
        class RetrySession:
            def __init__(self):
                self.committed = False

            async def execute(self, stmt):
                result = MagicMock()
                result.scalars.return_value.all.return_value = [fake_festival_1, fake_festival_2]
                return result

            async def commit(self):
                self.committed = True

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return False

        session = RetrySession()
        mock_session_local.return_value = _make_fake_session_factory(session)

        result = retry_failed()

        assert result == {"retried": 2}
        assert session.committed is True
        assert fake_festival_1.state == FestivalState.RESEARCHING
        assert fake_festival_1.retry_count == 0
        assert fake_festival_1.last_error is None
        assert fake_festival_2.state == FestivalState.RESEARCHING
        assert mock_research_pipeline.delay.call_count == 2

    @patch("src.tasks.maintenance.AsyncSessionLocal")
    @patch("src.tasks.maintenance.utc_now")
    @patch("src.tasks.pipeline.research_pipeline")
    def test_no_failed_festivals(
        self, mock_research_pipeline, mock_utc_now, mock_session_local
    ):
        """Task handles no failed festivals gracefully."""
        now = datetime(2026, 6, 1, 12, 0, 0)
        mock_utc_now.return_value = now

        class EmptySession:
            def __init__(self):
                self.committed = False

            async def execute(self, stmt):
                result = MagicMock()
                result.scalars.return_value.all.return_value = []
                return result

            async def commit(self):
                self.committed = True

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return False

        session = EmptySession()
        mock_session_local.return_value = _make_fake_session_factory(session)

        result = retry_failed()

        assert result == {"retried": 0}
        assert session.committed is True
        assert mock_research_pipeline.delay.call_count == 0
