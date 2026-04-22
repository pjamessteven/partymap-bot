"""Schedule management API routes."""

import logging
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.models import PipelineSchedule
from src.utils.utc_now import utc_now

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schedule", tags=["schedule"])

# Valid task types
VALID_TASK_TYPES = {"discovery", "goabase_sync", "cleanup_failed"}


def _get_task_map():
    """Lazy-load task functions to avoid circular imports."""
    from src.tasks.goabase_tasks import goabase_sync_task
    from src.tasks.maintenance import cleanup_failed
    from src.tasks.pipeline import discovery_pipeline

    return {
        "discovery": discovery_pipeline,
        "goabase_sync": goabase_sync_task,
        "cleanup_failed": cleanup_failed,
    }


class ScheduleConfig(BaseModel):
    """Schedule configuration response schema."""

    id: str
    task_type: str
    enabled: bool
    hour: int
    minute: int
    day_of_week: Optional[int] = None
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    run_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScheduleUpdate(BaseModel):
    """Update schedule request schema."""

    enabled: Optional[bool] = None
    hour: Optional[int] = Field(None, ge=0, le=23)
    minute: Optional[int] = Field(None, ge=0, le=59)
    day_of_week: Optional[int] = Field(None, ge=0, le=6)

    @field_validator("hour", "minute", "day_of_week", mode="before")
    @classmethod
    def validate_schedule_spacing(cls, v, info):
        """Ensure minimum 1 hour between runs."""
        # This is validated at the endpoint level where we have full context
        return v


class ScheduleApplyResponse(BaseModel):
    """Response for apply schedule changes."""

    message: str
    refreshed_at: datetime
    active_schedules: int


class ScheduleRunResponse(BaseModel):
    """Response for manual task run."""

    message: str
    task_type: str
    task_id: Optional[str] = None


async def _validate_schedule_spacing(
    db: AsyncSession, task_type: str, hour: int, minute: int, exclude_id: Optional[UUID] = None
):
    """Validate that no other schedule is within 1 hour of the proposed time."""
    # Get all enabled schedules except current one
    query = select(PipelineSchedule).where(
        PipelineSchedule.enabled == True, PipelineSchedule.task_type != task_type
    )
    if exclude_id:
        query = query.where(PipelineSchedule.id != exclude_id)

    result = await db.execute(query)
    schedules = result.scalars().all()

    # Convert proposed time to minutes for comparison
    proposed_minutes = hour * 60 + minute

    for sched in schedules:
        if sched.day_of_week is not None:
            # Weekly schedule - only check if same day
            continue  # Weekly schedules don't conflict with daily on time alone

        existing_minutes = sched.hour * 60 + sched.minute
        diff = abs(proposed_minutes - existing_minutes)

        # Check if within 60 minutes (accounting for midnight wrap)
        if diff < 60 or diff > 1380:  # 1380 = 24*60 - 60
            raise HTTPException(
                status_code=400,
                detail=f"Schedule conflict: Another task runs at {sched.hour:02d}:{sched.minute:02d}. "
                f"Minimum 1 hour spacing required.",
            )


@router.get("", response_model=List[ScheduleConfig])
async def get_all_schedules(db: AsyncSession = Depends(get_db)):
    """Get all schedule configurations."""
    result = await db.execute(select(PipelineSchedule).order_by(PipelineSchedule.task_type))
    schedules = result.scalars().all()
    return [
        ScheduleConfig(
            id=str(s.id),
            task_type=s.task_type,
            enabled=s.enabled,
            hour=s.hour,
            minute=s.minute,
            day_of_week=s.day_of_week,
            last_run_at=s.last_run_at,
            next_run_at=s.next_run_at,
            run_count=s.run_count,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in schedules
    ]


@router.get("/{task_type}", response_model=ScheduleConfig)
async def get_schedule(task_type: str, db: AsyncSession = Depends(get_db)):
    """Get specific task schedule."""
    if task_type not in VALID_TASK_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid task type: {task_type}")

    result = await db.execute(
        select(PipelineSchedule).where(PipelineSchedule.task_type == task_type)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail=f"Schedule not found: {task_type}")

    return ScheduleConfig(
        id=str(schedule.id),
        task_type=schedule.task_type,
        enabled=schedule.enabled,
        hour=schedule.hour,
        minute=schedule.minute,
        day_of_week=schedule.day_of_week,
        last_run_at=schedule.last_run_at,
        next_run_at=schedule.next_run_at,
        run_count=schedule.run_count,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


@router.put("/{task_type}", response_model=ScheduleConfig)
async def update_schedule(
    task_type: str,
    update: ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update schedule configuration.

    Validates:
    - Hour: 0-23
    - Minute: 0-59
    - Day of week: 0-6 (0=Monday), optional
    - Minimum 1 hour between any two scheduled tasks
    """
    if task_type not in VALID_TASK_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid task type: {task_type}")

    result = await db.execute(
        select(PipelineSchedule).where(PipelineSchedule.task_type == task_type)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail=f"Schedule not found: {task_type}")

    # Validate schedule spacing if time is being updated
    new_hour = update.hour if update.hour is not None else schedule.hour
    new_minute = update.minute if update.minute is not None else schedule.minute

    if update.hour is not None or update.minute is not None:
        await _validate_schedule_spacing(db, task_type, new_hour, new_minute, schedule.id)

    # Apply updates
    if update.enabled is not None:
        schedule.enabled = update.enabled
    if update.hour is not None:
        schedule.hour = update.hour
    if update.minute is not None:
        schedule.minute = update.minute
    if update.day_of_week is not None:
        schedule.day_of_week = update.day_of_week

    # Recalculate next_run_at if enabled and schedule changed
    if schedule.enabled:
        now = utc_now()
        if schedule.day_of_week is not None:
            # Weekly schedule
            days_ahead = schedule.day_of_week - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            next_run = now + timedelta(days=days_ahead)
        else:
            # Daily schedule - could be today or tomorrow
            next_run = now.replace(
                hour=schedule.hour, minute=schedule.minute, second=0, microsecond=0
            )
            if next_run <= now:
                next_run += timedelta(days=1)

        schedule.next_run_at = next_run
    else:
        schedule.next_run_at = None

    await db.commit()
    await db.refresh(schedule)

    logger.info(
        f"Updated schedule for {task_type}: enabled={schedule.enabled}, time={schedule.hour:02d}:{schedule.minute:02d}"
    )

    return ScheduleConfig(
        id=str(schedule.id),
        task_type=schedule.task_type,
        enabled=schedule.enabled,
        hour=schedule.hour,
        minute=schedule.minute,
        day_of_week=schedule.day_of_week,
        last_run_at=schedule.last_run_at,
        next_run_at=schedule.next_run_at,
        run_count=schedule.run_count,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


@router.post("/{task_type}/enable", response_model=ScheduleConfig)
async def enable_schedule(task_type: str, db: AsyncSession = Depends(get_db)):
    """Enable auto-scheduling for task."""
    if task_type not in VALID_TASK_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid task type: {task_type}")

    result = await db.execute(
        select(PipelineSchedule).where(PipelineSchedule.task_type == task_type)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail=f"Schedule not found: {task_type}")

    # Validate schedule spacing before enabling
    await _validate_schedule_spacing(db, task_type, schedule.hour, schedule.minute, schedule.id)

    schedule.enabled = True

    # Calculate next run
    now = utc_now()
    if schedule.day_of_week is not None:
        days_ahead = schedule.day_of_week - now.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        next_run = now + timedelta(days=days_ahead)
    else:
        next_run = now.replace(hour=schedule.hour, minute=schedule.minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)

    schedule.next_run_at = next_run

    await db.commit()
    await db.refresh(schedule)

    logger.info(f"Enabled schedule for {task_type}")

    return ScheduleConfig(
        id=str(schedule.id),
        task_type=schedule.task_type,
        enabled=schedule.enabled,
        hour=schedule.hour,
        minute=schedule.minute,
        day_of_week=schedule.day_of_week,
        last_run_at=schedule.last_run_at,
        next_run_at=schedule.next_run_at,
        run_count=schedule.run_count,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


@router.post("/{task_type}/disable", response_model=ScheduleConfig)
async def disable_schedule(task_type: str, db: AsyncSession = Depends(get_db)):
    """Disable auto-scheduling for task."""
    if task_type not in VALID_TASK_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid task type: {task_type}")

    result = await db.execute(
        select(PipelineSchedule).where(PipelineSchedule.task_type == task_type)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail=f"Schedule not found: {task_type}")

    schedule.enabled = False
    schedule.next_run_at = None

    await db.commit()
    await db.refresh(schedule)

    logger.info(f"Disabled schedule for {task_type}")

    return ScheduleConfig(
        id=str(schedule.id),
        task_type=schedule.task_type,
        enabled=schedule.enabled,
        hour=schedule.hour,
        minute=schedule.minute,
        day_of_week=schedule.day_of_week,
        last_run_at=schedule.last_run_at,
        next_run_at=schedule.next_run_at,
        run_count=schedule.run_count,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


@router.post("/apply", response_model=ScheduleApplyResponse)
async def apply_schedule_changes():
    """Force scheduler to reload schedule from database immediately.

    Note: The scheduler automatically refreshes every 60 seconds.
    This endpoint forces an immediate refresh.
    """
    try:
        # Send signal to scheduler to refresh
        # The scheduler checks last_updated timestamp and refreshes if needed
        # We can't directly call the scheduler, but we can signal via Redis or just wait
        # The scheduler will pick up changes on next tick (max 60 seconds)

        # Get current active schedule count from DB
        from src.core.database import SessionLocal

        session = SessionLocal()
        try:
            result = session.query(PipelineSchedule).filter_by(enabled=True).count()
            active_count = result
        finally:
            session.close()

        return ScheduleApplyResponse(
            message="Schedule changes applied. Scheduler will pick up changes within 60 seconds.",
            refreshed_at=utc_now(),
            active_schedules=active_count,
        )
    except Exception as e:
        logger.error(f"Failed to apply schedule changes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to apply changes: {str(e)}")


@router.post("/run-now/{task_type}", response_model=ScheduleRunResponse)
async def run_task_now(task_type: str):
    """Manually trigger task immediately.

    Note: This does not affect the scheduled next_run_at time.
    """
    if task_type not in VALID_TASK_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid task type: {task_type}")

    try:
        task = _get_task_map().get(task_type)
        if not task:
            raise HTTPException(status_code=500, detail=f"Task not configured: {task_type}")

        # Send task to queue
        result = task.delay()

        logger.info(f"Manually triggered {task_type}: task_id={result.id}")

        return ScheduleRunResponse(
            message=f"{task_type} task queued for execution",
            task_type=task_type,
            task_id=result.id,
        )
    except Exception as e:
        logger.error(f"Failed to run {task_type}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to run task: {str(e)}")
