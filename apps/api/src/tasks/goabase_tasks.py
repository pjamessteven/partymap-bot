"""Celery tasks and API endpoints for Goabase sync."""

import logging
from datetime import datetime
from typing import Dict, Any

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from src.config import get_settings
from src.sources.goabase_sync import GoabaseSync, sync_manager

logger = logging.getLogger(__name__)


@shared_task(bind=True, soft_time_limit=3600, time_limit=7200)
def goabase_sync_task(self) -> Dict[str, Any]:
    """
    Celery task to sync all festivals from Goabase.
    
    Runs periodically (configurable: daily, weekly, monthly).
    Can be manually triggered from the UI.
    
    Soft time limit: 1 hour (graceful stop)
    Hard time limit: 2 hours (force kill)
    """
    import asyncio
    
    settings = get_settings()
    
    # Check if sync is already running
    if sync_manager.status.is_running:
        logger.warning("Goabase sync already running, skipping")
        return {
            "status": "skipped",
            "reason": "Sync already running",
            "current_status": sync_manager.status.__dict__
        }
    
    async def _sync():
        async with GoabaseSync(settings, sync_manager) as sync:
            return await sync.sync_all()
    
    try:
        logger.info("Starting Goabase sync task")
        result = asyncio.run(_sync())
        result["status"] = "success"
        result["task_id"] = self.request.id
        logger.info(f"Goabase sync task completed: {result}")
        return result
        
    except SoftTimeLimitExceeded:
        logger.warning("Goabase sync task hit soft time limit, stopping gracefully")
        sync_manager.request_stop()
        return {
            "status": "stopped",
            "reason": "Time limit exceeded",
            "current_status": sync_manager.status.__dict__
        }
        
    except Exception as e:
        logger.error(f"Goabase sync task failed: {e}")
        sync_manager.mark_complete()
        raise self.retry(exc=e, countdown=3600)


@shared_task
def goabase_sync_stop_task() -> Dict[str, Any]:
    """
    Task to request Goabase sync to stop gracefully.
    """
    if not sync_manager.status.is_running:
        return {
            "status": "not_running",
            "message": "No Goabase sync is currently running"
        }
    
    sync_manager.request_stop()
    return {
        "status": "stop_requested",
        "message": "Stop signal sent to running Goabase sync",
        "current_status": sync_manager.status.__dict__
    }


async def get_goabase_sync_status() -> Dict[str, Any]:
    """Get current Goabase sync status."""
    status = sync_manager.status
    return {
        "is_running": status.is_running,
        "started_at": status.started_at.isoformat() if status.started_at else None,
        "completed_at": status.completed_at.isoformat() if status.completed_at else None,
        "total_found": status.total_found,
        "new_count": status.new_count,
        "update_count": status.update_count,
        "unchanged_count": status.unchanged_count,
        "error_count": status.error_count,
        "current_operation": status.current_operation,
        "stop_requested": status.stop_requested,
        "progress_percentage": _calculate_progress(status),
    }


def _calculate_progress(status) -> int:
    """Calculate progress percentage."""
    if status.total_found == 0:
        return 0
    
    processed = status.new_count + status.update_count + status.unchanged_count + status.error_count
    return min(100, int((processed / status.total_found) * 100))
