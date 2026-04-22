"""Tests for refresh pipeline endpoints."""

import pytest
from uuid import uuid4

from tests.fixtures.factories import create_refresh_approval


class TestListApprovals:
    """Tests for GET /api/refresh/approvals"""

    @pytest.mark.asyncio
    async def test_empty(self, async_client):
        """Returns empty list when no approvals."""
        response = await async_client.get("/api/refresh/approvals")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_pending_only(self, async_client, db_session):
        """Returns pending and auto_approved by default."""
        await create_refresh_approval(db_session, status="pending")
        await create_refresh_approval(db_session, status="auto_approved")
        await create_refresh_approval(db_session, status="rejected")
        
        response = await async_client.get("/api/refresh/approvals")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_filter_by_status(self, async_client, db_session):
        """Filters by status query param."""
        await create_refresh_approval(db_session, status="pending")
        await create_refresh_approval(db_session, status="approved")
        
        response = await async_client.get("/api/refresh/approvals?status=approved")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == "approved"


class TestGetApproval:
    """Tests for GET /api/refresh/approvals/{id}"""

    @pytest.mark.asyncio
    async def test_found(self, async_client, db_session):
        """Returns approval details."""
        approval = await create_refresh_approval(db_session, event_name="Test Fest")
        
        response = await async_client.get(f"/api/refresh/approvals/{approval.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["event_name"] == "Test Fest"
        assert data["id"] == str(approval.id)

    @pytest.mark.asyncio
    async def test_not_found(self, async_client):
        """Returns 404 for unknown approval."""
        response = await async_client.get(f"/api/refresh/approvals/{uuid4()}")
        assert response.status_code == 404


class TestApprove:
    """Tests for POST /api/refresh/approvals/{id}/approve"""

    @pytest.mark.asyncio
    async def test_success(self, async_client, db_session, mock_celery_tasks):
        """Approves and queues apply task."""
        approval = await create_refresh_approval(db_session, status="pending")
        
        response = await async_client.post(f"/api/refresh/approvals/{approval.id}/approve")
        assert response.status_code == 200
        data = response.json()
        assert "approved" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_already_approved(self, async_client, db_session):
        """Returns 400 if already approved."""
        approval = await create_refresh_approval(db_session, status="approved")
        
        response = await async_client.post(f"/api/refresh/approvals/{approval.id}/approve")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_not_found(self, async_client):
        """Returns 404 for unknown approval."""
        response = await async_client.post(f"/api/refresh/approvals/{uuid4()}/approve")
        assert response.status_code == 404


class TestReject:
    """Tests for POST /api/refresh/approvals/{id}/reject"""

    @pytest.mark.asyncio
    async def test_success(self, async_client, db_session):
        """Rejects approval."""
        approval = await create_refresh_approval(db_session, status="pending")
        
        response = await async_client.post(
            f"/api/refresh/approvals/{approval.id}/reject?reason=Not%20accurate"
        )
        assert response.status_code == 200
        data = response.json()
        assert "rejected" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_already_rejected(self, async_client, db_session):
        """Returns 400 if already rejected."""
        approval = await create_refresh_approval(db_session, status="rejected")
        
        response = await async_client.post(f"/api/refresh/approvals/{approval.id}/reject")
        assert response.status_code == 400


class TestTrigger:
    """Tests for POST /api/refresh/trigger"""

    @pytest.mark.asyncio
    async def test_default_params(self, async_client, mock_celery_tasks):
        """Triggers with default days_ahead=120."""
        response = await async_client.post("/api/refresh/trigger")
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["days_ahead"] == 120

    @pytest.mark.asyncio
    async def test_custom_days(self, async_client, mock_celery_tasks):
        """Triggers with custom days_ahead."""
        response = await async_client.post("/api/refresh/trigger?days_ahead=60")
        assert response.status_code == 200
        data = response.json()
        assert data["days_ahead"] == 60


class TestStats:
    """Tests for GET /api/refresh/stats"""

    @pytest.mark.asyncio
    async def test_empty(self, async_client):
        """Returns empty stats."""
        response = await async_client.get("/api/refresh/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["pending"] == 0
        assert data["approved_last_7_days"] == 0

    @pytest.mark.asyncio
    async def test_with_approvals(self, async_client, db_session):
        """Returns counts by status."""
        await create_refresh_approval(db_session, status="pending")
        await create_refresh_approval(db_session, status="approved")
        
        response = await async_client.get("/api/refresh/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["pending"] >= 1
        assert "counts" in data
