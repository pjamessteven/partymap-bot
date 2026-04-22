"""API routes for Goabase sync operations."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.dashboard.settings_router import get_setting_value, update_setting
from src.tasks.goabase_tasks import (
    get_goabase_sync_status,
    goabase_sync_stop_task,
    goabase_sync_task,
)

router = APIRouter(prefix="/goabase", tags=["goabase"])


@router.post("/sync/start")
async def start_goabase_sync(
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger Goabase sync.
    
    Returns immediately with task ID. Check status with /sync/status endpoint.
    """
    # Check if already running
    status = await get_goabase_sync_status()
    if status["is_running"]:
        raise HTTPException(
            status_code=409,
            detail="Goabase sync is already running"
        )

    # Trigger Celery task
    task = goabase_sync_task.delay()

    return {
        "status": "started",
        "task_id": task.id,
        "message": "Goabase sync started. Check /sync/status for progress."
    }


@router.post("/sync/stop")
async def stop_goabase_sync():
    """
    Request Goabase sync to stop gracefully.
    
    Sends stop signal to running sync. May take a few seconds to complete current item.
    """
    result = goabase_sync_stop_task.delay()
    return {
        "status": "stop_requested",
        "task_id": result.id,
        "message": "Stop signal sent to Goabase sync"
    }


@router.get("/sync/status")
async def goabase_sync_status():
    """
    Get current Goabase sync status and progress.
    
    Returns:
    - is_running: Whether sync is currently active
    - progress_percentage: Completion percentage (0-100)
    - counts: new, update, unchanged, error counts
    - current_operation: What the sync is currently doing
    """
    return await get_goabase_sync_status()


@router.get("/settings")
async def get_goabase_settings(
    db: AsyncSession = Depends(get_db),
):
    """
    Get all Goabase sync settings.
    """
    settings_keys = [
        "auto_goabase_sync_enabled",
        "goabase_sync_frequency",
        "goabase_sync_day",
        "goabase_sync_hour",
    ]

    settings = {}
    for key in settings_keys:
        value = await get_setting_value(db, key)
        settings[key] = value

    return settings


@router.put("/settings")
async def update_goabase_settings(
    settings: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Update Goabase sync settings.

    Valid settings:
    - auto_goabase_sync_enabled: bool
    - goabase_sync_frequency: "daily" | "weekly" | "monthly"
    - goabase_sync_day: "monday" | "tuesday" | ... | "sunday"
    - goabase_sync_hour: int (0-23)
    """
    valid_keys = {
        "auto_goabase_sync_enabled": "boolean",
        "goabase_sync_frequency": "string",
        "goabase_sync_day": "string",
        "goabase_sync_hour": "integer",
    }

    # Validate inputs
    for key, value in settings.items():
        if key not in valid_keys:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid setting: {key}. Valid settings: {list(valid_keys.keys())}"
            )

        # Validate frequency
        if key == "goabase_sync_frequency" and value not in ["daily", "weekly", "monthly"]:
            raise HTTPException(
                status_code=400,
                detail="goabase_sync_frequency must be: daily, weekly, or monthly"
            )

        # Validate day
        if key == "goabase_sync_day":
            valid_days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            if value.lower() not in valid_days:
                raise HTTPException(
                    status_code=400,
                    detail=f"goabase_sync_day must be one of: {', '.join(valid_days)}"
                )

        # Validate hour
        if key == "goabase_sync_hour":
            try:
                hour = int(value)
                if not (0 <= hour <= 23):
                    raise ValueError()
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="goabase_sync_hour must be an integer between 0 and 23"
                )

    # Update settings
    from src.core.schemas import SystemSettingUpdate
    for key, value in settings.items():
        update = SystemSettingUpdate(value=value)
        await update_setting(key=key, update=update, db=db)

    return {
        "status": "success",
        "message": "Goabase settings updated",
        "settings": settings
    }
