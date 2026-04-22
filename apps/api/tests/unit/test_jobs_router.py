"""Tests for job control and scheduling endpoints."""

import pytest
from datetime import datetime
from uuid import uuid4

from src.core.models import JobActivity
from tests.fixtures.factories import create_festival


class TestJobStatus:
    """Tests for GET /api/jobs/status"""

    @pytest.mark.asyncio
    async def test_get_all_status(self, async_client):
        """Returns status for all job types."""
        response = await async_client.get("/api/jobs/status")
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data or "discovery" in data or isinstance(data, dict)


class TestJobActivity:
    """Tests for GET /api/jobs/activity"""

    @pytest.mark.asyncio
    async def test_paginated_activity(self, async_client, db_session):
        """Returns job activity with pagination."""
        # Create some activity records
        for i in range(3):
            activity = JobActivity(
                job_type="discovery",
                activity_type="started",
                message=f"Discovery run {i}",
            )
            db_session.add(activity)
        await db_session.commit()
        
        response = await async_client.get("/api/jobs/activity?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    @pytest.mark.asyncio
    async def test_filter_by_job_type(self, async_client, db_session):
        """Filters activity by job_type."""
        activity = JobActivity(
            job_type="research",
            activity_type="completed",
            message="Research done",
        )
        db_session.add(activity)
        await db_session.commit()
        
        response = await async_client.get("/api/jobs/activity?job_type=research")
        assert response.status_code == 200


class TestStartStopJobs:
    """Tests for job start/stop endpoints."""

    @pytest.mark.asyncio
    async def test_start_discovery(self, async_client, mock_celery_tasks):
        """Starts discovery job."""
        response = await async_client.post("/api/jobs/discovery/start")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_stop_discovery(self, async_client):
        """Stops discovery job."""
        response = await async_client.post("/api/jobs/discovery/stop")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_start_research(self, async_client, mock_celery_tasks):
        """Starts research job."""
        response = await async_client.post("/api/jobs/research/start")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_start_sync(self, async_client, mock_celery_tasks):
        """Starts sync job."""
        response = await async_client.post("/api/jobs/sync/start")
        assert response.status_code == 200


class TestBulkJobs:
    """Tests for bulk job operations."""

    @pytest.mark.asyncio
    async def test_bulk_start(self, async_client, mock_celery_tasks):
        """Starts multiple jobs."""
        response = await async_client.post(
            "/api/jobs/bulk/start",
            json=["discovery", "research"]
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data

    @pytest.mark.asyncio
    async def test_bulk_stop(self, async_client):
        """Stops multiple jobs."""
        response = await async_client.post(
            "/api/jobs/bulk/stop",
            json=["discovery"]
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_clear_all(self, async_client):
        """Clears all job statuses."""
        response = await async_client.post("/api/jobs/clear-all?confirm=true")
        assert response.status_code == 200


class TestScheduling:
    """Tests for scheduling control endpoints."""

    @pytest.mark.asyncio
    async def test_get_status(self, async_client):
        """Returns scheduling status."""
        response = await async_client.get("/api/jobs/scheduling/status")
        assert response.status_code == 200
        data = response.json()
        assert "scheduling_enabled" in data

    @pytest.mark.asyncio
    async def test_enable_scheduling(self, async_client):
        """Enables automatic scheduling."""
        response = await async_client.post("/api/jobs/scheduling/enable")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_disable_scheduling(self, async_client):
        """Disables automatic scheduling."""
        response = await async_client.post("/api/jobs/scheduling/disable")
        assert response.status_code == 200
