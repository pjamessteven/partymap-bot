"""Tests for Dead Letter Queue operations."""

import pytest
from datetime import datetime, timedelta

from src.core.models import Festival, FestivalState
from src.services.dead_letter_queue import DeadLetterQueue
from tests.fixtures.factories import create_festival, create_quarantined_festival


class TestQuarantine:
    """Tests for quarantine operations."""

    @pytest.mark.asyncio
    async def test_quarantine_sets_state(self, db_session):
        """Quarantine sets festival to QUARANTINED state."""
        festival = await create_festival(db_session, state=FestivalState.FAILED.value, retry_count=5)
        dlq = DeadLetterQueue(db_session)
        
        result = await dlq.quarantine(
            festival.id,
            reason="Max retries reached",
            error_category="transient",
        )
        
        assert result is True
        await db_session.refresh(festival)
        assert festival.state == FestivalState.QUARANTINED.value
        assert festival.quarantine_reason == "Max retries reached"
        assert festival.error_category == "transient"

    @pytest.mark.asyncio
    async def test_should_quarantine_after_max_retries(self, db_session):
        """Should quarantine when retry_count >= 5."""
        festival = await create_festival(db_session, retry_count=5)
        dlq = DeadLetterQueue(db_session)
        
        assert await dlq.should_quarantine(festival.id) is True

    @pytest.mark.asyncio
    async def test_should_not_quarantine_low_retries(self, db_session):
        """Should not quarantine when retry_count < 5."""
        festival = await create_festival(db_session, retry_count=2)
        dlq = DeadLetterQueue(db_session)
        
        assert await dlq.should_quarantine(festival.id) is False


class TestRetry:
    """Tests for retry operations."""

    @pytest.mark.asyncio
    async def test_retry_resets_fields(self, db_session):
        """Retry resets state, retry_count, and error fields."""
        festival = await create_quarantined_festival(db_session, retry_count=5)
        dlq = DeadLetterQueue(db_session)
        
        result = await dlq.retry(festival.id)
        
        assert result["success"] is True
        assert result["new_state"] == "needs_research_new"
        await db_session.refresh(festival)
        assert festival.retry_count == 0
        assert festival.max_retries_reached is False
        assert festival.quarantined_at is None

    @pytest.mark.asyncio
    async def test_retry_not_quarantined(self, db_session):
        """Cannot retry non-quarantined festival."""
        festival = await create_festival(db_session, state=FestivalState.FAILED.value)
        dlq = DeadLetterQueue(db_session)
        
        result = await dlq.retry(festival.id)
        
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_force_retry_bypasses_validation(self, db_session):
        """Force=true bypasses validation check."""
        festival = await create_quarantined_festival(db_session)
        festival.research_data = {"invalid": "data"}
        await db_session.commit()
        
        dlq = DeadLetterQueue(db_session)
        result = await dlq.retry(festival.id, force=True)
        
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_bulk_retry(self, db_session):
        """Bulk retry handles multiple festivals."""
        f1 = await create_quarantined_festival(db_session)
        f2 = await create_quarantined_festival(db_session)
        
        dlq = DeadLetterQueue(db_session)
        result = await dlq.bulk_retry([f1.id, f2.id])
        
        assert result["total"] == 2
        assert result["successful"] == 2
        assert result["failed"] == 0


class TestCleanup:
    """Tests for cleanup operations."""

    @pytest.mark.asyncio
    async def test_no_expired(self, db_session):
        """Returns 0 when no expired festivals."""
        dlq = DeadLetterQueue(db_session)
        count = await dlq.cleanup_expired()
        assert count == 0

    @pytest.mark.asyncio
    async def test_removes_expired(self, db_session):
        """Deletes festivals quarantined >30 days ago."""
        festival = await create_quarantined_festival(db_session)
        festival.quarantined_at = datetime.utcnow() - timedelta(days=31)
        await db_session.commit()
        
        dlq = DeadLetterQueue(db_session)
        count = await dlq.cleanup_expired()
        
        assert count == 1

    @pytest.mark.asyncio
    async def test_keeps_recent(self, db_session):
        """Does not delete recently quarantined festivals."""
        festival = await create_quarantined_festival(db_session)
        festival.quarantined_at = datetime.utcnow() - timedelta(days=5)
        await db_session.commit()
        
        dlq = DeadLetterQueue(db_session)
        count = await dlq.cleanup_expired()
        
        assert count == 0


class TestGetQuarantined:
    """Tests for get_quarantined method."""

    @pytest.mark.asyncio
    async def test_get_quarantined_list(self, db_session):
        """Returns quarantined festivals ordered by quarantined_at."""
        f1 = await create_quarantined_festival(db_session, name="Old", error_category="transient")
        f1.quarantined_at = datetime.utcnow() - timedelta(days=1)
        f2 = await create_quarantined_festival(db_session, name="New", error_category="validation")
        f2.quarantined_at = datetime.utcnow()
        await db_session.commit()
        
        dlq = DeadLetterQueue(db_session)
        results = await dlq.get_quarantined(limit=10)
        
        assert len(results) == 2
        assert results[0].name == "New"  # Most recent first

    @pytest.mark.asyncio
    async def test_filter_by_category(self, db_session):
        """Filters by error category."""
        await create_quarantined_festival(db_session, error_category="transient")
        await create_quarantined_festival(db_session, error_category="validation")
        
        dlq = DeadLetterQueue(db_session)
        results = await dlq.get_quarantined(error_category="transient")
        
        assert len(results) == 1
        assert results[0].error_category == "transient"

    @pytest.mark.asyncio
    async def test_get_stats(self, db_session):
        """Returns quarantine statistics."""
        await create_quarantined_festival(db_session, error_category="transient")
        await create_quarantined_festival(db_session, error_category="transient")
        await create_quarantined_festival(db_session, error_category="validation")
        
        dlq = DeadLetterQueue(db_session)
        stats = await dlq.get_quarantine_stats()
        
        assert stats["total_quarantined"] == 3
        assert stats["by_category"]["transient"] == 2
        assert stats["by_category"]["validation"] == 1
        assert stats["retention_days"] == 30
