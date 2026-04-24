"""Settings API routes for system configuration and scheduling."""

import json
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.models import PipelineSchedule, SystemSettings
from src.core.settings_utils import get_setting_value, update_setting
from src.tasks.pipeline import discovery_pipeline
from src.utils.utc_now import utc_now

router = APIRouter()


def _parse_setting_value(setting: SystemSettings) -> Any:
    """Parse setting value based on its type."""
    if setting.value_type == "boolean":
        return setting.value.lower() == "true"
    elif setting.value_type == "integer":
        return int(setting.value)
    elif setting.value_type == "float":
        return float(setting.value)
    elif setting.value_type == "json":
        return json.loads(setting.value)
    return setting.value


def _serialize_setting_value(value: Any, value_type: str) -> str:
    """Serialize value to string for storage."""
    if value_type == "json":
        return json.dumps(value)
    return str(value)


def _setting_to_dict(setting: SystemSettings) -> dict:
    """Convert SystemSettings to response dict."""
    return {
        "id": str(setting.id),
        "key": setting.key,
        "value": _parse_setting_value(setting),
        "value_type": setting.value_type,
        "description": setting.description,
        "editable": setting.editable,
        "category": setting.category,
        "created_at": setting.created_at.isoformat() if setting.created_at else None,
        "updated_at": setting.updated_at.isoformat() if setting.updated_at else None,
    }


@router.get("/settings")
async def get_settings(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List system settings."""
    query = select(SystemSettings)

    if category:
        query = query.where(SystemSettings.category == category)

    query = query.order_by(SystemSettings.category, SystemSettings.key)

    result = await db.execute(query)
    settings = result.scalars().all()

    settings_list = [_setting_to_dict(s) for s in settings]

    # Group by category
    by_category = {}
    for s in settings_list:
        cat = s["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(s)

    return {
        "settings": settings_list,
        "by_category": by_category,
    }


# Schedule endpoints (MUST be defined before /settings/{key} to avoid shadowing)


@router.get("/settings/schedules")
async def get_schedules(db: AsyncSession = Depends(get_db)):
    """List all pipeline schedules."""
    result = await db.execute(select(PipelineSchedule).order_by(PipelineSchedule.task_type))
    schedules = result.scalars().all()

    return [
        {
            "id": str(s.id),
            "task_type": s.task_type,
            "enabled": s.enabled,
            "hour": s.hour,
            "minute": s.minute,
            "day_of_week": s.day_of_week,
            "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
            "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
            "run_count": s.run_count,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in schedules
    ]


@router.get("/settings/schedules/{task_type}")
async def get_schedule(task_type: str, db: AsyncSession = Depends(get_db)):
    """Get a specific schedule."""
    result = await db.execute(
        select(PipelineSchedule).where(PipelineSchedule.task_type == task_type)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    return {
        "id": str(schedule.id),
        "task_type": schedule.task_type,
        "enabled": schedule.enabled,
        "hour": schedule.hour,
        "minute": schedule.minute,
        "day_of_week": schedule.day_of_week,
        "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
        "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
        "run_count": schedule.run_count,
        "created_at": schedule.created_at.isoformat() if schedule.created_at else None,
        "updated_at": schedule.updated_at.isoformat() if schedule.updated_at else None,
    }


@router.put("/settings/schedules/{task_type}")
async def update_schedule(
    task_type: str,
    updates: dict,
    db: AsyncSession = Depends(get_db),
):
    """Update a schedule configuration."""
    result = await db.execute(
        select(PipelineSchedule).where(PipelineSchedule.task_type == task_type)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if "enabled" in updates:
        schedule.enabled = updates["enabled"]
    if "hour" in updates:
        if not (0 <= updates["hour"] <= 23):
            raise HTTPException(status_code=400, detail="Hour must be between 0 and 23")
        schedule.hour = updates["hour"]
    if "minute" in updates:
        if not (0 <= updates["minute"] <= 59):
            raise HTTPException(status_code=400, detail="Minute must be between 0 and 59")
        schedule.minute = updates["minute"]
    if "day_of_week" in updates:
        schedule.day_of_week = updates["day_of_week"]

    await db.commit()
    await db.refresh(schedule)

    return {
        "id": str(schedule.id),
        "task_type": schedule.task_type,
        "enabled": schedule.enabled,
        "hour": schedule.hour,
        "minute": schedule.minute,
        "day_of_week": schedule.day_of_week,
        "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
        "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
        "run_count": schedule.run_count,
        "created_at": schedule.created_at.isoformat() if schedule.created_at else None,
        "updated_at": schedule.updated_at.isoformat() if schedule.updated_at else None,
    }


@router.post("/settings/schedules/{task_type}/enable")
async def enable_schedule(task_type: str, db: AsyncSession = Depends(get_db)):
    """Enable a schedule."""
    result = await db.execute(
        select(PipelineSchedule).where(PipelineSchedule.task_type == task_type)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    schedule.enabled = True
    await db.commit()
    await db.refresh(schedule)

    return {
        "id": str(schedule.id),
        "task_type": schedule.task_type,
        "enabled": schedule.enabled,
        "hour": schedule.hour,
        "minute": schedule.minute,
        "day_of_week": schedule.day_of_week,
        "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
        "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
        "run_count": schedule.run_count,
        "created_at": schedule.created_at.isoformat() if schedule.created_at else None,
        "updated_at": schedule.updated_at.isoformat() if schedule.updated_at else None,
    }


@router.post("/settings/schedules/{task_type}/disable")
async def disable_schedule(task_type: str, db: AsyncSession = Depends(get_db)):
    """Disable a schedule."""
    result = await db.execute(
        select(PipelineSchedule).where(PipelineSchedule.task_type == task_type)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    schedule.enabled = False
    await db.commit()
    await db.refresh(schedule)

    return {
        "id": str(schedule.id),
        "task_type": schedule.task_type,
        "enabled": schedule.enabled,
        "hour": schedule.hour,
        "minute": schedule.minute,
        "day_of_week": schedule.day_of_week,
        "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
        "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
        "run_count": schedule.run_count,
        "created_at": schedule.created_at.isoformat() if schedule.created_at else None,
        "updated_at": schedule.updated_at.isoformat() if schedule.updated_at else None,
    }


@router.post("/settings/schedules/apply")
async def apply_schedules(db: AsyncSession = Depends(get_db)):
    """Apply schedule changes (refresh Celery beat)."""
    # In a real implementation, this would restart Celery beat
    # For now, just return success
    result = await db.execute(select(PipelineSchedule).where(PipelineSchedule.enabled == True))
    active = result.scalars().all()

    return {
        "message": "Schedules applied",
        "refreshed_at": utc_now().isoformat(),
        "active_schedules": len(active),
    }


@router.post("/settings/schedules/run-now/{task_type}")
async def run_task_now(task_type: str, db: AsyncSession = Depends(get_db)):
    """Run a scheduled task immediately."""
    result = await db.execute(
        select(PipelineSchedule).where(PipelineSchedule.task_type == task_type)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Update last_run_at
    schedule.last_run_at = utc_now()
    schedule.run_count += 1
    await db.commit()

    # Trigger the appropriate task
    task_id = None
    if task_type == "discovery":
        task = discovery_pipeline.delay()
        task_id = task.id
    # Add more task types as needed

    return {
        "message": f"Task {task_type} triggered",
        "task_type": task_type,
        "task_id": task_id,
    }


# Auto-process endpoints (also before /settings/{key})


@router.get("/settings/auto-process/status")
async def get_auto_process_status(db: AsyncSession = Depends(get_db)):
    """Get auto-process status."""
    enabled = await get_setting_value(db, "auto_process_enabled", default="false")
    return {
        "enabled": enabled.lower() == "true" if isinstance(enabled, str) else bool(enabled),
        "description": "Automatically process discovered festivals through the pipeline",
    }


@router.put("/settings/auto-process/enable")
async def enable_auto_process(db: AsyncSession = Depends(get_db)):
    """Enable auto-processing."""
    setting = await update_setting(db, "auto_process_enabled", "true")
    return {
        "enabled": True,
        "description": "Automatically process discovered festivals through the pipeline",
    }


@router.put("/settings/auto-process/disable")
async def disable_auto_process(db: AsyncSession = Depends(get_db)):
    """Disable auto-processing."""
    setting = await update_setting(db, "auto_process_enabled", "false")
    return {
        "enabled": False,
        "description": "Automatically process discovered festivals through the pipeline",
    }


@router.get("/settings/{key}")
async def get_setting(key: str, db: AsyncSession = Depends(get_db)):
    """Get a single setting by key."""
    result = await db.execute(
        select(SystemSettings).where(SystemSettings.key == key)
    )
    setting = result.scalar_one_or_none()

    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")

    return _setting_to_dict(setting)


@router.put("/settings/{key}")
async def update_setting_endpoint(
    key: str,
    value: dict,
    db: AsyncSession = Depends(get_db),
):
    """Update a setting value."""
    result = await db.execute(
        select(SystemSettings).where(SystemSettings.key == key)
    )
    setting = result.scalar_one_or_none()

    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")

    if not setting.editable:
        raise HTTPException(status_code=403, detail="Setting is not editable")

    raw_value = value.get("value")
    setting.value = _serialize_setting_value(raw_value, setting.value_type)
    await db.commit()
    await db.refresh(setting)

    return _setting_to_dict(setting)




# Auto-process endpoints


@router.get("/settings/auto-process/status")
async def get_auto_process_status(db: AsyncSession = Depends(get_db)):
    """Get auto-process status."""
    enabled = await get_setting_value(db, "auto_process_enabled", default="false")
    return {
        "enabled": enabled.lower() == "true" if isinstance(enabled, str) else bool(enabled),
        "description": "Automatically process discovered festivals through the pipeline",
    }


@router.put("/settings/auto-process/enable")
async def enable_auto_process(db: AsyncSession = Depends(get_db)):
    """Enable auto-processing."""
    setting = await update_setting(db, "auto_process_enabled", "true")
    return {
        "enabled": True,
        "description": "Automatically process discovered festivals through the pipeline",
    }


@router.put("/settings/auto-process/disable")
async def disable_auto_process(db: AsyncSession = Depends(get_db)):
    """Disable auto-processing."""
    setting = await update_setting(db, "auto_process_enabled", "false")
    return {
        "enabled": False,
        "description": "Automatically process discovered festivals through the pipeline",
    }
