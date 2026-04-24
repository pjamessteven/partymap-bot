"""Tests for JobTracker."""

import json

import pytest

from src.core.job_tracker import JobTracker, JobType, JobStatus


class TestJobTrackerAsyncMethods:
    """Tests for async JobTracker methods."""

    @pytest.mark.asyncio
    async def test_start_job(self, mock_redis_tracker, mock_job_activity):
        """start_job stores RUNNING status in Redis."""
        await JobTracker.start_job(JobType.DISCOVERY, "task-123", total_items=10)

        status = JobTracker.get_status(JobType.DISCOVERY)
        assert status is not None
        assert status["status"] == "running"
        assert status["task_id"] == "task-123"
        assert status["progress"]["total"] == 10
        assert status["progress"]["current"] == 0

    @pytest.mark.asyncio
    async def test_try_start_job_atomic(self, mock_redis_tracker, mock_job_activity):
        """try_start_job returns True when job is not running."""
        result = await JobTracker.try_start_job(JobType.DISCOVERY, "task-123", total_items=10)

        assert result is True
        status = JobTracker.get_status(JobType.DISCOVERY)
        assert status["status"] == "running"

    @pytest.mark.asyncio
    async def test_try_start_job_rejects_duplicate(self, mock_redis_tracker, mock_job_activity):
        """try_start_job returns False when job is already running."""
        first = await JobTracker.try_start_job(JobType.DISCOVERY, "task-first")
        assert first is True

        second = await JobTracker.try_start_job(JobType.DISCOVERY, "task-second")
        assert second is False

        # Original task should remain
        status = JobTracker.get_status(JobType.DISCOVERY)
        assert status["task_id"] == "task-first"

    @pytest.mark.asyncio
    async def test_try_start_job_allows_restart_after_stop(self, mock_redis_tracker, mock_job_activity):
        """try_start_job allows restarting after stop_job releases the lock."""
        await JobTracker.try_start_job(JobType.DISCOVERY, "task-1")
        await JobTracker.stop_job(JobType.DISCOVERY)

        result = await JobTracker.try_start_job(JobType.DISCOVERY, "task-2")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_running_true(self, mock_redis_tracker, mock_job_activity):
        """is_running returns True for a running job."""
        await JobTracker.start_job(JobType.RESEARCH, "task-456")

        assert JobTracker.is_running(JobType.RESEARCH) is True

    @pytest.mark.asyncio
    async def test_is_running_false(self, mock_redis_tracker):
        """is_running returns False when no job is stored."""
        assert JobTracker.is_running(JobType.SYNC) is False

    @pytest.mark.asyncio
    async def test_complete_job(self, mock_redis_tracker, mock_job_activity):
        """complete_job updates status to COMPLETED."""
        await JobTracker.start_job(JobType.DISCOVERY, "task-789")
        await JobTracker.complete_job(JobType.DISCOVERY, result={"processed": 5})

        status = JobTracker.get_status(JobType.DISCOVERY)
        assert status["status"] == "completed"
        assert status["result"]["processed"] == 5
        assert "completed_at" in status
        assert status["currently_processing"] == []

    @pytest.mark.asyncio
    async def test_fail_job(self, mock_redis_tracker, mock_job_activity):
        """fail_job updates status to FAILED."""
        await JobTracker.start_job(JobType.SYNC, "task-abc")
        await JobTracker.fail_job(JobType.SYNC, error="Connection timeout")

        status = JobTracker.get_status(JobType.SYNC)
        assert status["status"] == "failed"
        assert status["error"] == "Connection timeout"
        assert "failed_at" in status

    @pytest.mark.asyncio
    async def test_stop_job(self, mock_redis_tracker, mock_job_activity):
        """stop_job updates status to STOPPED."""
        await JobTracker.start_job(JobType.GOABASE_SYNC, "task-def")
        success = await JobTracker.stop_job(JobType.GOABASE_SYNC)

        assert success is True
        status = JobTracker.get_status(JobType.GOABASE_SYNC)
        assert status["status"] == "stopped"
        assert "stopped_at" in status

    @pytest.mark.asyncio
    async def test_stop_job_not_running(self, mock_redis_tracker):
        """stop_job returns False when job is not running."""
        success = await JobTracker.stop_job(JobType.DISCOVERY)
        assert success is False

    @pytest.mark.asyncio
    async def test_update_progress(self, mock_redis_tracker, mock_job_activity):
        """update_progress updates current/total/percent."""
        await JobTracker.start_job(JobType.DISCOVERY, "task-ghi", total_items=20)
        await JobTracker.update_progress(JobType.DISCOVERY, current=5, total=20)

        status = JobTracker.get_status(JobType.DISCOVERY)
        assert status["progress"]["current"] == 5
        assert status["progress"]["total"] == 20
        assert status["progress"]["percent"] == 25.0

    @pytest.mark.asyncio
    async def test_update_progress_with_festival(self, mock_redis_tracker, mock_job_activity):
        """update_progress adds festival to currently_processing."""
        await JobTracker.start_job(JobType.RESEARCH, "task-jkl")
        await JobTracker.update_progress(
            JobType.RESEARCH, current=1, total=3,
            festival_id="fest-1", festival_name="Test Fest"
        )

        status = JobTracker.get_status(JobType.RESEARCH)
        processing = status["currently_processing"]
        assert len(processing) == 1
        assert processing[0]["id"] == "fest-1"
        assert processing[0]["name"] == "Test Fest"

    @pytest.mark.asyncio
    async def test_mark_festival_complete(self, mock_redis_tracker, mock_job_activity):
        """mark_festival_complete removes festival from processing list."""
        await JobTracker.start_job(JobType.SYNC, "task-mno")
        await JobTracker.update_progress(
            JobType.SYNC, current=1, total=2,
            festival_id="fest-a", festival_name="Fest A"
        )
        await JobTracker.mark_festival_complete(JobType.SYNC, "fest-a")

        status = JobTracker.get_status(JobType.SYNC)
        assert status["currently_processing"] == []

    @pytest.mark.asyncio
    async def test_get_all_status(self, mock_redis_tracker, mock_job_activity):
        """get_all_status returns status for all job types."""
        await JobTracker.start_job(JobType.DISCOVERY, "task-1")
        await JobTracker.complete_job(JobType.DISCOVERY)

        all_status = JobTracker.get_all_status()
        assert "discovery" in all_status
        assert "research" in all_status
        assert all_status["discovery"]["status"] == "completed"
        assert all_status["research"] is None

    @pytest.mark.asyncio
    async def test_clear_job(self, mock_redis_tracker, mock_job_activity):
        """clear_job removes status from Redis."""
        await JobTracker.start_job(JobType.DISCOVERY, "task-pqr")
        JobTracker.clear_job(JobType.DISCOVERY)

        assert JobTracker.get_status(JobType.DISCOVERY) is None

    @pytest.mark.asyncio
    async def test_clear_all_jobs(self, mock_redis_tracker, mock_job_activity):
        """clear_all_jobs removes all statuses."""
        await JobTracker.start_job(JobType.DISCOVERY, "task-1")
        await JobTracker.start_job(JobType.RESEARCH, "task-2")
        JobTracker.clear_all_jobs()

        for job_type in JobType:
            assert JobTracker.get_status(job_type) is None


class TestJobTrackerSyncMethods:
    """Tests for sync JobTracker methods (used by Celery signals)."""

    def test_start_job_sync(self, mock_redis_tracker):
        """start_job_sync stores RUNNING status synchronously."""
        JobTracker.start_job_sync(JobType.DISCOVERY, "sync-task-1")

        status = JobTracker.get_status(JobType.DISCOVERY)
        assert status["status"] == "running"
        assert status["task_id"] == "sync-task-1"

    def test_try_start_job_sync_atomic(self, mock_redis_tracker):
        """try_start_job_sync returns True when job is not running."""
        result = JobTracker.try_start_job_sync(JobType.DISCOVERY, "sync-task-1")

        assert result is True
        status = JobTracker.get_status(JobType.DISCOVERY)
        assert status["status"] == "running"

    def test_try_start_job_sync_rejects_duplicate(self, mock_redis_tracker):
        """try_start_job_sync returns False when job is already running."""
        first = JobTracker.try_start_job_sync(JobType.DISCOVERY, "sync-first")
        assert first is True

        second = JobTracker.try_start_job_sync(JobType.DISCOVERY, "sync-second")
        assert second is False

        status = JobTracker.get_status(JobType.DISCOVERY)
        assert status["task_id"] == "sync-first"

    def test_complete_job_sync(self, mock_redis_tracker):
        """complete_job_sync updates status to COMPLETED."""
        JobTracker.start_job_sync(JobType.RESEARCH, "sync-task-2")
        JobTracker.complete_job_sync(JobType.RESEARCH, result={"processed": 3})

        status = JobTracker.get_status(JobType.RESEARCH)
        assert status["status"] == "completed"

    def test_fail_job_sync(self, mock_redis_tracker):
        """fail_job_sync updates status to FAILED."""
        JobTracker.start_job_sync(JobType.SYNC, "sync-task-3")
        JobTracker.fail_job_sync(JobType.SYNC, error="Boom")

        status = JobTracker.get_status(JobType.SYNC)
        assert status["status"] == "failed"

    def test_stop_job_sync(self, mock_redis_tracker):
        """stop_job_sync updates status to STOPPED."""
        JobTracker.start_job_sync(JobType.GOABASE_SYNC, "sync-task-4")
        success = JobTracker.stop_job_sync(JobType.GOABASE_SYNC)

        assert success is True
        assert JobTracker.get_status(JobType.GOABASE_SYNC)["status"] == "stopped"

    def test_stop_job_sync_not_running(self, mock_redis_tracker):
        """stop_job_sync returns False when no job is running."""
        success = JobTracker.stop_job_sync(JobType.DISCOVERY)
        assert success is False

    def test_update_progress_sync(self, mock_redis_tracker):
        """update_progress_sync updates progress synchronously."""
        JobTracker.start_job_sync(JobType.DISCOVERY, "sync-task-5", total_items=100)
        JobTracker.update_progress_sync(JobType.DISCOVERY, current=50, total=100)

        status = JobTracker.get_status(JobType.DISCOVERY)
        assert status["progress"]["percent"] == 50.0

    def test_mark_festival_complete_sync(self, mock_redis_tracker):
        """mark_festival_complete_sync removes festival synchronously."""
        JobTracker.start_job_sync(JobType.SYNC, "sync-task-6")
        JobTracker.update_progress_sync(
            JobType.SYNC, current=1, total=2,
            festival_id="f-1", festival_name="F1"
        )
        JobTracker.mark_festival_complete_sync(JobType.SYNC, "f-1")

        assert JobTracker.get_status(JobType.SYNC)["currently_processing"] == []


class TestJobTrackerCeleryIntegration:
    """Tests for Celery inspection and task revocation."""

    def _build_fake_app(self, task_configs: dict):
        """Build a fake Celery app for direct injection into inspect_and_sync_status.

        Args:
            task_configs: Dict mapping task_id -> {"ready": bool, "successful": bool, "state": str, "result": any}
        """
        from unittest.mock import MagicMock

        def get_result(task_id):
            cfg = task_configs.get(task_id, {})
            m = MagicMock()
            m.ready.return_value = cfg.get("ready", False)
            m.successful.return_value = cfg.get("successful", False)
            m.state = cfg.get("state", "PENDING")
            m.result = cfg.get("result", None)
            return m

        fake_app = MagicMock()
        fake_app.AsyncResult = MagicMock(side_effect=get_result)
        fake_app.control.revoke = MagicMock()
        return fake_app

    def test_revoke_task(self, mock_redis_tracker, mock_celery_result):
        """revoke_task calls celery_app.control.revoke."""
        JobTracker.start_job_sync(JobType.DISCOVERY, "revoke-task-1")
        success = JobTracker.revoke_task(JobType.DISCOVERY)

        assert success is True
        mock_celery_result["revoke"].assert_called_once_with(
            "revoke-task-1", terminate=True, signal="SIGTERM"
        )

    def test_revoke_task_no_status(self, mock_redis_tracker, mock_celery_result):
        """revoke_task returns False when no status exists."""
        success = JobTracker.revoke_task(JobType.RESEARCH)
        assert success is False

    def test_inspect_and_sync_status_running(self, mock_redis_tracker):
        """inspect_and_sync_status returns running job unchanged."""
        JobTracker.start_job_sync(JobType.DISCOVERY, "inspect-task-1")
        fake_app = self._build_fake_app({
            "inspect-task-1": {"ready": False, "state": "STARTED"}
        })
        status = JobTracker.inspect_and_sync_status(JobType.DISCOVERY, _celery_app=fake_app)
        assert status["status"] == "running"

    def test_inspect_and_sync_status_stale_completed(self, mock_redis_tracker):
        """inspect_and_sync_status auto-corrects RUNNING to COMPLETED."""
        JobTracker.start_job_sync(JobType.RESEARCH, "inspect-task-2")
        fake_app = self._build_fake_app({
            "inspect-task-2": {"ready": True, "successful": True, "state": "SUCCESS"}
        })
        status = JobTracker.inspect_and_sync_status(JobType.RESEARCH, _celery_app=fake_app)
        assert status["status"] == "completed"
        assert "completed_at" in status

    def test_inspect_and_sync_status_stale_failed(self, mock_redis_tracker):
        """inspect_and_sync_status auto-corrects RUNNING to FAILED."""
        JobTracker.start_job_sync(JobType.SYNC, "inspect-task-3")
        fake_app = self._build_fake_app({
            "inspect-task-3": {"ready": True, "successful": False, "state": "FAILURE", "result": "TimeoutError"}
        })
        status = JobTracker.inspect_and_sync_status(JobType.SYNC, _celery_app=fake_app)
        assert status["status"] == "failed"
        assert status["error"] == "TimeoutError"

    def test_inspect_and_sync_status_celery_started_but_redis_missing(self, mock_redis_tracker):
        """inspect_and_sync_status reconstructs state when Celery has STARTED but Redis is stale."""
        JobTracker.start_job_sync(JobType.DISCOVERY, "inspect-task-4")
        # Manually change Redis to something weird
        mock_redis_tracker[JobTracker._key(JobType.DISCOVERY)] = json.dumps({
            "status": "pending", "task_id": "inspect-task-4"
        })
        fake_app = self._build_fake_app({
            "inspect-task-4": {"ready": False, "state": "STARTED"}
        })
        status = JobTracker.inspect_and_sync_status(JobType.DISCOVERY, _celery_app=fake_app)
        assert status["status"] == "running"

    def test_get_all_status_synced(self, mock_redis_tracker):
        """get_all_status_synced inspects all jobs."""
        JobTracker.start_job_sync(JobType.DISCOVERY, "synced-task-1")
        JobTracker.start_job_sync(JobType.RESEARCH, "synced-task-2")

        fake_app = self._build_fake_app({
            "synced-task-2": {"ready": True, "successful": True, "state": "SUCCESS"}
        })
        # get_all_status_synced doesn't accept _celery_app, so we test individual inspect_and_sync_status
        discovery_status = JobTracker.inspect_and_sync_status(JobType.DISCOVERY, _celery_app=fake_app)
        research_status = JobTracker.inspect_and_sync_status(JobType.RESEARCH, _celery_app=fake_app)

        assert discovery_status["status"] == "running"
        assert research_status["status"] == "completed"
        assert JobTracker.get_all_status_synced()["sync"] is None


class TestJobTrackerProcessingFestivals:
    """Tests for get_processing_festivals."""

    @pytest.mark.asyncio
    async def test_get_processing_festivals(self, mock_redis_tracker, mock_job_activity):
        """get_processing_festivals returns currently processing items."""
        await JobTracker.start_job(JobType.SYNC, "task-proc")
        await JobTracker.update_progress(
            JobType.SYNC, current=1, total=3,
            festival_id="f-1", festival_name="Fest One"
        )
        await JobTracker.update_progress(
            JobType.SYNC, current=2, total=3,
            festival_id="f-2", festival_name="Fest Two"
        )

        festivals = JobTracker.get_processing_festivals(JobType.SYNC)
        assert len(festivals) == 2
        assert festivals[0]["name"] == "Fest One"
        assert festivals[1]["name"] == "Fest Two"

    def test_get_processing_festivals_empty(self, mock_redis_tracker):
        """get_processing_festivals returns empty list when no job."""
        assert JobTracker.get_processing_festivals(JobType.DISCOVERY) == []
