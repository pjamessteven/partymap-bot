"""Job status tracking for the dashboard."""

import json
import logging
from enum import Enum
from typing import Dict, List, Optional

from src.core.database import get_async_redis_client, get_redis_client
from src.core.job_activity import JobActivityLogger
from src.utils.utc_now import utc_now

logger = logging.getLogger(__name__)

# Import Celery app for task inspection (module-level for testability)
_celery_app = None


def _get_celery_app():
    """Lazy import of Celery app to avoid circular imports at module load."""
    global _celery_app
    if _celery_app is None:
        from src.tasks.celery_app import celery_app
        _celery_app = celery_app
    return _celery_app


class JobType(str, Enum):
    """Types of jobs that can be tracked."""

    GOABASE_SYNC = "goabase_sync"
    DISCOVERY = "discovery"
    RESEARCH = "research"
    SYNC = "sync"
    REFRESH = "refresh"


class JobStatus(str, Enum):
    """Job status states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class JobTracker:
    """Track job status using Redis with DB persistence."""

    KEY_PREFIX = "partymap_bot:job:"
    LOCK_PREFIX = "partymap_bot:job_lock:"

    @classmethod
    def _key(cls, job_type: JobType) -> str:
        return f"{cls.KEY_PREFIX}{job_type.value}"

    @classmethod
    def _lock_key(cls, job_type: JobType) -> str:
        return f"{cls.LOCK_PREFIX}{job_type.value}"

    @classmethod
    def _build_status_data(
        cls,
        task_id: str,
        metadata: Optional[Dict] = None,
        total_items: Optional[int] = None,
    ) -> dict:
        """Build the standard job status payload."""
        return {
            "status": JobStatus.RUNNING.value,
            "task_id": task_id,
            "started_at": utc_now().isoformat(),
            "metadata": metadata or {},
            "progress": {
                "current": 0,
                "total": total_items or 0,
                "percent": 0,
            },
            "currently_processing": [],
        }

    # ─────────────────────────────────────────────
    # Async methods (used by API endpoints)
    # ─────────────────────────────────────────────

    @classmethod
    async def try_start_job(
        cls,
        job_type: JobType,
        task_id: str,
        metadata: Optional[Dict] = None,
        total_items: Optional[int] = None,
    ) -> bool:
        """Atomically start a job if not already running.

        Uses a Redis lock key with NX to prevent race conditions between
        concurrent start requests.

        Returns:
            True if the job was started, False if it was already running.
        """
        redis = get_async_redis_client()
        lock_key = cls._lock_key(job_type)

        # Acquire lock atomically (expires after 1 hour as safety net)
        acquired = await redis.set(lock_key, task_id, nx=True, ex=3600)
        if not acquired:
            logger.warning(
                f"Job {job_type.value} already running (lock held by {await redis.get(lock_key)})"
            )
            return False

        data = cls._build_status_data(task_id, metadata, total_items)
        await redis.set(cls._key(job_type), json.dumps(data))
        logger.info(f"Job {job_type.value} started: {task_id}")

        await JobActivityLogger.log_job_started(
            job_type=job_type.value,
            task_id=task_id,
            total_items=total_items,
        )
        return True

    @classmethod
    async def start_job(
        cls,
        job_type: JobType,
        task_id: str,
        metadata: Optional[Dict] = None,
        total_items: Optional[int] = None,
    ) -> None:
        """Mark a job as started (non-atomic; prefer try_start_job)."""
        data = cls._build_status_data(task_id, metadata, total_items)
        redis = get_async_redis_client()
        await redis.set(cls._key(job_type), json.dumps(data))
        logger.info(f"Job {job_type.value} started: {task_id}")

        await JobActivityLogger.log_job_started(
            job_type=job_type.value,
            task_id=task_id,
            total_items=total_items,
        )

    @classmethod
    async def update_progress(
        cls,
        job_type: JobType,
        current: int,
        total: int,
        festival_id: Optional[str] = None,
        festival_name: Optional[str] = None,
    ) -> None:
        """Update job progress."""
        key = cls._key(job_type)
        redis = get_async_redis_client()
        existing = await redis.get(key)
        if existing:
            data = json.loads(existing)
            data["progress"] = {
                "current": current,
                "total": total,
                "percent": round((current / total) * 100, 1) if total > 0 else 0,
            }

            processing = data.get("currently_processing", [])
            if festival_id and festival_id not in [p.get("id") for p in processing]:
                processing.append({
                    "id": festival_id,
                    "name": festival_name or "Unknown",
                    "started_at": utc_now().isoformat(),
                })
                data["currently_processing"] = processing

            await redis.set(key, json.dumps(data))

    @classmethod
    async def mark_festival_complete(
        cls,
        job_type: JobType,
        festival_id: str,
    ) -> None:
        """Mark a festival as completed and remove from processing list."""
        key = cls._key(job_type)
        redis = get_async_redis_client()
        existing = await redis.get(key)
        if existing:
            data = json.loads(existing)
            processing = data.get("currently_processing", [])
            data["currently_processing"] = [
                p for p in processing if p.get("id") != festival_id
            ]
            await redis.set(key, json.dumps(data))

    @classmethod
    async def complete_job(
        cls,
        job_type: JobType,
        result: Optional[Dict] = None,
    ) -> None:
        """Mark a job as completed."""
        key = cls._key(job_type)
        redis = get_async_redis_client()
        existing = await redis.get(key)
        if existing:
            data = json.loads(existing)
            data["status"] = JobStatus.COMPLETED.value
            data["completed_at"] = utc_now().isoformat()
            data["result"] = result or {}
            data["currently_processing"] = []
            await redis.set(key, json.dumps(data))
            logger.info(f"Job {job_type.value} completed")

            await JobActivityLogger.log_job_completed(
                job_type=job_type.value,
                task_id=data.get("task_id"),
                processed=result.get("processed", 0) if result else 0,
                failed=result.get("failed", 0) if result else 0,
            )

        # Release lock regardless of whether status existed
        await redis.delete(cls._lock_key(job_type))

    @classmethod
    async def fail_job(
        cls,
        job_type: JobType,
        error: str,
    ) -> None:
        """Mark a job as failed."""
        key = cls._key(job_type)
        redis = get_async_redis_client()
        existing = await redis.get(key)
        if existing:
            data = json.loads(existing)
            data["status"] = JobStatus.FAILED.value
            data["failed_at"] = utc_now().isoformat()
            data["error"] = error
            await redis.set(key, json.dumps(data))
            logger.info(f"Job {job_type.value} failed: {error}")

            await JobActivityLogger.log_job_failed(
                job_type=job_type.value,
                task_id=data.get("task_id"),
                error=error,
            )

        # Release lock regardless of whether status existed
        await redis.delete(cls._lock_key(job_type))

    @classmethod
    async def stop_job(cls, job_type: JobType) -> bool:
        """Mark a job as stopped (for stopping running jobs)."""
        key = cls._key(job_type)
        redis = get_async_redis_client()
        existing = await redis.get(key)
        stopped = False
        if existing:
            data = json.loads(existing)
            if data.get("status") == JobStatus.RUNNING.value:
                data["status"] = JobStatus.STOPPED.value
                data["stopped_at"] = utc_now().isoformat()
                data["currently_processing"] = []
                await redis.set(key, json.dumps(data))
                logger.info(f"Job {job_type.value} stopped")

                await JobActivityLogger.log_job_stopped(
                    job_type=job_type.value,
                    task_id=data.get("task_id"),
                    processed=data.get("progress", {}).get("current", 0),
                )
                stopped = True

        # Always release the lock so the job can be restarted
        await redis.delete(cls._lock_key(job_type))
        return stopped

    # ─────────────────────────────────────────────
    # Sync methods (used by Celery signal handlers)
    # ─────────────────────────────────────────────

    @classmethod
    def try_start_job_sync(
        cls,
        job_type: JobType,
        task_id: str,
        metadata: Optional[Dict] = None,
        total_items: Optional[int] = None,
    ) -> bool:
        """Sync version: atomically start a job if not already running."""
        redis = get_redis_client()
        lock_key = cls._lock_key(job_type)

        # Acquire lock atomically (expires after 1 hour as safety net)
        acquired = redis.set(lock_key, task_id, nx=True, ex=3600)
        if not acquired:
            logger.warning(
                f"Job {job_type.value} already running (sync, lock held by {redis.get(lock_key)})"
            )
            return False

        data = cls._build_status_data(task_id, metadata, total_items)
        redis.set(cls._key(job_type), json.dumps(data))
        logger.info(f"Job {job_type.value} started (sync): {task_id}")
        return True

    @classmethod
    def start_job_sync(
        cls,
        job_type: JobType,
        task_id: str,
        metadata: Optional[Dict] = None,
        total_items: Optional[int] = None,
    ) -> None:
        """Sync version: mark a job as started (non-atomic; prefer try_start_job_sync)."""
        data = cls._build_status_data(task_id, metadata, total_items)
        get_redis_client().set(cls._key(job_type), json.dumps(data))
        logger.info(f"Job {job_type.value} started (sync): {task_id}")

    @classmethod
    def update_progress_sync(
        cls,
        job_type: JobType,
        current: int,
        total: int,
        festival_id: Optional[str] = None,
        festival_name: Optional[str] = None,
    ) -> None:
        """Sync version: update job progress."""
        key = cls._key(job_type)
        existing = get_redis_client().get(key)
        if existing:
            data = json.loads(existing)
            data["progress"] = {
                "current": current,
                "total": total,
                "percent": round((current / total) * 100, 1) if total > 0 else 0,
            }

            processing = data.get("currently_processing", [])
            if festival_id and festival_id not in [p.get("id") for p in processing]:
                processing.append({
                    "id": festival_id,
                    "name": festival_name or "Unknown",
                    "started_at": utc_now().isoformat(),
                })
                data["currently_processing"] = processing

            get_redis_client().set(key, json.dumps(data))

    @classmethod
    def complete_job_sync(
        cls,
        job_type: JobType,
        result: Optional[Dict] = None,
    ) -> None:
        """Sync version: mark a job as completed."""
        redis = get_redis_client()
        key = cls._key(job_type)
        existing = redis.get(key)
        if existing:
            data = json.loads(existing)
            data["status"] = JobStatus.COMPLETED.value
            data["completed_at"] = utc_now().isoformat()
            data["result"] = result or {}
            data["currently_processing"] = []
            redis.set(key, json.dumps(data))
            logger.info(f"Job {job_type.value} completed (sync)")

        # Release lock regardless of whether status existed
        redis.delete(cls._lock_key(job_type))

    @classmethod
    def fail_job_sync(
        cls,
        job_type: JobType,
        error: str,
    ) -> None:
        """Sync version: mark a job as failed."""
        redis = get_redis_client()
        key = cls._key(job_type)
        existing = redis.get(key)
        if existing:
            data = json.loads(existing)
            data["status"] = JobStatus.FAILED.value
            data["failed_at"] = utc_now().isoformat()
            data["error"] = error
            redis.set(key, json.dumps(data))
            logger.info(f"Job {job_type.value} failed (sync): {error}")

        # Release lock regardless of whether status existed
        redis.delete(cls._lock_key(job_type))

    @classmethod
    def stop_job_sync(cls, job_type: JobType) -> bool:
        """Sync version: mark a job as stopped."""
        redis = get_redis_client()
        key = cls._key(job_type)
        existing = redis.get(key)
        stopped = False
        if existing:
            data = json.loads(existing)
            if data.get("status") == JobStatus.RUNNING.value:
                data["status"] = JobStatus.STOPPED.value
                data["stopped_at"] = utc_now().isoformat()
                data["currently_processing"] = []
                redis.set(key, json.dumps(data))
                logger.info(f"Job {job_type.value} stopped (sync)")
                stopped = True

        # Always release the lock so the job can be restarted
        redis.delete(cls._lock_key(job_type))
        return stopped

    @classmethod
    def mark_festival_complete_sync(
        cls,
        job_type: JobType,
        festival_id: str,
    ) -> None:
        """Sync version: mark a festival as completed."""
        key = cls._key(job_type)
        existing = get_redis_client().get(key)
        if existing:
            data = json.loads(existing)
            processing = data.get("currently_processing", [])
            data["currently_processing"] = [
                p for p in processing if p.get("id") != festival_id
            ]
            get_redis_client().set(key, json.dumps(data))

    # ─────────────────────────────────────────────
    # Celery integration
    # ─────────────────────────────────────────────

    @classmethod
    def inspect_and_sync_status(cls, job_type: JobType, _celery_app=None) -> Optional[Dict]:
        """
        Get job status, syncing Redis cache with Celery ground truth.

        If Celery reports a task as ready but Redis shows RUNNING,
        auto-correct Redis to COMPLETED or FAILED.

        Args:
            job_type: The job type to inspect.
            _celery_app: Optional Celery app override for testing.
        """
        celery_app = _celery_app or _get_celery_app()

        redis_status = cls.get_status(job_type)
        if not redis_status:
            return None

        task_id = redis_status.get("task_id")
        if not task_id:
            return redis_status

        try:
            result = celery_app.AsyncResult(task_id)

            # DEBUG
            import os
            if os.environ.get("DEBUG_INSPECT"):
                print(f"DEBUG inspect: celery_app type={type(celery_app).__name__}, task_id={task_id}, result={result}, ready={result.ready()}, successful={result.successful()}, state={result.state}")

            if result.ready():
                # Celery says task is done, but what does Redis say?
                redis_state = redis_status.get("status")

                if redis_state == JobStatus.RUNNING.value:
                    if result.successful():
                        redis_status["status"] = JobStatus.COMPLETED.value
                        redis_status["completed_at"] = utc_now().isoformat()
                        redis_status["currently_processing"] = []
                        logger.info(
                            f"Auto-corrected {job_type.value} from RUNNING to COMPLETED "
                            f"(Celery task {task_id} successful)"
                        )
                    else:
                        # Failed or retried too many times
                        exc = result.result
                        error_msg = str(exc) if exc else "Task failed"
                        redis_status["status"] = JobStatus.FAILED.value
                        redis_status["failed_at"] = utc_now().isoformat()
                        redis_status["error"] = error_msg
                        logger.info(
                            f"Auto-corrected {job_type.value} from RUNNING to FAILED "
                            f"(Celery task {task_id} failed: {error_msg})"
                        )

                    # Persist the corrected state back to Redis
                    get_redis_client().set(cls._key(job_type), json.dumps(redis_status))

            elif result.state == "STARTED" and redis_status.get("status") != JobStatus.RUNNING.value:
                # Celery says started but Redis doesn't show running - fix it
                redis_status["status"] = JobStatus.RUNNING.value
                redis_status["started_at"] = redis_status.get("started_at") or utc_now().isoformat()
                get_redis_client().set(cls._key(job_type), json.dumps(redis_status))

        except Exception as e:
            logger.warning(f"Could not inspect Celery task {task_id}: {e}")

        return redis_status

    @classmethod
    def revoke_task(cls, job_type: JobType) -> bool:
        """Revoke the Celery task associated with a job."""
        celery_app = _get_celery_app()

        status = cls.get_status(job_type)
        if not status:
            return False

        task_id = status.get("task_id")
        if not task_id:
            return False

        try:
            celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
            logger.info(f"Revoked Celery task {task_id} for {job_type.value}")
            return True
        except Exception as e:
            logger.error(f"Failed to revoke task {task_id}: {e}")
            return False

    # ─────────────────────────────────────────────
    # Read-only methods
    # ─────────────────────────────────────────────

    @classmethod
    def get_status(cls, job_type: JobType) -> Optional[Dict]:
        """Get current job status."""
        key = cls._key(job_type)
        data = get_redis_client().get(key)
        if data:
            return json.loads(data)
        return None

    @classmethod
    def get_all_status(cls) -> Dict[str, Optional[Dict]]:
        """Get status of all job types."""
        return {job_type.value: cls.get_status(job_type) for job_type in JobType}

    @classmethod
    def get_all_status_synced(cls) -> Dict[str, Optional[Dict]]:
        """Get status of all job types, synced with Celery ground truth."""
        return {
            job_type.value: cls.inspect_and_sync_status(job_type)
            for job_type in JobType
        }

    @classmethod
    def is_running(cls, job_type: JobType) -> bool:
        """Check if a job is currently running."""
        status = cls.get_status(job_type)
        return status is not None and status.get("status") == JobStatus.RUNNING.value

    @classmethod
    def clear_job(cls, job_type: JobType) -> None:
        """Clear job status and lock."""
        redis = get_redis_client()
        redis.delete(cls._key(job_type))
        redis.delete(cls._lock_key(job_type))

    @classmethod
    def clear_all_jobs(cls) -> None:
        """Clear all job statuses and locks."""
        redis = get_redis_client()
        for job_type in JobType:
            redis.delete(cls._key(job_type))
            redis.delete(cls._lock_key(job_type))

    @classmethod
    def get_processing_festivals(cls, job_type: JobType) -> List[Dict]:
        """Get list of festivals currently being processed."""
        status = cls.get_status(job_type)
        if status:
            return status.get("currently_processing", [])
        return []
