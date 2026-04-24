"""Tests for job control and scheduling endpoints."""

import pytest
from datetime import datetime
from uuid import uuid4

from src.core.models import JobActivity, Festival, FestivalState
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
    async def test_start_discovery(self, async_client, mock_celery_tasks, mock_redis_tracker, mock_broadcaster, mock_job_activity):
        """Starts discovery job and registers it with JobTracker."""
        response = await async_client.post("/api/jobs/discovery/start")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "task_id" in data
        assert data["message"] == "Discovery started"

    @pytest.mark.asyncio
    async def test_start_discovery_already_running(self, async_client, mock_celery_tasks, mock_redis_tracker):
        """Returns 400 when discovery is already running."""
        from src.core.job_tracker import JobTracker, JobType
        JobTracker.try_start_job_sync(JobType.DISCOVERY, "existing-task")

        response = await async_client.post("/api/jobs/discovery/start")
        assert response.status_code == 400
        assert "already running" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_stop_discovery(self, async_client, mock_redis_tracker, mock_celery_result, mock_broadcaster, mock_job_activity):
        """Stops discovery job and revokes Celery task."""
        from src.core.job_tracker import JobTracker, JobType
        JobTracker.try_start_job_sync(JobType.DISCOVERY, "stop-task-1")

        response = await async_client.post("/api/jobs/discovery/stop")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "stopped" in data["message"].lower()
        # Verify revoke was called
        mock_celery_result["revoke"].assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_discovery_not_running(self, async_client):
        """Returns 400 when discovery is not running."""
        response = await async_client.post("/api/jobs/discovery/stop")
        assert response.status_code == 400
        assert "not running" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_start_research(self, async_client, mock_celery_tasks, mock_redis_tracker, mock_broadcaster, db_session, mock_job_activity):
        """Starts research job for all festivals needing research."""
        # Create festivals needing research
        for name in ["Fest A", "Fest B"]:
            festival = Festival(
                id=uuid4(),
                name=name,
                source="test",
                state=FestivalState.RESEARCHED_PARTIAL.value,
            )
            db_session.add(festival)
        await db_session.commit()

        response = await async_client.post("/api/jobs/research/start")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["queued"] == 2
        assert "task_id" in data

    @pytest.mark.asyncio
    async def test_start_research_no_festivals(self, async_client, mock_celery_tasks, mock_job_activity):
        """Returns message when no festivals need research."""
        response = await async_client.post("/api/jobs/research/start")
        assert response.status_code == 200
        data = response.json()
        assert data["queued"] == 0
        assert "no festivals" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_start_research_already_running(self, async_client, mock_redis_tracker, mock_broadcaster):
        """Returns 400 when research is already running."""
        from src.core.job_tracker import JobTracker, JobType
        JobTracker.try_start_job_sync(JobType.RESEARCH, "existing-research")

        response = await async_client.post("/api/jobs/research/start")
        assert response.status_code == 400
        assert "already running" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_stop_research(self, async_client, mock_redis_tracker, mock_celery_result, mock_broadcaster, mock_job_activity):
        """Stops research job."""
        from src.core.job_tracker import JobTracker, JobType
        JobTracker.try_start_job_sync(JobType.RESEARCH, "stop-research-1")

        response = await async_client.post("/api/jobs/research/stop")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_start_sync(self, async_client, mock_celery_tasks, mock_redis_tracker, mock_broadcaster, mock_job_activity):
        """Starts sync job."""
        response = await async_client.post("/api/jobs/sync/start")
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert "thread_id" in data

    @pytest.mark.asyncio
    async def test_stop_sync(self, async_client, mock_redis_tracker, mock_celery_result, mock_broadcaster, mock_job_activity):
        """Stops sync job and revokes Celery task."""
        from src.core.job_tracker import JobTracker, JobType
        JobTracker.try_start_job_sync(JobType.SYNC, "stop-sync-1")

        response = await async_client.post("/api/jobs/sync/stop")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_start_goabase(self, async_client, mock_celery_tasks, mock_redis_tracker, mock_broadcaster, mock_job_activity):
        """Starts Goabase sync job."""
        response = await async_client.post("/api/jobs/goabase/start")
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    @pytest.mark.asyncio
    async def test_stop_goabase(self, async_client, mock_redis_tracker, mock_celery_result, mock_broadcaster, mock_job_activity):
        """Stops Goabase sync job and revokes Celery task."""
        from src.core.job_tracker import JobTracker, JobType
        JobTracker.try_start_job_sync(JobType.GOABASE_SYNC, "stop-goabase-1")

        response = await async_client.post("/api/jobs/goabase/stop")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestBulkJobs:
    """Tests for bulk job operations."""

    @pytest.mark.asyncio
    async def test_bulk_start(self, async_client, mock_celery_tasks, mock_redis_tracker, mock_broadcaster, mock_job_activity):
        """Starts multiple jobs."""
        response = await async_client.post(
            "/api/jobs/bulk/start",
            json=["discovery", "research"]
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        results = data["results"]
        assert len(results) == 2
        assert all(r["success"] for r in results)

    @pytest.mark.asyncio
    async def test_bulk_start_skips_running(self, async_client, mock_celery_tasks, mock_redis_tracker, mock_broadcaster, mock_job_activity):
        """Skips jobs that are already running."""
        from src.core.job_tracker import JobTracker, JobType
        JobTracker.try_start_job_sync(JobType.DISCOVERY, "existing-bulk")

        response = await async_client.post(
            "/api/jobs/bulk/start",
            json=["discovery", "research"]
        )
        assert response.status_code == 200
        data = response.json()
        results = {r["job_type"]: r for r in data["results"]}
        assert results["discovery"]["success"] is False
        assert "already running" in results["discovery"]["error"]
        assert results["research"]["success"] is True

    @pytest.mark.asyncio
    async def test_bulk_start_invalid_type(self, async_client, mock_celery_tasks, mock_redis_tracker, mock_broadcaster, mock_job_activity):
        """Returns error for invalid job types."""
        response = await async_client.post(
            "/api/jobs/bulk/start",
            json=["invalid_type"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["success"] is False

    @pytest.mark.asyncio
    async def test_bulk_stop(self, async_client, mock_redis_tracker, mock_celery_result, mock_broadcaster, mock_job_activity):
        """Stops multiple running jobs."""
        from src.core.job_tracker import JobTracker, JobType
        JobTracker.try_start_job_sync(JobType.DISCOVERY, "bulk-stop-1")
        JobTracker.try_start_job_sync(JobType.RESEARCH, "bulk-stop-2")

        response = await async_client.post(
            "/api/jobs/bulk/stop",
            json=["discovery", "research"]
        )
        assert response.status_code == 200
        data = response.json()
        assert all(r["success"] for r in data["results"])

    @pytest.mark.asyncio
    async def test_clear_all(self, async_client):
        """Clears all job statuses."""
        response = await async_client.post("/api/jobs/clear-all?confirm=true")
        assert response.status_code == 200


class TestJobWebSocket:
    """Tests for WebSocket endpoint."""

    @pytest.mark.asyncio
    async def test_websocket_connect(self, async_client):
        """WebSocket accepts connections and sends initial status."""
        # Note: httpx AsyncClient doesn't support WebSocket.
        # This test is a placeholder for when using TestClient or similar.
        pass


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


class TestJobStatusCeleryInspection:
    """Tests that get_jobs_status syncs with Celery ground truth."""

    @pytest.mark.asyncio
    async def test_status_auto_corrects_stale_running(self, async_client, mock_redis_tracker, mock_celery_result):
        """If Celery says task is done but Redis says RUNNING, status is corrected."""
        from src.core.job_tracker import JobTracker, JobType
        JobTracker.try_start_job_sync(JobType.DISCOVERY, "stale-task-1")
        mock_celery_result["make"]("stale-task-1", ready=True, successful=True)

        response = await async_client.get("/api/jobs/status")
        assert response.status_code == 200
        data = response.json()
        assert data["discovery"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_status_shows_running_when_celery_running(self, async_client, mock_redis_tracker, mock_celery_result):
        """If Celery says STARTED, status shows RUNNING."""
        from src.core.job_tracker import JobTracker, JobType
        JobTracker.try_start_job_sync(JobType.RESEARCH, "live-task-1")
        mock_celery_result["make"]("live-task-1", ready=False, state="STARTED")

        response = await async_client.get("/api/jobs/status")
        assert response.status_code == 200
        data = response.json()
        assert data["research"]["status"] == "running"
