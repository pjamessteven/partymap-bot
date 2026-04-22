"""Tests for error tracking, DLQ, and circuit breaker endpoints."""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from src.core.models import Festival, FestivalState
from tests.fixtures.factories import create_festival, create_quarantined_festival


class TestErrorStats:
    """Tests for GET /errors/stats"""

    @pytest.mark.asyncio
    async def test_empty_database(self, async_client):
        """Returns empty stats when no errors exist."""
        response = await async_client.get("/api/errors/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["dlq"]["total_quarantined"] == 0
        assert data["circuit_breakers"]["partymap"]["state"] == "closed"
        assert data["errors_by_category"] == {}
        assert data["validation_summary"] == {}

    @pytest.mark.asyncio
    async def test_with_quarantined_festivals(self, async_client, db_session):
        """Returns quarantine counts by category."""
        await create_quarantined_festival(db_session, error_category="transient")
        await create_quarantined_festival(db_session, error_category="validation")
        
        response = await async_client.get("/api/errors/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["dlq"]["total_quarantined"] == 2
        assert data["dlq"]["by_category"]["transient"] == 1
        assert data["dlq"]["by_category"]["validation"] == 1
        assert data["errors_by_category"]["transient"] == 1
        assert data["errors_by_category"]["validation"] == 1


class TestQuarantinedFestivals:
    """Tests for GET /errors/quarantined"""

    @pytest.mark.asyncio
    async def test_empty_list(self, async_client):
        """Returns empty items when no quarantined festivals."""
        response = await async_client.get("/api/errors/quarantined")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_paginated_list(self, async_client, db_session):
        """Returns quarantined festivals with pagination."""
        for i in range(5):
            await create_quarantined_festival(db_session, name=f"Failed {i}")
        
        response = await async_client.get("/api/errors/quarantined?limit=3&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert data["total"] == 5
        assert data["limit"] == 3
        assert data["offset"] == 0

    @pytest.mark.asyncio
    async def test_filter_by_category(self, async_client, db_session):
        """Filters quarantined festivals by error category."""
        await create_quarantined_festival(db_session, name="Transient Fail", error_category="transient")
        await create_quarantined_festival(db_session, name="Validation Fail", error_category="validation")
        
        response = await async_client.get("/api/errors/quarantined?error_category=transient")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["error_category"] == "transient"
        assert data["total"] == 1


class TestRetryQuarantined:
    """Tests for POST /errors/quarantined/{id}/retry"""

    @pytest.mark.asyncio
    async def test_successful_retry(self, async_client, db_session):
        """Retries quarantined festival and resets state."""
        festival = await create_quarantined_festival(db_session, retry_count=5)
        
        response = await async_client.post(f"/api/errors/quarantined/{festival.id}/retry")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["new_state"] == "needs_research_new"

    @pytest.mark.asyncio
    async def test_invalid_festival_id(self, async_client):
        """Returns 400 for invalid UUID."""
        response = await async_client.post("/api/errors/quarantined/not-a-uuid/retry")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_not_quarantined(self, async_client, db_session):
        """Returns 400 if festival is not quarantined."""
        festival = await create_festival(db_session, state=FestivalState.FAILED.value)
        
        response = await async_client.post(f"/api/errors/quarantined/{festival.id}/retry")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_force_retry_bypasses_validation(self, async_client, db_session):
        """Force=true bypasses validation check."""
        festival = await create_quarantined_festival(db_session)
        festival.research_data = {"invalid": "data"}
        await db_session.commit()
        
        response = await async_client.post(
            f"/api/errors/quarantined/{festival.id}/retry?force=true"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestBulkRetry:
    """Tests for POST /errors/quarantined/bulk-retry"""

    @pytest.mark.asyncio
    async def test_mixed_success_failure(self, async_client, db_session):
        """Some succeed, some fail."""
        f1 = await create_quarantined_festival(db_session, name="Good")
        f2 = await create_quarantined_festival(db_session, name="Bad")
        
        response = await async_client.post(
            "/api/errors/quarantined/bulk-retry",
            json={"festival_ids": [str(f1.id), str(f2.id), "not-a-uuid"]}
        )
        assert response.status_code == 400  # Invalid UUID in list

    @pytest.mark.asyncio
    async def test_successful_bulk_retry(self, async_client, db_session):
        """Retries multiple valid festivals."""
        f1 = await create_quarantined_festival(db_session)
        f2 = await create_quarantined_festival(db_session)
        
        response = await async_client.post(
            "/api/errors/quarantined/bulk-retry",
            json={"festival_ids": [str(f1.id), str(f2.id)]}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["successful"] == 2
        assert data["failed"] == 0


class TestCleanup:
    """Tests for POST /errors/cleanup"""

    @pytest.mark.asyncio
    async def test_no_expired(self, async_client, db_session):
        """Returns 0 when nothing to clean up."""
        response = await async_client.post("/api/errors/cleanup")
        assert response.status_code == 200
        data = response.json()
        assert data["cleaned_up"] == 0

    @pytest.mark.asyncio
    async def test_expired_quarantined(self, async_client, db_session):
        """Deletes festivals quarantined more than 30 days ago."""
        old = await create_quarantined_festival(db_session)
        old.quarantined_at = datetime.utcnow() - timedelta(days=31)
        await db_session.commit()
        
        response = await async_client.post("/api/errors/cleanup")
        assert response.status_code == 200
        data = response.json()
        assert data["cleaned_up"] == 1


class TestCircuitBreakers:
    """Tests for circuit breaker endpoints."""

    @pytest.mark.asyncio
    async def test_all_closed(self, async_client):
        """Returns all circuit breakers as closed."""
        response = await async_client.get("/api/errors/circuit-breakers")
        assert response.status_code == 200
        data = response.json()
        assert "breakers" in data
        for name, metrics in data["breakers"].items():
            assert metrics["state"] == "closed"

    @pytest.mark.asyncio
    async def test_reset_breaker(self, async_client):
        """Resets a circuit breaker to closed."""
        response = await async_client.post("/api/errors/circuit-breakers/partymap/reset")
        assert response.status_code == 200
        data = response.json()
        assert "reset to CLOSED" in data["message"]

    @pytest.mark.asyncio
    async def test_reset_unknown_breaker(self, async_client):
        """Returns 404 for unknown breaker name."""
        response = await async_client.post("/api/errors/circuit-breakers/unknown/reset")
        assert response.status_code == 404


class TestValidateFestival:
    """Tests for POST /errors/festivals/{id}/validate"""

    @pytest.mark.asyncio
    async def test_valid_data(self, async_client, db_session):
        """Valid festival data returns ready status."""
        from tests.fixtures.mock_data import VALID_FESTIVAL_DATA
        festival = await create_festival(db_session, research_data=VALID_FESTIVAL_DATA)
        
        response = await async_client.post(f"/api/errors/festivals/{festival.id}/validate")
        assert response.status_code == 200
        data = response.json()
        assert data["validation"]["status"] in ("ready", "needs_review")

    @pytest.mark.asyncio
    async def test_invalid_data(self, async_client, db_session):
        """Invalid festival data returns validation_failed."""
        from tests.fixtures.mock_data import INVALID_FESTIVAL_DATA
        festival = await create_festival(db_session, research_data=INVALID_FESTIVAL_DATA)
        
        response = await async_client.post(f"/api/errors/festivals/{festival.id}/validate")
        assert response.status_code == 200
        data = response.json()
        assert data["validation"]["status"] == "invalid"
        assert len(data["validation"]["errors"]) > 0

    @pytest.mark.asyncio
    async def test_no_research_data(self, async_client, db_session):
        """Returns 400 if no research_data exists."""
        festival = await create_festival(db_session, research_data=None)
        
        response = await async_client.post(f"/api/errors/festivals/{festival.id}/validate")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_not_found(self, async_client):
        """Returns 404 for non-existent festival."""
        response = await async_client.post(f"/api/errors/festivals/{uuid4()}/validate")
        assert response.status_code == 404
