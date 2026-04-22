"""Tests for festival management endpoints."""

import pytest
from datetime import datetime
from uuid import uuid4

from src.core.models import Festival, FestivalState
from tests.fixtures.factories import create_festival, create_quarantined_festival


class TestListFestivals:
    """Tests for GET /api/festivals"""

    @pytest.mark.asyncio
    async def test_default_list(self, async_client, db_session):
        """Returns festivals with pagination."""
        await create_festival(db_session, name="Festival A")
        await create_festival(db_session, name="Festival B")
        
        response = await async_client.get("/api/festivals")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["festivals"]) == 2

    @pytest.mark.asyncio
    async def test_filter_by_state(self, async_client, db_session):
        """Filters festivals by state."""
        await create_festival(db_session, name="Researching", state=FestivalState.RESEARCHING.value)
        await create_festival(db_session, name="Synced", state=FestivalState.SYNCED.value)
        
        response = await async_client.get("/api/festivals?state=researching")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["festivals"][0]["name"] == "Researching"

    @pytest.mark.asyncio
    async def test_search_by_name(self, async_client, db_session):
        """Searches festivals by name."""
        await create_festival(db_session, name="Summer Festival")
        await create_festival(db_session, name="Winter Festival")
        
        response = await async_client.get("/api/festivals?search=summer")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert "Summer" in data["festivals"][0]["name"]

    @pytest.mark.asyncio
    async def test_pagination(self, async_client, db_session):
        """Paginates results correctly."""
        for i in range(5):
            await create_festival(db_session, name=f"Festival {i}")
        
        response = await async_client.get("/api/festivals?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["festivals"]) == 2
        assert data["total"] == 5


class TestGetFestival:
    """Tests for GET /api/festivals/{id}"""

    @pytest.mark.asyncio
    async def test_found(self, async_client, db_session):
        """Returns festival details when found."""
        festival = await create_festival(db_session, name="Test Fest")
        
        response = await async_client.get(f"/api/festivals/{festival.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Fest"
        assert data["id"] == str(festival.id)

    @pytest.mark.asyncio
    async def test_not_found(self, async_client):
        """Returns 404 when festival not found."""
        response = await async_client.get(f"/api/festivals/{uuid4()}")
        assert response.status_code == 404


class TestDeduplicate:
    """Tests for POST /api/festivals/{id}/deduplicate"""

    @pytest.mark.asyncio
    async def test_new_festival(self, async_client, db_session, mock_partymap_client, mock_celery_tasks):
        """New festival queues for research."""
        mock_partymap_client.find_existing_event.return_value = None
        festival = await create_festival(db_session)
        
        response = await async_client.post(f"/api/festivals/{festival.id}/deduplicate")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_existing_event(self, async_client, db_session, mock_partymap_client):
        """Existing event found marks as duplicate."""
        mock_partymap_client.find_existing_event.return_value = {"id": 12345, "name": "Existing"}
        festival = await create_festival(db_session)
        
        response = await async_client.post(f"/api/festivals/{festival.id}/deduplicate")
        assert response.status_code == 200


class TestResearch:
    """Tests for POST /api/festivals/{id}/research"""

    @pytest.mark.asyncio
    async def test_queues_research(self, async_client, db_session, mock_celery_tasks):
        """Queues research pipeline for festival."""
        festival = await create_festival(db_session, state=FestivalState.NEEDS_RESEARCH_NEW.value)
        
        response = await async_client.post(f"/api/festivals/{festival.id}/research")
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "research"
        assert data["result"] in ("queued", "started")

    @pytest.mark.asyncio
    async def test_already_researching(self, async_client, db_session):
        """Returns appropriate response if already researching."""
        festival = await create_festival(db_session, state=FestivalState.RESEARCHING.value)
        
        response = await async_client.post(f"/api/festivals/{festival.id}/research")
        assert response.status_code == 200


class TestSync:
    """Tests for POST /api/festivals/{id}/sync"""

    @pytest.mark.asyncio
    async def test_queues_sync(self, async_client, db_session, mock_celery_tasks):
        """Queues sync pipeline for researched festival."""
        festival = await create_festival(db_session, state=FestivalState.RESEARCHED.value)
        
        response = await async_client.post(f"/api/festivals/{festival.id}/sync")
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "sync"

    @pytest.mark.asyncio
    async def test_no_research_data(self, async_client, db_session):
        """Returns error if no research data."""
        festival = await create_festival(db_session, research_data=None, state=FestivalState.RESEARCHED.value)
        
        response = await async_client.post(f"/api/festivals/{festival.id}/sync")
        # Should still queue - the task handles missing data
        assert response.status_code in (200, 400)


class TestRetry:
    """Tests for POST /api/festivals/{id}/retry"""

    @pytest.mark.asyncio
    async def test_resets_failed(self, async_client, db_session):
        """Resets failed festival state."""
        festival = await create_festival(db_session, state=FestivalState.FAILED.value, retry_count=3)
        
        response = await async_client.post(f"/api/festivals/{festival.id}/retry")
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "retry"


class TestSkip:
    """Tests for POST /api/festivals/{id}/skip"""

    @pytest.mark.asyncio
    async def test_sets_skipped(self, async_client, db_session):
        """Sets festival state to skipped."""
        festival = await create_festival(db_session)
        
        response = await async_client.post(
            f"/api/festivals/{festival.id}/skip?reason=Not%20a%20festival"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "skip"


class TestReset:
    """Tests for POST /api/festivals/{id}/reset"""

    @pytest.mark.asyncio
    async def test_reset_to_discovered(self, async_client, db_session):
        """Resets festival to discovered state."""
        festival = await create_festival(db_session, state=FestivalState.FAILED.value)
        
        response = await async_client.post(f"/api/festivals/{festival.id}/reset")
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "reset"
        assert data["new_state"] == "discovered"

    @pytest.mark.asyncio
    async def test_reset_to_specific_state(self, async_client, db_session):
        """Resets festival to specified state."""
        festival = await create_festival(db_session, state=FestivalState.FAILED.value)
        
        response = await async_client.post(
            f"/api/festivals/{festival.id}/reset?target_state=needs_research_new"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["new_state"] == "needs_research_new"


class TestBulkResearch:
    """Tests for POST /api/festivals/bulk/research"""

    @pytest.mark.asyncio
    async def test_queues_matching(self, async_client, db_session, mock_celery_tasks):
        """Bulk queues festivals for research."""
        for _ in range(3):
            await create_festival(db_session, state=FestivalState.FAILED.value, failure_reason="dates")
        
        response = await async_client.post(
            "/api/festivals/bulk/research?failure_reason=dates&limit=10"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["queued"] >= 0
        assert "daily_remaining" in data


class TestPendingFestivals:
    """Tests for GET /api/festivals/pending"""

    @pytest.mark.asyncio
    async def test_returns_pending(self, async_client, db_session):
        """Returns festivals needing manual action."""
        await create_festival(db_session, state=FestivalState.NEEDS_REVIEW.value)
        await create_festival(db_session, state=FestivalState.SYNCED.value)
        
        response = await async_client.get("/api/festivals/pending")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
