"""Dashboard API routes."""

import logging
from datetime import timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.core.database import get_db
from src.core.models import (
    AgentDecision,
    CostLog,
    DiscoveryQuery,
    Festival,
    FestivalEventDate,
    FestivalState,
    StateTransition,
    SystemSettings,
)
from src.core.schemas import (
    FestivalAction,
    FestivalActionRequest,
    FestivalActionResponse,
    FestivalActionResult,
    FestivalPendingAction,
)
from src.dashboard.schedule_router import router as schedule_router
from src.dashboard.settings_router import router as settings_router
from src.tasks.celery_app import discovery_pipeline, research_pipeline, sync_pipeline
from src.tasks.goabase_sync import goabase_sync_pipeline
from src.utils.utc_now import utc_now

logger = logging.getLogger(__name__)

router = APIRouter()

# Include sub-routers
router.include_router(schedule_router)
router.include_router(settings_router)


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get dashboard statistics."""
    # Count by state and total festivals
    state_counts = {}
    total_festivals = 0
    for state in FestivalState:
        result = await db.execute(select(func.count()).where(Festival.state == state.value))
        count = result.scalar()
        state_counts[state.value] = count
        total_festivals += count

    # Today's cost
    today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_cost = await db.execute(
        select(func.sum(CostLog.cost_cents)).where(CostLog.created_at >= today_start)
    )
    today_cost_cents = today_cost.scalar() or 0

    # Week cost (last 7 days)
    week_start = utc_now() - timedelta(days=7)
    week_cost = await db.execute(
        select(func.sum(CostLog.cost_cents)).where(CostLog.created_at >= week_start)
    )
    week_cost_cents = week_cost.scalar() or 0

    # Month cost (last 30 days)
    month_start = utc_now() - timedelta(days=30)
    month_cost = await db.execute(
        select(func.sum(CostLog.cost_cents)).where(CostLog.created_at >= month_start)
    )
    month_cost_cents = month_cost.scalar() or 0

    # Pending count (festivals in discovered, researching, researched, failed states)
    pending_states = [
        FestivalState.DISCOVERED.value,
        FestivalState.RESEARCHING.value,
        FestivalState.RESEARCHED.value,
        FestivalState.FAILED.value,
    ]
    pending_result = await db.execute(
        select(func.count()).where(Festival.state.in_(pending_states))
    )
    pending_count = pending_result.scalar() or 0

    # Failed count
    failed_result = await db.execute(
        select(func.count()).where(Festival.state == FestivalState.FAILED.value)
    )
    failed_count = failed_result.scalar() or 0

    return {
        "total_festivals": total_festivals,
        "by_state": state_counts,
        "today_cost_cents": today_cost_cents,
        "week_cost_cents": week_cost_cents,
        "month_cost_cents": month_cost_cents,
        "pending_count": pending_count,
        "failed_count": failed_count,
    }


@router.get("/festivals")
async def list_festivals(
    state: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List festivals with filters."""
    query = select(Festival)

    if state:
        query = query.where(Festival.state == state)
    if source:
        query = query.where(Festival.source == source)
    if search:
        query = query.where(Festival.name.ilike(f"%{search}%"))

    query = query.order_by(desc(Festival.created_at))
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    festivals = result.scalars().all()

    return {
        "festivals": [
            {
                "id": str(f.id),
                "name": f.name,
                "source": f.source,
                "state": f.state,
                "is_duplicate": f.is_duplicate,
                "retry_count": f.retry_count,
                "created_at": f.created_at.isoformat() if f.created_at else None,
                "research_data": f.research_data,
                "partymap_event_id": str(f.partymap_event_id) if f.partymap_event_id else None,
                "partymap_date_id": str(f.partymap_date_id) if f.partymap_date_id else None,
            }
            for f in festivals
        ],
        "total": len(festivals),
        "limit": limit,
        "offset": offset,
    }


@router.get("/festivals/pending", response_model=List[FestivalPendingAction])
async def get_pending_festivals(
    state: Optional[FestivalState] = Query(None, description="Filter by specific state"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of results"),
    db: AsyncSession = Depends(get_db),
):
    """Get festivals that need manual action.

    Returns festivals in states that require manual intervention when
    auto_process is disabled: DISCOVERED, RESEARCHING, RESEARCHED, FAILED

    Each festival includes a suggested_action field indicating the
    recommended next step based on its current state.
    """
    query = select(Festival)

    if state:
        query = query.where(Festival.state == state.value)
    else:
        # States that typically need manual action
        query = query.where(
            Festival.state.in_(
                [
                    FestivalState.DISCOVERED.value,
                    FestivalState.RESEARCHING.value,
                    FestivalState.RESEARCHED.value,
                    FestivalState.FAILED.value,
                ]
            )
        )

    query = query.order_by(Festival.created_at.desc()).limit(limit)

    result = await db.execute(query)
    festivals = result.scalars().all()

    pending_actions = []
    for festival in festivals:
        # Determine suggested action based on state
        if festival.state == FestivalState.DISCOVERED.value:
            suggested_action = FestivalAction.DEDUPLICATE
            action_desc = "Check for duplicates and determine if research is needed"
        elif festival.state == FestivalState.RESEARCHING.value:
            suggested_action = FestivalAction.RESEARCH
            action_desc = "Run research agent to extract festival details"
        elif festival.state == FestivalState.RESEARCHED.value:
            suggested_action = FestivalAction.SYNC
            action_desc = "Sync festival data to PartyMap"
        elif festival.state == FestivalState.FAILED.value:
            suggested_action = FestivalAction.RETRY
            action_desc = "Retry the failed operation"
        else:
            suggested_action = FestivalAction.SKIP
            action_desc = "No action needed"

        pending_actions.append(
            FestivalPendingAction(
                festival_id=festival.id,
                name=festival.name,
                state=FestivalState(festival.state),
                source=festival.source,
                suggested_action=suggested_action,
                action_description=action_desc,
                created_at=festival.created_at,
                retry_count=festival.retry_count,
                last_error=festival.last_error,
                partymap_event_id=str(festival.partymap_event_id) if festival.partymap_event_id else None,
            )
        )

    return pending_actions


@router.get("/festivals/{festival_id}")
async def get_festival(
    festival_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get full festival details."""
    festival = await db.get(Festival, festival_id)
    if not festival:
        raise HTTPException(status_code=404, detail="Festival not found")

    # Get event dates
    dates_result = await db.execute(
        select(FestivalEventDate).where(FestivalEventDate.festival_id == festival_id)
    )
    event_dates = dates_result.scalars().all()

    # Get decisions
    decisions_result = await db.execute(
        select(AgentDecision)
        .where(AgentDecision.festival_id == festival_id)
        .order_by(AgentDecision.step_number)
    )
    decisions = decisions_result.scalars().all()

    # Get cost
    cost_result = await db.execute(
        select(func.sum(CostLog.cost_cents)).where(CostLog.festival_id == festival_id)
    )
    total_cost = cost_result.scalar() or 0

    return {
        "id": str(festival.id),
        "name": festival.name,
        "source": festival.source,
        "source_url": festival.source_url,
        "state": festival.state,
        "is_duplicate": festival.is_duplicate,
        "is_new_event_date": festival.is_new_event_date,
        "date_confirmed": festival.date_confirmed,
        "partymap_event_id": str(festival.partymap_event_id)
        if festival.partymap_event_id
        else None,
        "retry_count": festival.retry_count,
        "last_error": festival.last_error,
        "discovery_cost_cents": festival.discovery_cost_cents,
        "research_cost_cents": festival.research_cost_cents,
        "total_cost_cents": total_cost,
        "event_dates": [
            {
                "id": str(d.id),
                "start": d.start_date.isoformat() if d.start_date else None,
                "end": d.end_date.isoformat() if d.end_date else None,
                "location": d.location_description,
                "lineup_count": len(d.lineup) if d.lineup else 0,
            }
            for d in event_dates
        ],
        "decisions": [
            {
                "agent_type": d.agent_type,
                "step": d.step_number,
                "thought": d.thought,
                "action": d.action,
                "observation": d.observation,
                "confidence": d.confidence,
            }
            for d in decisions
        ],
        "research_data": festival.research_data,
        "created_at": festival.created_at.isoformat() if festival.created_at else None,
        "updated_at": festival.updated_at.isoformat() if festival.updated_at else None,
    }


@router.post("/festivals/{festival_id}/retry")
async def retry_festival(
    festival_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Manually retry a failed festival."""
    festival = await db.get(Festival, festival_id)
    if not festival:
        raise HTTPException(status_code=404, detail="Festival not found")

    # Reset for retry
    old_state = festival.state
    festival.state = FestivalState.RESEARCHING
    festival.retry_count = 0
    festival.last_error = None

    # Log transition
    transition = StateTransition(
        festival_id=festival_id,
        from_state=old_state,
        to_state=FestivalState.RESEARCHING,
        reason="Manual retry",
    )
    db.add(transition)
    await db.commit()

    # Queue for research
    research_pipeline.delay(str(festival_id))

    return {"message": "Festival queued for retry", "festival_id": str(festival_id)}


@router.post("/festivals/{festival_id}/skip")
async def skip_festival(
    festival_id: UUID,
    reason: str,
    db: AsyncSession = Depends(get_db),
):
    """Skip a festival."""
    festival = await db.get(Festival, festival_id)
    if not festival:
        raise HTTPException(status_code=404, detail="Festival not found")

    old_state = festival.state
    festival.state = FestivalState.SKIPPED
    festival.skip_reason = reason

    transition = StateTransition(
        festival_id=festival_id,
        from_state=old_state,
        to_state=FestivalState.SKIPPED,
        reason=f"Manual skip: {reason}",
    )
    db.add(transition)
    await db.commit()

    return {"message": "Festival skipped", "festival_id": str(festival_id)}


@router.post("/festivals/{festival_id}/force-sync")
async def force_sync(
    festival_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Force sync a festival."""
    festival = await db.get(Festival, festival_id)
    if not festival:
        raise HTTPException(status_code=404, detail="Festival not found")

    festival.state = FestivalState.SYNCING
    await db.commit()

    sync_pipeline.delay(str(festival_id))

    return {"message": "Festival queued for sync", "festival_id": str(festival_id)}


@router.post("/discovery/run")
async def run_discovery(
    query: Optional[str] = None,
):
    """Manually trigger discovery."""
    task = discovery_pipeline.delay(manual_query=query)
    return {"message": "Discovery started", "task_id": task.id, "query": query}


@router.post("/goabase/sync")
async def run_goabase_sync():
    """Manually trigger Goabase sync."""
    task = goabase_sync_pipeline.delay()
    return {"message": "Goabase sync started", "task_id": task.id}


@router.get("/queries")
async def list_queries(
    enabled_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """List discovery queries."""
    query = select(DiscoveryQuery)
    if enabled_only:
        query = query.where(DiscoveryQuery.enabled == True)
    query = query.order_by(DiscoveryQuery.last_run_at.nullsfirst())

    result = await db.execute(query)
    queries = result.scalars().all()

    return [
        {
            "id": str(q.id),
            "query_text": q.query,
            "category": q.category,
            "enabled": q.enabled,
            "run_count": q.run_count,
            "last_run_at": q.last_run_at.isoformat() if q.last_run_at else None,
            "created_at": q.created_at.isoformat() if q.created_at else None,
            "updated_at": q.updated_at.isoformat() if q.updated_at else None,
        }
        for q in queries
    ]


@router.post("/queries/{query_id}/enable")
async def enable_query(
    query_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Enable a discovery query."""
    query = await db.get(DiscoveryQuery, query_id)
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")

    query.enabled = True
    await db.commit()
    await db.refresh(query)
    return {
        "id": str(query.id),
        "query_text": query.query,
        "category": query.category,
        "enabled": query.enabled,
        "run_count": query.run_count,
        "last_run_at": query.last_run_at.isoformat() if query.last_run_at else None,
        "created_at": query.created_at.isoformat() if query.created_at else None,
        "updated_at": query.updated_at.isoformat() if query.updated_at else None,
    }


@router.post("/queries/{query_id}/disable")
async def disable_query(
    query_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Disable a discovery query."""
    query = await db.get(DiscoveryQuery, query_id)
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")

    query.enabled = False
    await db.commit()
    await db.refresh(query)
    return {
        "id": str(query.id),
        "query_text": query.query,
        "category": query.category,
        "enabled": query.enabled,
        "run_count": query.run_count,
        "last_run_at": query.last_run_at.isoformat() if query.last_run_at else None,
        "created_at": query.created_at.isoformat() if query.created_at else None,
        "updated_at": query.updated_at.isoformat() if query.updated_at else None,
    }


@router.get("/costs")
async def get_costs(
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    """Get cost logs."""
    from_date = utc_now() - timedelta(days=days)

    # Get raw cost logs
    result = await db.execute(
        select(CostLog)
        .where(CostLog.created_at >= from_date)
        .order_by(desc(CostLog.created_at))
    )
    cost_logs = result.scalars().all()

    return [
        {
            "id": str(log.id),
            "festival_id": str(log.festival_id) if log.festival_id else None,
            "agent_type": log.agent_type,
            "operation": log.service,  # Map service to operation for frontend
            "cost_cents": log.cost_cents,
            "details": {"description": log.description} if log.description else {},
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in cost_logs
    ]


@router.post("/queries")
async def create_query(
    query_text: str,
    category: str = "general",
    db: AsyncSession = Depends(get_db),
):
    """Create a new discovery query."""
    query = DiscoveryQuery(
        query=query_text,
        category=category,
        enabled=True,
    )
    db.add(query)
    await db.commit()
    await db.refresh(query)
    return {
        "id": str(query.id),
        "query_text": query.query,
        "category": query.category,
        "enabled": query.enabled,
        "run_count": query.run_count,
        "last_run_at": query.last_run_at.isoformat() if query.last_run_at else None,
        "created_at": query.created_at.isoformat() if query.created_at else None,
        "updated_at": query.updated_at.isoformat() if query.updated_at else None,
    }


@router.put("/queries/{query_id}")
async def update_query(
    query_id: UUID,
    query_text: Optional[str] = None,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Update a discovery query."""
    query = await db.get(DiscoveryQuery, query_id)
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")

    if query_text is not None:
        query.query = query_text
    if category is not None:
        query.category = category

    await db.commit()
    await db.refresh(query)
    return {
        "id": str(query.id),
        "query_text": query.query,
        "category": query.category,
        "enabled": query.enabled,
        "run_count": query.run_count,
        "last_run_at": query.last_run_at.isoformat() if query.last_run_at else None,
        "created_at": query.created_at.isoformat() if query.created_at else None,
        "updated_at": query.updated_at.isoformat() if query.updated_at else None,
    }


@router.delete("/queries/{query_id}")
async def delete_query(
    query_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a discovery query."""
    query = await db.get(DiscoveryQuery, query_id)
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")

    await db.delete(query)
    await db.commit()
    return {"message": "Query deleted", "id": str(query_id)}


# ==================== Manual Festival Action Endpoints ====================

from src.core.schemas import DeduplicationResultResponse


@router.post("/festivals/{festival_id}/deduplicate", response_model=DeduplicationResultResponse)
async def deduplicate_festival(
    festival_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger deduplication check for a festival.

    This checks if the festival is a duplicate of an existing PartyMap event
    and determines the next step:
    - New festival → moves to RESEARCHING state
    - New date for existing event → moves to RESEARCHING state
    - Existing event needs update → moves to RESEARCHING state
    - Duplicate up-to-date → moves to SYNCED state

    In manual mode, the next step is NOT automatically queued - you must
    manually trigger research or sync via their respective endpoints.
    """
    festival = await db.get(Festival, festival_id)
    if not festival:
        raise HTTPException(status_code=404, detail="Festival not found")

    if festival.state != FestivalState.DISCOVERED.value:
        raise HTTPException(
            status_code=400,
            detail=f"Festival must be in DISCOVERED state, currently: {festival.state}",
        )

    # Run deduplication synchronously for immediate result
    import asyncio

    from sqlalchemy.orm import Session

    from src.config import get_settings
    from src.core.database import sync_engine
    from src.partymap.client import PartyMapClient

    settings = get_settings()
    sync_session = Session(bind=sync_engine)

    try:
        # Check for duplicates
        async def _check_duplicate():
            client = PartyMapClient(settings)
            location = (
                festival.discovered_data.get("location", "") if festival.discovered_data else ""
            )
            result = await client.check_duplicate(
                name=festival.name, source_url=festival.source_url, location=location
            )
            await client.close()
            return result

        result = asyncio.run(_check_duplicate())

        # Update festival with deduplication results
        festival.is_duplicate = result.is_duplicate
        festival.existing_event_id = result.existing_event_id
        festival.is_new_event_date = result.is_new_event_date
        festival.date_confirmed = result.date_confirmed

        # Determine action based on result
        if result.is_duplicate:
            if result.is_new_event_date or not result.date_confirmed:
                # Needs research
                old_state = festival.state
                festival.state = FestivalState.RESEARCHING.value

                # Log transition
                transition = StateTransition(
                    festival_id=festival_id,
                    from_state=old_state,
                    to_state=FestivalState.RESEARCHING.value,
                    reason="Manual deduplication: new date or needs update",
                )
                db.add(transition)

                action_taken = "Moved to RESEARCHING state (ready for research)"
            else:
                # Up to date, skip to synced
                old_state = festival.state
                festival.state = FestivalState.SYNCED.value

                transition = StateTransition(
                    festival_id=festival_id,
                    from_state=old_state,
                    to_state=FestivalState.SYNCED.value,
                    reason="Manual deduplication: already up to date",
                )
                db.add(transition)

                action_taken = "Marked as SYNCED (already up to date)"
        else:
            # New festival - needs research
            old_state = festival.state
            festival.state = FestivalState.RESEARCHING.value

            transition = StateTransition(
                festival_id=festival_id,
                from_state=old_state,
                to_state=FestivalState.RESEARCHING.value,
                reason="Manual deduplication: new festival",
            )
            db.add(transition)

            action_taken = "Moved to RESEARCHING state (new festival)"

        await db.commit()

        # Check auto_process to inform user
        from src.dashboard.settings_router import is_auto_process_enabled

        auto_process = await is_auto_process_enabled(db)

        return DeduplicationResultResponse(
            festival_id=festival_id,
            is_duplicate=result.is_duplicate,
            existing_event_id=result.existing_event_id,
            is_new_event_date=result.is_new_event_date,
            date_confirmed=result.date_confirmed,
            confidence=result.confidence,
            reason=result.reason,
            action_taken=action_taken,
            auto_queued=False,  # Manual endpoint never auto-queues
        )

    except Exception as e:
        await db.rollback()
        logger.error(f"Manual deduplication failed for {festival_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Deduplication failed: {str(e)}")


@router.post("/festivals/{festival_id}/research", response_model=FestivalActionResponse)
async def research_festival(
    festival_id: UUID,
    request: Optional[FestivalActionRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger research for a festival.

    Queues the festival for research regardless of auto_process setting.
    The festival must be in RESEARCHING state (set by deduplication check).

    Use this endpoint in manual mode to trigger research after deduplication,
    or to retry research for a failed festival.
    """
    festival = await db.get(Festival, festival_id)
    if not festival:
        raise HTTPException(status_code=404, detail="Festival not found")

    # Allow research from RESEARCHING or FAILED states
    if festival.state not in [FestivalState.RESEARCHING.value, FestivalState.FAILED.value]:
        raise HTTPException(
            status_code=400,
            detail=f"Festival must be in RESEARCHING or FAILED state, currently: {festival.state}",
        )

    old_state = festival.state

    # Reset retry count if coming from FAILED
    if festival.state == FestivalState.FAILED.value:
        festival.retry_count = 0
        festival.last_error = None

    # Update state
    festival.state = FestivalState.RESEARCHING.value

    # Log transition
    reason = request.reason if request and request.reason else "Manual research trigger"
    transition = StateTransition(
        festival_id=festival_id,
        from_state=old_state,
        to_state=FestivalState.RESEARCHING.value,
        reason=reason,
    )
    db.add(transition)
    await db.commit()

    # Queue research task
    task = research_pipeline.delay(str(festival_id))

    return FestivalActionResponse(
        festival_id=festival_id,
        action="research",
        result="queued",
        message=f"Research queued for {festival.name}. Task ID: {task.id}",
        previous_state=old_state,
        new_state=FestivalState.RESEARCHING.value,
        task_id=task.id,
        queued=True,
    )


@router.post("/festivals/bulk/research")
async def bulk_research_festivals(
    failure_reason: Optional[str] = Query(None, description="Filter by failure reason"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of festivals to research"),
    min_completeness: float = Query(0.0, ge=0.0, le=1.0, description="Minimum completeness score for partial research"),
    max_retry_count: int = Query(3, ge=0, description="Maximum retry count for failed festivals"),
    db: AsyncSession = Depends(get_db),
):
    """
    Bulk research for festivals matching criteria.
    
    Default: Research all failed festivals where failure_reason = 'dates' and retry_count < 3
    Limits to 50 festivals per day for cost control.
    """
    settings = get_settings()

    # Check auto_process setting - require manual mode for bulk operations
    auto_process_result = await db.execute(
        select(SystemSettings).where(SystemSettings.key == "auto_process")
    )
    auto_process_setting = auto_process_result.scalar_one_or_none()

    if auto_process_setting and auto_process_setting.value == "true":
        raise HTTPException(
            status_code=400,
            detail="Bulk research requires manual mode. Disable auto_process in settings first."
        )

    # Check daily limit (50 per day as per requirement #4)
    today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)

    # Count research tasks queued today
    today_research_count = await _get_today_research_count()
    remaining_today = 50 - today_research_count

    if remaining_today <= 0:
        raise HTTPException(
            status_code=429,
            detail=f"Daily limit of 50 bulk research operations reached. Try again tomorrow."
        )

    # Adjust limit to remaining daily quota
    limit = min(limit, remaining_today)

    # Build query based on filters
    query = select(Festival).where(
        Festival.state.in_([FestivalState.FAILED.value, FestivalState.RESEARCHED_PARTIAL.value]),
        Festival.retry_count < max_retry_count
    )

    # Apply failure reason filter
    if failure_reason:
        query = query.where(Festival.failure_reason == failure_reason)
    else:
        # Default: 'dates' failure reason (as per requirement #3)
        query = query.where(Festival.failure_reason == "dates")

    # Apply completeness filter
    if min_completeness > 0:
        query = query.where(
            Festival.research_completeness_score >= min_completeness
        )

    query = query.limit(limit)

    # Execute query
    result = await db.execute(query)
    festivals = result.scalars().all()

    if not festivals:
        return {
            "queued": 0,
            "message": "No festivals match the specified criteria",
            "daily_remaining": remaining_today
        }

    # Queue research tasks
    queued = 0
    task_ids = []

    for festival in festivals:
        try:
            # Reset retry count for failed festivals
            if festival.state == FestivalState.FAILED.value:
                festival.retry_count = 0
                festival.last_error = None

            # Update state
            festival.state = FestivalState.RESEARCHING.value

            # Log transition
            transition = StateTransition(
                festival_id=festival.id,
                from_state=festival.state,
                to_state=FestivalState.RESEARCHING.value,
                reason=f"Bulk research: {failure_reason or 'dates'}"
            )
            db.add(transition)

            # Queue research task
            task = research_pipeline.delay(str(festival.id))
            task_ids.append(task.id)
            queued += 1

            logger.info(f"Queued bulk research for festival {festival.id} ({festival.name})")

        except Exception as e:
            logger.error(f"Failed to queue research for festival {festival.id}: {e}")
            # Continue with other festivals

    await db.commit()

    # Increment daily counter
    if queued > 0:
        await _increment_today_research_count(queued)
        today_research_count = await _get_today_research_count()
        new_remaining = 50 - today_research_count
    else:
        new_remaining = remaining_today

    return {
        "queued": queued,
        "total_matched": len(festivals),
        "task_ids": task_ids,
        "filters_applied": {
            "failure_reason": failure_reason or "dates",
            "limit": limit,
            "min_completeness": min_completeness,
            "max_retry_count": max_retry_count
        },
        "daily_remaining": new_remaining,
        "daily_used": today_research_count if queued > 0 else today_research_count,
        "message": f"Queued research for {queued} festivals"
    }


async def _get_today_research_count() -> int:
    """Get count of research tasks queued today using Redis."""
    from src.core.database import get_redis_client

    redis_client = get_redis_client()
    today_key = f"partymap_bot:daily_research_count:{utc_now().date().isoformat()}"

    # Get current count
    count = redis_client.get(today_key)
    return int(count) if count else 0


async def _increment_today_research_count(amount: int = 1) -> int:
    """Increment count of research tasks queued today."""
    from src.core.database import get_redis_client

    redis_client = get_redis_client()
    today_key = f"partymap_bot:daily_research_count:{utc_now().date().isoformat()}"

    # Increment and set expiry to 48 hours to handle timezone edge cases
    new_count = redis_client.incrby(today_key, amount)
    if redis_client.ttl(today_key) == -1:  # No expiry set
        # Set expiry to 48 hours
        redis_client.expire(today_key, 48 * 60 * 60)

    return new_count


@router.post("/festivals/{festival_id}/sync", response_model=FestivalActionResponse)
async def sync_festival(
    festival_id: UUID,
    request: Optional[FestivalActionRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger sync for a festival.

    Queues the festival for sync to PartyMap. The festival must have
    completed research (state = RESEARCHED).

    Use this endpoint in manual mode to trigger sync after research completes.
    """
    festival = await db.get(Festival, festival_id)
    if not festival:
        raise HTTPException(status_code=404, detail="Festival not found")

    if festival.state != FestivalState.RESEARCHED.value:
        raise HTTPException(
            status_code=400,
            detail=f"Festival must be in RESEARCHED state, currently: {festival.state}",
        )

    old_state = festival.state
    festival.state = FestivalState.SYNCING.value

    # Log transition
    reason = request.reason if request and request.reason else "Manual sync trigger"
    transition = StateTransition(
        festival_id=festival_id,
        from_state=old_state,
        to_state=FestivalState.SYNCING.value,
        reason=reason,
    )
    db.add(transition)
    await db.commit()

    # Queue sync task
    task = sync_pipeline.delay(str(festival_id))

    return FestivalActionResponse(
        festival_id=festival_id,
        action=FestivalAction.SYNC,
        result=FestivalActionResult.QUEUED,
        message=f"Sync queued for {festival.name}",
        previous_state=FestivalState(old_state),
        new_state=FestivalState.SYNCING,
        task_id=task.id,
        queued=True,
    )


@router.post("/festivals/{festival_id}/skip", response_model=FestivalActionResponse)
async def skip_festival_manual(
    festival_id: UUID,
    reason: str = Query(..., description="Reason for skipping this festival"),
    db: AsyncSession = Depends(get_db),
):
    """Manually skip a festival.

    Marks the festival as SKIPPED with the provided reason.
    Skipped festivals are excluded from further processing.
    """
    festival = await db.get(Festival, festival_id)
    if not festival:
        raise HTTPException(status_code=404, detail="Festival not found")

    old_state = festival.state
    festival.state = FestivalState.SKIPPED.value
    festival.skip_reason = reason

    # Log transition
    transition = StateTransition(
        festival_id=festival_id,
        from_state=old_state,
        to_state=FestivalState.SKIPPED.value,
        reason=f"Manual skip: {reason}",
    )
    db.add(transition)
    await db.commit()

    return FestivalActionResponse(
        festival_id=festival_id,
        action=FestivalAction.SKIP,
        result=FestivalActionResult.SKIPPED,
        message=f"Festival skipped: {reason}",
        previous_state=FestivalState(old_state),
        new_state=FestivalState.SKIPPED,
        queued=False,
    )


@router.post("/festivals/{festival_id}/reset", response_model=FestivalActionResponse)
async def reset_festival(
    festival_id: UUID,
    target_state: FestivalState = Query(
        FestivalState.DISCOVERED,
        description="State to reset to (default: DISCOVERED)",
    ),
    db: AsyncSession = Depends(get_db),
):
    """Reset a festival to an earlier state.

    Useful for reprocessing a festival from a specific stage.
    Clears relevant data based on target state:
    - DISCOVERED: Clears all research and sync data
    - RESEARCHING: Clears research data but keeps discovered data
    - RESEARCHED: Clears sync data but keeps research data

    Use with caution - this will re-queue tasks if auto_process is enabled.
    """
    festival = await db.get(Festival, festival_id)
    if not festival:
        raise HTTPException(status_code=404, detail="Festival not found")

    old_state = festival.state

    # Clear data based on target state
    if target_state == FestivalState.DISCOVERED:
        festival.research_data = {}
        festival.sync_data = {}
        festival.research_cost_cents = 0
        festival.is_duplicate = False
        festival.existing_event_id = None
    elif target_state == FestivalState.RESEARCHING:
        festival.research_data = {}
        festival.sync_data = {}
        festival.research_cost_cents = 0

    festival.state = target_state.value
    festival.retry_count = 0
    festival.last_error = None

    # Log transition
    transition = StateTransition(
        festival_id=festival_id,
        from_state=old_state,
        to_state=target_state.value,
        reason=f"Manual reset to {target_state.value}",
    )
    db.add(transition)
    await db.commit()

    return FestivalActionResponse(
        festival_id=festival_id,
        action=FestivalAction.RESET,
        result=FestivalActionResult.COMPLETED,
        message=f"Festival reset to {target_state.value}",
        previous_state=FestivalState(old_state),
        new_state=target_state,
        queued=False,
    )
