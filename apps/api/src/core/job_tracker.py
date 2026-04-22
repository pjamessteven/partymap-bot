"""Job status tracking for the dashboard."""

import json
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, List

from src.core.database import redis_client
from src.core.job_activity import JobActivityLogger

logger = logging.getLogger(__name__)


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

    @classmethod
    def _key(cls, job_type: JobType) -> str:
        return f"{cls.KEY_PREFIX}{job_type.value}"

    @classmethod
    async def start_job(
        cls,
        job_type: JobType,
        task_id: str,
        metadata: Optional[Dict] = None,
        total_items: Optional[int] = None,
    ) -> None:
        """Mark a job as started."""
        data = {
            "status": JobStatus.RUNNING.value,
            "task_id": task_id,
            "started_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
            "progress": {
                "current": 0,
                "total": total_items or 0,
                "percent": 0,
            },
            "currently_processing": [],  # List of festival IDs being processed
        }
        redis_client.set(cls._key(job_type), json.dumps(data))
        logger.info(f"Job {job_type.value} started: {task_id}")

        # Log to database
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
        existing = redis_client.get(key)
        if existing:
            data = json.loads(existing)
            data["progress"] = {
                "current": current,
                "total": total,
                "percent": round((current / total) * 100, 1) if total > 0 else 0,
            }

            # Track currently processing festivals
            processing = data.get("currently_processing", [])
            if festival_id and festival_id not in processing:
                processing.append({
                    "id": festival_id,
                    "name": festival_name or "Unknown",
                    "started_at": datetime.utcnow().isoformat(),
                })
                data["currently_processing"] = processing

            redis_client.set(key, json.dumps(data))

    @classmethod
    async def mark_festival_complete(
        cls,
        job_type: JobType,
        festival_id: str,
    ) -> None:
        """Mark a festival as completed and remove from processing list."""
        key = cls._key(job_type)
        existing = redis_client.get(key)
        if existing:
            data = json.loads(existing)
            processing = data.get("currently_processing", [])
            data["currently_processing"] = [
                p for p in processing if p.get("id") != festival_id
            ]
            redis_client.set(key, json.dumps(data))

    @classmethod
    async def complete_job(
        cls,
        job_type: JobType,
        result: Optional[Dict] = None,
    ) -> None:
        """Mark a job as completed."""
        key = cls._key(job_type)
        existing = redis_client.get(key)
        if existing:
            data = json.loads(existing)
            data["status"] = JobStatus.COMPLETED.value
            data["completed_at"] = datetime.utcnow().isoformat()
            data["result"] = result or {}
            data["currently_processing"] = []
            redis_client.set(key, json.dumps(data))
            logger.info(f"Job {job_type.value} completed")

            # Log to database
            await JobActivityLogger.log_job_completed(
                job_type=job_type.value,
                task_id=data.get("task_id"),
                processed=result.get("processed", 0) if result else 0,
                failed=result.get("failed", 0) if result else 0,
            )

    @classmethod
    async def fail_job(
        cls,
        job_type: JobType,
        error: str,
    ) -> None:
        """Mark a job as failed."""
        key = cls._key(job_type)
        existing = redis_client.get(key)
        if existing:
            data = json.loads(existing)
            data["status"] = JobStatus.FAILED.value
            data["failed_at"] = datetime.utcnow().isoformat()
            data["error"] = error
            redis_client.set(key, json.dumps(data))
            logger.info(f"Job {job_type.value} failed: {error}")

            # Log to database
            await JobActivityLogger.log_job_failed(
                job_type=job_type.value,
                task_id=data.get("task_id"),
                error=error,
            )

    @classmethod
    async def stop_job(cls, job_type: JobType) -> bool:
        """Mark a job as stopped (for stopping running jobs)."""
        key = cls._key(job_type)
        existing = redis_client.get(key)
        if existing:
            data = json.loads(existing)
            if data.get("status") == JobStatus.RUNNING.value:
                data["status"] = JobStatus.STOPPED.value
                data["stopped_at"] = datetime.utcnow().isoformat()
                data["currently_processing"] = []
                redis_client.set(key, json.dumps(data))
                logger.info(f"Job {job_type.value} stopped")

                # Log to database
                await JobActivityLogger.log_job_stopped(
                    job_type=job_type.value,
                    task_id=data.get("task_id"),
                    processed=data.get("progress", {}).get("current", 0),
                )
                return True
        return False

    @classmethod
    def get_status(cls, job_type: JobType) -> Optional[Dict]:
        """Get current job status."""
        key = cls._key(job_type)
        data = redis_client.get(key)
        if data:
            return json.loads(data)
        return None

    @classmethod
    def get_all_status(cls) -> Dict[str, Optional[Dict]]:
        """Get status of all job types."""
        return {job_type.value: cls.get_status(job_type) for job_type in JobType}

    @classmethod
    def is_running(cls, job_type: JobType) -> bool:
        """Check if a job is currently running."""
        status = cls.get_status(job_type)
        return status is not None and status.get("status") == JobStatus.RUNNING.value

    @classmethod
    def clear_job(cls, job_type: JobType) -> None:
        """Clear job status."""
        redis_client.delete(cls._key(job_type))

    @classmethod
    def clear_all_jobs(cls) -> None:
        """Clear all job statuses."""
        for job_type in JobType:
            redis_client.delete(cls._key(job_type))

    @classmethod
    def get_processing_festivals(cls, job_type: JobType) -> List[Dict]:
        """Get list of festivals currently being processed."""
        status = cls.get_status(job_type)
        if status:
            return status.get("currently_processing", [])
        return []
