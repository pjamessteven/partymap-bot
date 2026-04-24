"""Celery tasks and API endpoints for Goabase sync."""

import logging
from typing import Any, Dict

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from src.config import get_settings
from src.sources.goabase_sync import GoabaseSync, sync_manager

logger = logging.getLogger(__name__)


@shared_task(bind=True, soft_time_limit=3600, time_limit=7200)
def goabase_sync_task(self, thread_id: str = None) -> Dict[str, Any]:
    """
    Celery task to sync all festivals from Goabase with streaming.
    
    Runs periodically (configurable: daily, weekly, monthly).
    Can be manually triggered from the UI.
    Streams progress to the UI in real-time.
    
    Soft time limit: 1 hour (graceful stop)
    Hard time limit: 2 hours (force kill)
    """
    import asyncio
    import uuid

    settings = get_settings()

    # Check if sync is already running
    if sync_manager.status.is_running:
        logger.warning("Goabase sync already running, skipping")
        return {
            "status": "skipped",
            "reason": "Sync already running",
            "current_status": sync_manager.status.__dict__
        }

    # Generate thread ID for this sync run if not provided
    import uuid as uuid_module
    if not thread_id:
        thread_id = f"goabase_{uuid_module.uuid4().hex[:8]}"

    async def _sync():
        from src.agents.streaming.job_streamer import JobStreamer

        async with JobStreamer("goabase", thread_id) as streamer:
            await streamer.info("Starting Goabase sync...")
            
            async with GoabaseSync(settings, sync_manager, writer=streamer._emit) as sync:
                result = await sync.sync_all()
                
                # Send completion event
                await streamer.complete(
                    total_found=result.get("total_found", 0),
                    new_count=result.get("new_count", 0),
                    update_count=result.get("update_count", 0),
                    error_count=result.get("error_count", 0),
                )
                return result

    try:
        logger.info(f"Starting Goabase sync task: {thread_id}")
        result = asyncio.run(_sync())
        result["status"] = "success"
        result["task_id"] = self.request.id
        result["thread_id"] = thread_id
        logger.info(f"Goabase sync task completed: {result}")
        return result

    except SoftTimeLimitExceeded:
        logger.warning("Goabase sync task hit soft time limit, stopping gracefully")
        sync_manager.request_stop()
        return {
            "status": "stopped",
            "reason": "Time limit exceeded",
            "thread_id": thread_id,
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
