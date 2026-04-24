"""Tests for Celery signal handlers in src/tasks/signals.py."""

import pytest
from unittest.mock import MagicMock, patch

from src.core.job_tracker import JobTracker, JobType, JobStatus
from src.tasks.signals import on_task_prerun, on_task_postrun, on_task_failure


class TestCelerySignals:
    """Tests for Celery task signal handlers."""

    @pytest.fixture(autouse=True)
    def clean_redis(self, mock_redis_tracker):
        """Ensure clean Redis state for each test."""
        JobTracker.clear_all_jobs()
        yield
        JobTracker.clear_all_jobs()

    def test_prerun_discovery(self, mock_redis_tracker):
        """task_prerun signal marks discovery as RUNNING."""
        sender = MagicMock()
        sender.name = "src.tasks.pipeline.discovery_pipeline"

        on_task_prerun(sender, task_id="celery-task-1", task=sender, args=(), kwargs={})

        status = JobTracker.get_status(JobType.DISCOVERY)
        assert status is not None
        assert status["status"] == "running"
        assert status["task_id"] == "celery-task-1"

    def test_prerun_research(self, mock_redis_tracker):
        """task_prerun signal marks research as RUNNING."""
        sender = MagicMock()
        sender.name = "src.tasks.pipeline.research_pipeline"

        on_task_prerun(sender, task_id="celery-task-2", task=sender, args=("fest-id",), kwargs={})

        status = JobTracker.get_status(JobType.RESEARCH)
        assert status["status"] == "running"

    def test_prerun_sync(self, mock_redis_tracker):
        """task_prerun signal marks sync as RUNNING."""
        sender = MagicMock()
        sender.name = "src.tasks.pipeline.sync_pipeline"

        on_task_prerun(sender, task_id="celery-task-3", task=sender, args=(), kwargs={})

        status = JobTracker.get_status(JobType.SYNC)
        assert status["status"] == "running"

    def test_prerun_run_sync_task(self, mock_redis_tracker):
        """task_prerun signal marks sync for run_sync_task wrapper."""
        sender = MagicMock()
        sender.name = "src.tasks.pipeline.run_sync_task"

        on_task_prerun(sender, task_id="celery-task-4", task=sender, args=(), kwargs={})

        status = JobTracker.get_status(JobType.SYNC)
        assert status["status"] == "running"

    def test_prerun_goabase(self, mock_redis_tracker):
        """task_prerun signal marks goabase_sync as RUNNING."""
        sender = MagicMock()
        sender.name = "src.tasks.goabase_tasks.goabase_sync_task"

        on_task_prerun(sender, task_id="celery-task-5", task=sender, args=(), kwargs={})

        status = JobTracker.get_status(JobType.GOABASE_SYNC)
        assert status["status"] == "running"

    def test_prerun_refresh(self, mock_redis_tracker):
        """task_prerun signal marks refresh as RUNNING."""
        sender = MagicMock()
        sender.name = "src.tasks.refresh_pipeline.refresh_unconfirmed_dates_task"

        on_task_prerun(sender, task_id="celery-task-6", task=sender, args=(), kwargs={})

        status = JobTracker.get_status(JobType.REFRESH)
        assert status["status"] == "running"

    def test_prerun_unknown_task(self, mock_redis_tracker):
        """task_prerun ignores unknown tasks."""
        sender = MagicMock()
        sender.name = "src.tasks.maintenance.cleanup_failed"

        on_task_prerun(sender, task_id="celery-task-7", task=sender, args=(), kwargs={})

        # No status should be set for any job type
        for job_type in JobType:
            assert JobTracker.get_status(job_type) is None

    def test_postrun_success(self, mock_redis_tracker):
        """task_postrun on SUCCESS marks job COMPLETED."""
        # Pre-run to set up state
        sender = MagicMock()
        sender.name = "src.tasks.pipeline.discovery_pipeline"
        on_task_prerun(sender, task_id="post-task-1", task=sender, args=(), kwargs={})

        on_task_postrun(
            sender, task_id="post-task-1", task=sender,
            args=(), kwargs={}, retval={"count": 5}, state="SUCCESS"
        )

        status = JobTracker.get_status(JobType.DISCOVERY)
        assert status["status"] == "completed"
        assert status["result"]["retval"] == "{'count': 5}"

    def test_postrun_failure_state(self, mock_redis_tracker):
        """task_postrun on FAILURE does NOT mark job (failure signal handles it)."""
        sender = MagicMock()
        sender.name = "src.tasks.pipeline.research_pipeline"
        on_task_prerun(sender, task_id="post-task-2", task=sender, args=(), kwargs={})

        on_task_postrun(
            sender, task_id="post-task-2", task=sender,
            args=(), kwargs={}, retval=None, state="FAILURE"
        )

        # Postrun doesn't change state on FAILURE - the failure signal does
        status = JobTracker.get_status(JobType.RESEARCH)
        assert status["status"] == "running"

    def test_postrun_retry(self, mock_redis_tracker):
        """task_postrun on RETRY keeps job as RUNNING."""
        sender = MagicMock()
        sender.name = "src.tasks.pipeline.discovery_pipeline"
        on_task_prerun(sender, task_id="post-task-3", task=sender, args=(), kwargs={})

        on_task_postrun(
            sender, task_id="post-task-3", task=sender,
            args=(), kwargs={}, retval=None, state="RETRY"
        )

        status = JobTracker.get_status(JobType.DISCOVERY)
        assert status["status"] == "running"

    def test_postrun_unknown_task(self, mock_redis_tracker):
        """task_postrun ignores unknown tasks."""
        sender = MagicMock()
        sender.name = "some.random.task"

        on_task_postrun(
            sender, task_id="post-task-4", task=sender,
            args=(), kwargs={}, retval=None, state="SUCCESS"
        )

        for job_type in JobType:
            assert JobTracker.get_status(job_type) is None

    def test_failure_signal(self, mock_redis_tracker):
        """task_failure signal marks job as FAILED."""
        sender = MagicMock()
        sender.name = "src.tasks.pipeline.sync_pipeline"
        on_task_prerun(sender, task_id="fail-task-1", task=sender, args=(), kwargs={})

        on_task_failure(
            sender, task_id="fail-task-1", exception=Exception("DB timeout"),
            args=(), kwargs={}, traceback="tb", einfo=None
        )

        status = JobTracker.get_status(JobType.SYNC)
        assert status["status"] == "failed"
        assert "DB timeout" in status["error"]

    def test_failure_signal_no_exception(self, mock_redis_tracker):
        """task_failure signal handles None exception gracefully."""
        sender = MagicMock()
        sender.name = "src.tasks.pipeline.discovery_pipeline"
        on_task_prerun(sender, task_id="fail-task-2", task=sender, args=(), kwargs={})

        on_task_failure(
            sender, task_id="fail-task-2", exception=None,
            args=(), kwargs={}, traceback="tb", einfo=None
        )

        status = JobTracker.get_status(JobType.DISCOVERY)
        assert status["status"] == "failed"
        assert status["error"] == "Task failed"

    def test_failure_signal_unknown_task(self, mock_redis_tracker):
        """task_failure ignores unknown tasks."""
        sender = MagicMock()
        sender.name = "some.random.task"

        on_task_failure(
            sender, task_id="fail-task-3", exception=Exception("boom"),
            args=(), kwargs={}, traceback="tb", einfo=None
        )

        for job_type in JobType:
            assert JobTracker.get_status(job_type) is None

    def test_signal_exception_safety(self, mock_redis_tracker):
        """Signal handlers must never raise even on errors."""
        sender = MagicMock()
        sender.name = "src.tasks.pipeline.discovery_pipeline"

        # Corrupt Redis to cause errors
        import json
        from src.core.job_tracker import get_redis_client
        get_redis_client().set(
            JobTracker._key(JobType.DISCOVERY),
            "not-valid-json"
        )

        # These should NOT raise
        on_task_prerun(sender, task_id="safe-1", task=sender, args=(), kwargs={})
        on_task_postrun(
            sender, task_id="safe-1", task=sender,
            args=(), kwargs={}, retval=None, state="SUCCESS"
        )
        on_task_failure(
            sender, task_id="safe-1", exception=Exception("boom"),
            args=(), kwargs={}, traceback="tb", einfo=None
        )

    def test_full_lifecycle_discovery(self, mock_redis_tracker):
        """Simulate full discovery lifecycle: prerun -> progress -> postrun."""
        sender = MagicMock()
        sender.name = "src.tasks.pipeline.discovery_pipeline"

        # Task starts
        on_task_prerun(sender, task_id="life-1", task=sender, args=(), kwargs={})
        assert JobTracker.is_running(JobType.DISCOVERY)

        # Progress updates
        JobTracker.update_progress_sync(JobType.DISCOVERY, current=3, total=10)
        status = JobTracker.get_status(JobType.DISCOVERY)
        assert status["progress"]["percent"] == 30.0

        # Task completes
        on_task_postrun(
            sender, task_id="life-1", task=sender,
            args=(), kwargs={}, retval={"found": 10}, state="SUCCESS"
        )
        status = JobTracker.get_status(JobType.DISCOVERY)
        assert status["status"] == "completed"

    def test_full_lifecycle_failure(self, mock_redis_tracker):
        """Simulate full failure lifecycle: prerun -> failure signal."""
        sender = MagicMock()
        sender.name = "src.tasks.pipeline.research_pipeline"

        on_task_prerun(sender, task_id="life-2", task=sender, args=(), kwargs={})
        assert JobTracker.is_running(JobType.RESEARCH)

        on_task_failure(
            sender, task_id="life-2", exception=ValueError("Invalid data"),
            args=(), kwargs={}, traceback="tb", einfo=None
        )
        status = JobTracker.get_status(JobType.RESEARCH)
        assert status["status"] == "failed"
        assert "Invalid data" in status["error"]
