"""Job activity logging service with DB persistence."""

from datetime import datetime, timedelta
from src.utils.utc_now import utc_now
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import JobActivity
from src.core.database import AsyncSessionLocal


class JobActivityLogger:
    """Log job lifecycle events to database with 90-day retention."""

    @classmethod
    async def log_activity(
        cls,
        job_type: str,
        activity_type: str,
        message: str,
        details: Optional[dict] = None,
        festival_id: Optional[UUID] = None,
        task_id: Optional[str] = None,
    ) -> JobActivity:
        """Log a job activity event."""
        async with AsyncSessionLocal() as db:
            activity = JobActivity(
                job_type=job_type,
                activity_type=activity_type,
                message=message,
                details=details,
                festival_id=festival_id,
                task_id=task_id,
            )
            db.add(activity)
            await db.commit()
            return activity

    @classmethod
    async def log_job_started(
        cls,
        job_type: str,
        task_id: str,
        total_items: Optional[int] = None,
    ) -> JobActivity:
        """Log job started event."""
        return await cls.log_activity(
            job_type=job_type,
            activity_type="started",
            message=f"{job_type} job started",
            details={"total_items": total_items} if total_items else {},
            task_id=task_id,
        )

    @classmethod
    async def log_job_progress(
        cls,
        job_type: str,
        current: int,
        total: int,
        festival_id: Optional[UUID] = None,
        festival_name: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> JobActivity:
        """Log job progress update."""
        message = f"Processing {current}/{total}"
        if festival_name:
            message = f"Processing {festival_name} ({current}/{total})"

        return await cls.log_activity(
            job_type=job_type,
            activity_type="progress",
            message=message,
            details={
                "current": current,
                "total": total,
                "percent": round((current / total) * 100, 1) if total > 0 else 0,
                "festival_name": festival_name,
            },
            festival_id=festival_id,
            task_id=task_id,
        )

    @classmethod
    async def log_festival_started(
        cls,
        job_type: str,
        festival_id: UUID,
        festival_name: str,
        task_id: Optional[str] = None,
    ) -> JobActivity:
        """Log when processing starts on a specific festival."""
        return await cls.log_activity(
            job_type=job_type,
            activity_type="festival_started",
            message=f"Started processing {festival_name}",
            details={"festival_name": festival_name},
            festival_id=festival_id,
            task_id=task_id,
        )

    @classmethod
    async def log_festival_completed(
        cls,
        job_type: str,
        festival_id: UUID,
        festival_name: str,
        result: str = "success",
        task_id: Optional[str] = None,
    ) -> JobActivity:
        """Log when processing completes on a specific festival."""
        return await cls.log_activity(
            job_type=job_type,
            activity_type="festival_completed",
            message=f"Completed processing {festival_name}",
            details={"festival_name": festival_name, "result": result},
            festival_id=festival_id,
            task_id=task_id,
        )

    @classmethod
    async def log_job_completed(
        cls,
        job_type: str,
        processed: int,
        failed: int = 0,
        task_id: Optional[str] = None,
    ) -> JobActivity:
        """Log job completed event."""
        message = f"{job_type} job completed - {processed} processed"
        if failed > 0:
            message += f", {failed} failed"

        return await cls.log_activity(
            job_type=job_type,
            activity_type="completed",
            message=message,
            details={"processed": processed, "failed": failed},
            task_id=task_id,
        )

    @classmethod
    async def log_job_failed(
        cls,
        job_type: str,
        error: str,
        task_id: Optional[str] = None,
    ) -> JobActivity:
        """Log job failed event."""
        return await cls.log_activity(
            job_type=job_type,
            activity_type="failed",
            message=f"{job_type} job failed: {error}",
            details={"error": error},
            task_id=task_id,
        )

    @classmethod
    async def log_job_stopped(
        cls,
        job_type: str,
        processed: int = 0,
        task_id: Optional[str] = None,
    ) -> JobActivity:
        """Log job stopped event."""
        return await cls.log_activity(
            job_type=job_type,
            activity_type="stopped",
            message=f"{job_type} job stopped after processing {processed} items",
            details={"processed": processed},
            task_id=task_id,
        )

    @classmethod
    async def get_recent_activity(
        cls,
        job_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[JobActivity]:
        """Get recent job activity."""
        async with AsyncSessionLocal() as db:
            query = select(JobActivity).order_by(JobActivity.created_at.desc())

            if job_type:
                query = query.where(JobActivity.job_type == job_type)

            query = query.limit(limit).offset(offset)
            result = await db.execute(query)
            return result.scalars().all()

    @classmethod
    async def get_activity_for_job(
        cls,
        job_type: str,
        task_id: str,
        limit: int = 100,
    ) -> List[JobActivity]:
        """Get all activity for a specific job run."""
        async with AsyncSessionLocal() as db:
            query = (
                select(JobActivity)
                .where(JobActivity.job_type == job_type)
                .where(JobActivity.task_id == task_id)
                .order_by(JobActivity.created_at.desc())
                .limit(limit)
            )
            result = await db.execute(query)
            return result.scalars().all()

    @classmethod
    async def cleanup_old_activity(cls, days: int = 90) -> int:
        """Delete activity older than specified days."""
        cutoff = utc_now() - timedelta(days=days)
        async with AsyncSessionLocal() as db:
            query = delete(JobActivity).where(JobActivity.created_at < cutoff)
            result = await db.execute(query)
            await db.commit()
            return result.rowcount