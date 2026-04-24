"""API routes for job control and monitoring."""

import json
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.streaming.broadcaster import get_broadcaster
from src.core.database import get_db
from src.core.job_activity import JobActivityLogger
from src.core.job_tracker import JobTracker, JobType
from src.core.models import PipelineSchedule
from src.tasks.celery_app import discovery_pipeline, research_pipeline, run_sync_task
from src.tasks.goabase_tasks import goabase_sync_task
from src.utils.utc_now import utc_now

router = APIRouter()


# Store active WebSocket connections
_job_websockets: List[WebSocket] = []


async def broadcast_job_update(job_type: str, data: dict):
    """Broadcast job update to all connected WebSocket clients."""
    message = {
        "type": "job_update",
        "job_type": job_type,
        "data": data,
        "timestamp": utc_now().isoformat(),
    }

    # Broadcast via Redis for multi-instance support
    broadcaster = await get_broadcaster()
    await broadcaster.broadcast(f"jobs:{job_type}", message)

    # Also send to local WebSocket clients
    disconnected = []
    for ws in _job_websockets:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.append(ws)

    # Clean up disconnected clients
    for ws in disconnected:
        if ws in _job_websockets:
            _job_websockets.remove(ws)


@router.get("/jobs/status")
async def get_jobs_status(
    db: AsyncSession = Depends(get_db),
):
    """Get status of all jobs synced with Celery ground truth."""
    statuses = JobTracker.get_all_status_synced()

    # Add processing festivals info
    for job_type in statuses:
        if statuses[job_type]:
            statuses[job_type]["currently_processing"] = JobTracker.get_processing_festivals(
                JobType(job_type)
            )

    # Add 'goabase' alias for 'goabase_sync' to match frontend
    if "goabase_sync" in statuses:
        statuses["goabase"] = statuses["goabase_sync"]

    return statuses


@router.get("/jobs/activity")
async def get_job_activity(
    job_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get recent job activity from database."""
    activities = await JobActivityLogger.get_recent_activity(
        job_type=job_type,
        limit=limit,
        offset=offset,
    )

    return {
        "items": [
            {
                "id": str(a.id),
                "job_type": a.job_type,
                "activity_type": a.activity_type,
                "message": a.message,
                "details": a.details,
                "festival_id": str(a.festival_id) if a.festival_id else None,
                "task_id": a.task_id,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in activities
        ],
        "limit": limit,
        "offset": offset,
    }


# Individual job control endpoints
@router.post("/jobs/discovery/start")
async def start_discovery_job(
    query: Optional[str] = None,
):
    """Start discovery job."""
    task = discovery_pipeline.delay(manual_query=query)
    started = await JobTracker.try_start_job(JobType.DISCOVERY, task.id)
    if not started:
        # Revoke the task we just created since the job is already running
        from src.tasks.celery_app import celery_app
        celery_app.control.revoke(task.id, terminate=True, signal="SIGTERM")
        raise HTTPException(status_code=400, detail="Discovery already running")

    await broadcast_job_update("discovery", JobTracker.get_status(JobType.DISCOVERY))
    return {"message": "Discovery started", "task_id": task.id, "query": query}


@router.post("/jobs/discovery/stop")
async def stop_discovery_job():
    """Stop discovery job."""
    if not JobTracker.is_running(JobType.DISCOVERY):
        raise HTTPException(status_code=400, detail="Discovery not running")

    JobTracker.revoke_task(JobType.DISCOVERY)
    success = await JobTracker.stop_job(JobType.DISCOVERY)
    await broadcast_job_update("discovery", JobTracker.get_status(JobType.DISCOVERY))
    return {"message": "Discovery stopped", "success": success}


@router.post("/jobs/goabase/start")
async def start_goabase_job():
    """Start Goabase sync job."""
    task = goabase_sync_task.delay()
    started = await JobTracker.try_start_job(JobType.GOABASE_SYNC, task.id)
    if not started:
        from src.tasks.celery_app import celery_app
        celery_app.control.revoke(task.id, terminate=True, signal="SIGTERM")
        raise HTTPException(status_code=400, detail="Goabase sync already running")

    await broadcast_job_update("goabase_sync", JobTracker.get_status(JobType.GOABASE_SYNC))
    return {"message": "Goabase sync started", "task_id": task.id}


@router.post("/jobs/goabase/stop")
async def stop_goabase_job():
    """Stop Goabase sync job."""
    if not JobTracker.is_running(JobType.GOABASE_SYNC):
        raise HTTPException(status_code=400, detail="Goabase sync not running")

    JobTracker.revoke_task(JobType.GOABASE_SYNC)
    success = await JobTracker.stop_job(JobType.GOABASE_SYNC)
    await broadcast_job_update("goabase_sync", JobTracker.get_status(JobType.GOABASE_SYNC))
    return {"message": "Goabase sync stopped", "success": success}


@router.post("/jobs/research/start")
async def start_research_job(
    db: AsyncSession = Depends(get_db),
):
    """Start research job for all festivals needing research."""
    # Acquire lock atomically FIRST to prevent duplicate batches
    import uuid
    task_id = f"research_batch_{uuid.uuid4().hex[:8]}"
    started = await JobTracker.try_start_job(
        JobType.RESEARCH,
        task_id,
    )
    if not started:
        raise HTTPException(status_code=400, detail="Research already running")

    from sqlalchemy import or_, select
    from src.core.models import Festival, FestivalState

    result = await db.execute(
        select(Festival).where(
            or_(
                Festival.state == FestivalState.RESEARCHING.value,
                Festival.state == FestivalState.RESEARCHED_PARTIAL.value,
                Festival.state == FestivalState.FAILED.value,
                Festival.state == FestivalState.VALIDATION_FAILED.value,
            )
        ).with_for_update()
    )
    festivals = result.scalars().all()

    if not festivals:
        # Release the lock since there's nothing to do
        await JobTracker.stop_job(JobType.RESEARCH)
        return {"message": "No festivals need research", "task_id": None, "queued": 0}

    # Update tracker with actual total
    await JobTracker.update_progress(JobType.RESEARCH, current=0, total=len(festivals))

    # Queue research for each festival
    for festival in festivals:
        festival.state = FestivalState.RESEARCHING.value
        research_pipeline.delay(festival_id=str(festival.id))

    await db.commit()
    await broadcast_job_update("research", JobTracker.get_status(JobType.RESEARCH))

    return {
        "message": f"Research queued for {len(festivals)} festivals",
        "task_id": task_id,
        "queued": len(festivals),
    }


@router.post("/jobs/research/stop")
async def stop_research_job():
    """Stop research job."""
    if not JobTracker.is_running(JobType.RESEARCH):
        raise HTTPException(status_code=400, detail="Research not running")

    JobTracker.revoke_task(JobType.RESEARCH)
    success = await JobTracker.stop_job(JobType.RESEARCH)
    await broadcast_job_update("research", JobTracker.get_status(JobType.RESEARCH))
    return {"message": "Research stopped", "success": success}


@router.post("/jobs/sync/start")
async def start_sync_job():
    """Start sync job for all researched festivals.

    Returns immediately with task ID and thread_id. Stream progress via /threads/{thread_id}/runs/stream.
    """
    # Generate thread ID for streaming
    import uuid
    thread_id = f"sync_{uuid.uuid4().hex[:8]}"

    # Trigger Celery task with thread_id
    task = run_sync_task.delay(thread_id=thread_id)
    started = await JobTracker.try_start_job(JobType.SYNC, task.id)
    if not started:
        from src.tasks.celery_app import celery_app
        celery_app.control.revoke(task.id, terminate=True, signal="SIGTERM")
        raise HTTPException(status_code=400, detail="Sync already running")

    await broadcast_job_update("sync", JobTracker.get_status(JobType.SYNC))

    return {
        "status": "started",
        "task_id": task.id,
        "thread_id": thread_id,
        "message": "Sync job started. Stream progress via /threads/{thread_id}/runs/stream"
    }


@router.post("/jobs/sync/stop")
async def stop_sync_job():
    """Stop sync job."""
    if not JobTracker.is_running(JobType.SYNC):
        raise HTTPException(status_code=400, detail="Sync not running")

    JobTracker.revoke_task(JobType.SYNC)
    success = await JobTracker.stop_job(JobType.SYNC)
    await broadcast_job_update("sync", JobTracker.get_status(JobType.SYNC))
    return {"message": "Sync stopped", "success": success}


@router.post("/jobs/bulk/start")
async def start_jobs_bulk(
    job_types: List[str] = Body(..., description="List of job types to start"),
    db: AsyncSession = Depends(get_db),
):
    """Start multiple jobs."""
    results = []

    for job_type_str in job_types:
        try:
            job_type = JobType(job_type_str)
        except ValueError:
            results.append({
                "job_type": job_type_str,
                "success": False,
                "error": f"Invalid job type: {job_type_str}",
            })
            continue

        # Start the job via Celery task
        from src.tasks.goabase_tasks import goabase_sync_task
        from src.tasks.pipeline import discovery_pipeline, research_pipeline, run_sync_task

        task_map = {
            JobType.DISCOVERY: discovery_pipeline,
            JobType.RESEARCH: research_pipeline,
            JobType.SYNC: run_sync_task,
            JobType.GOABASE_SYNC: goabase_sync_task,
        }

        task = task_map.get(job_type)
        if not task:
            results.append({
                "job_type": job_type_str,
                "success": False,
                "error": "Task not found",
            })
            continue

        celery_task = task.delay()
        started = await JobTracker.try_start_job(job_type, celery_task.id)
        if not started:
            # Revoke the task we just created
            from src.tasks.celery_app import celery_app
            celery_app.control.revoke(celery_task.id, terminate=True, signal="SIGTERM")
            results.append({
                "job_type": job_type_str,
                "success": False,
                "error": "Job already running",
            })
            continue

        await broadcast_job_update(job_type_str, JobTracker.get_status(job_type))

        results.append({
            "job_type": job_type_str,
            "success": True,
            "task_id": celery_task.id,
        })

    return {"results": results}


@router.post("/jobs/bulk/stop")
async def stop_jobs_bulk(
    job_types: List[str] = Body(..., description="List of job types to stop"),
    db: AsyncSession = Depends(get_db),
):
    """Stop multiple running jobs."""
    results = []

    for job_type_str in job_types:
        try:
            job_type = JobType(job_type_str)
        except ValueError:
            results.append({
                "job_type": job_type_str,
                "success": False,
                "error": f"Invalid job type: {job_type_str}",
            })
            continue

        if not JobTracker.is_running(job_type):
            results.append({
                "job_type": job_type_str,
                "success": False,
                "error": "Job not running",
            })
            continue

        success = await JobTracker.stop_job(job_type)
        if success:
            await broadcast_job_update(job_type_str, JobTracker.get_status(job_type))

        results.append({
            "job_type": job_type_str,
            "success": success,
        })

    return {"results": results}


@router.post("/jobs/bulk/clear")
async def clear_jobs_bulk(
    job_types: List[str] = Body(..., description="List of job types to clear"),
    db: AsyncSession = Depends(get_db),
):
    """Clear status for selected jobs."""
    results = []

    for job_type_str in job_types:
        try:
            job_type = JobType(job_type_str)
        except ValueError:
            results.append({
                "job_type": job_type_str,
                "success": False,
                "error": f"Invalid job type: {job_type_str}",
            })
            continue

        # Don't clear running jobs
        if JobTracker.is_running(job_type):
            results.append({
                "job_type": job_type_str,
                "success": False,
                "error": "Cannot clear running job - stop it first",
            })
            continue

        JobTracker.clear_job(job_type)
        results.append({
            "job_type": job_type_str,
            "success": True,
        })

    return {"results": results}


@router.post("/jobs/clear-all")
async def clear_all_jobs(
    confirm: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Clear all job statuses. Requires confirmation."""
    if not confirm:
        raise HTTPException(400, "Must provide confirm=true to clear all jobs")

    # Check for running jobs
    running_jobs = []
    for job_type in JobType:
        if JobTracker.is_running(job_type):
            running_jobs.append(job_type.value)

    if running_jobs:
        raise HTTPException(
            400,
            f"Cannot clear all jobs while jobs are running: {', '.join(running_jobs)}. Stop them first."
        )

    JobTracker.clear_all_jobs()
    return {"message": "All job statuses cleared"}


@router.get("/jobs/scheduling/status")
async def get_scheduling_status(
    db: AsyncSession = Depends(get_db),
):
    """Get automatic scheduling status."""
    result = await db.execute(
        select(PipelineSchedule).where(PipelineSchedule.enabled == True)
    )
    enabled_schedules = result.scalars().all()

    # Check if auto-processing is enabled via settings
    from src.core.models import SystemSettings
    auto_process = await db.execute(
        select(SystemSettings).where(SystemSettings.key == "auto_process_enabled")
    )
    auto_process_setting = auto_process.scalar_one_or_none()

    return {
        "scheduling_enabled": len(enabled_schedules) > 0,
        "auto_process_enabled": (
            auto_process_setting.value == "true" if auto_process_setting else False
        ),
        "active_schedules": [
            {
                "task_type": s.task_type,
                "hour": s.hour,
                "minute": s.minute,
                "day_of_week": s.day_of_week,
                "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
            }
            for s in enabled_schedules
        ],
    }


@router.post("/jobs/scheduling/enable")
async def enable_scheduling(
    db: AsyncSession = Depends(get_db),
):
    """Enable automatic scheduling."""
    # Enable all schedules
    result = await db.execute(select(PipelineSchedule))
    schedules = result.scalars().all()

    for schedule in schedules:
        schedule.enabled = True

    await db.commit()

    return {"message": "Automatic scheduling enabled", "schedules_enabled": len(schedules)}


@router.post("/jobs/scheduling/disable")
async def disable_scheduling(
    db: AsyncSession = Depends(get_db),
):
    """Disable automatic scheduling (prevents new scheduled jobs from starting)."""
    # Disable all schedules
    result = await db.execute(select(PipelineSchedule))
    schedules = result.scalars().all()

    for schedule in schedules:
        schedule.enabled = False

    await db.commit()

    return {"message": "Automatic scheduling disabled", "schedules_disabled": len(schedules)}


@router.get("/jobs/{job_type}/activity")
async def get_job_activity_detail(
    job_type: str,
    task_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed activity for a specific job type."""
    try:
        job_type_enum = JobType(job_type)
    except ValueError:
        raise HTTPException(400, f"Invalid job type: {job_type}")

    if task_id:
        activities = await JobActivityLogger.get_activity_for_job(
            job_type=job_type,
            task_id=task_id,
            limit=limit,
        )
    else:
        activities = await JobActivityLogger.get_recent_activity(
            job_type=job_type,
            limit=limit,
        )

    return {
        "job_type": job_type,
        "task_id": task_id,
        "items": [
            {
                "id": str(a.id),
                "activity_type": a.activity_type,
                "message": a.message,
                "details": a.details,
                "festival_id": str(a.festival_id) if a.festival_id else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in activities
        ],
    }


@router.websocket("/jobs/ws")
async def jobs_websocket(websocket: WebSocket):
    """WebSocket for real-time job updates."""
    await websocket.accept()
    _job_websockets.append(websocket)

    # Subscribe to job updates via Redis
    broadcaster = await get_broadcaster()

    async def on_job_update(data: dict):
        try:
            await websocket.send_json(data)
        except (WebSocketDisconnect, RuntimeError) as e:
            # Client disconnected or connection closed
            logger.debug(f"WebSocket send failed (client likely disconnected): {e}")
        except Exception as e:
            # Unexpected error — log it so we can diagnose issues
            logger.warning(f"WebSocket send_json failed: {e}")

    # Subscribe to all job channels
    for job_type in JobType:
        await broadcaster.subscribe(f"jobs:{job_type.value}", on_job_update)

    try:
        # Send initial status
        statuses = JobTracker.get_all_status()
        await websocket.send_json({
            "type": "initial_status",
            "data": statuses,
        })

        # Keep connection alive and handle client messages
        while True:
            try:
                message = await websocket.receive_text()
            except (WebSocketDisconnect, RuntimeError):
                break

            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                logger.warning(f"WebSocket received invalid JSON: {message[:200]}")
                continue

            if data.get("action") == "ping":
                await websocket.send_json({"type": "pong"})
            elif data.get("action") == "get_status":
                statuses = JobTracker.get_all_status()
                await websocket.send_json({
                    "type": "status_update",
                    "data": statuses,
                })

    except WebSocketDisconnect:
        pass
    finally:
        # Unsubscribe and remove from list
        if websocket in _job_websockets:
            _job_websockets.remove(websocket)

        for job_type in JobType:
            try:
                await broadcaster.unsubscribe(f"jobs:{job_type.value}", on_job_update)
            except Exception as e:
                logger.warning(f"Broadcaster unsubscribe failed: {e}")
