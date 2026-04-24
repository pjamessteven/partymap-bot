"""Festival API routes for CRUD operations and manual actions."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.database import get_db
from src.core.models import CostLog, Festival, FestivalState, StateTransition
from src.core.schemas import (
    DeduplicationResultResponse,
    FestivalAction,
    FestivalActionRequest,
    FestivalActionResponse,
    FestivalPendingAction,
    FestivalUpdateRequest,
    FestivalUpdateResponse,
)
from src.core.validators import PartyMapSyncValidator, validate_festival_for_sync
from src.tasks.pipeline import deduplication_check, research_pipeline
from src.utils.utc_now import utc_now

router = APIRouter()


@router.get("/festivals")
async def get_festivals(
    state: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List festivals with optional filtering."""
    query = select(Festival).options(selectinload(Festival.event_dates))

    if state:
        query = query.where(Festival.state == state)
    if source:
        query = query.where(Festival.source == source)
    if search:
        query = query.where(Festival.name.ilike(f"%{search}%"))

    query = query.order_by(Festival.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    festivals = result.scalars().all()

    # Get total count
    count_query = select(Festival)
    if state:
        count_query = count_query.where(Festival.state == state)
    if source:
        count_query = count_query.where(Festival.source == source)
    if search:
        count_query = count_query.where(Festival.name.ilike(f"%{search}%"))

    count_query = select(func.count()).select_from(count_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return {
        "festivals": [f.to_dict() for f in festivals],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/festivals/pending")
async def get_pending_festivals(
    state: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get festivals needing manual action."""
    # States that require manual intervention
    pending_states = [
        FestivalState.DISCOVERED.value,
        FestivalState.RESEARCHED.value,
        FestivalState.RESEARCHED_PARTIAL.value,
        FestivalState.VALIDATION_FAILED.value,
        FestivalState.FAILED.value,
        FestivalState.NEEDS_REVIEW.value,
    ]

    query = select(Festival).where(Festival.state.in_(pending_states))

    if state:
        query = query.where(Festival.state == state)

    query = query.order_by(Festival.created_at.asc()).limit(limit)

    result = await db.execute(query)
    festivals = result.scalars().all()

    pending_actions = []
    for festival in festivals:
        suggested_action = _get_suggested_action(festival)
        action_description = _get_action_description(festival.state)

        pending_actions.append(
            FestivalPendingAction(
                festival_id=str(festival.id),
                name=festival.name,
                state=festival.state,
                source=festival.source,
                suggested_action=suggested_action,
                action_description=action_description,
                created_at=festival.created_at.isoformat() if festival.created_at else "",
                retry_count=festival.retry_count,
                last_error=festival.last_error,
                partymap_event_id=str(festival.partymap_event_id)
                if festival.partymap_event_id
                else None,
            )
        )

    return pending_actions


@router.post("/festivals/bulk/research")
async def bulk_research_festivals(
    failure_reason: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    min_completeness: Optional[float] = None,
    max_retry_count: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Bulk queue festivals for research."""
    from sqlalchemy import or_

    query = select(Festival).where(
        or_(
            Festival.state == FestivalState.FAILED.value,
            Festival.state == FestivalState.VALIDATION_FAILED.value,
            Festival.state == FestivalState.RESEARCHED_PARTIAL.value,
        )
    )

    if failure_reason:
        query = query.where(Festival.failure_reason == failure_reason)
    if min_completeness is not None:
        query = query.where(Festival.research_completeness_score >= min_completeness)
    if max_retry_count is not None:
        query = query.where(Festival.retry_count <= max_retry_count)

    query = query.order_by(Festival.retry_count.asc()).limit(limit).with_for_update()

    result = await db.execute(query)
    festivals = result.scalars().all()

    task_ids = []
    for festival in festivals:
        festival.state = FestivalState.RESEARCHING.value
        festival.state_changed_at = utc_now()
        task = research_pipeline.delay(festival_id=str(festival.id))
        task_ids.append(task.id)

    await db.commit()

    # Calculate daily remaining budget
    from sqlalchemy import func as sa_func

    today_cost_result = await db.execute(
        select(sa_func.sum(CostLog.cost_cents)).where(
            func.date(CostLog.created_at) == utc_now().date()
        )
    )
    today_cost = today_cost_result.scalar() or 0

    return {
        "queued": len(festivals),
        "total_matched": len(festivals),
        "task_ids": task_ids,
        "filters_applied": {
            "failure_reason": failure_reason,
            "limit": limit,
            "min_completeness": min_completeness,
            "max_retry_count": max_retry_count,
        },
        "daily_remaining": max(0, 10000 - today_cost),  # Default 10000 cents daily budget
        "daily_used": today_cost,
        "message": f"Queued {len(festivals)} festivals for research",
    }


@router.get("/festivals/{festival_id}")
async def get_festival(
    festival_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a single festival by ID."""
    result = await db.execute(
        select(Festival)
        .options(selectinload(Festival.event_dates))
        .where(Festival.id == UUID(festival_id))
        .with_for_update()
    )
    festival = result.scalar_one_or_none()

    if not festival:
        raise HTTPException(status_code=404, detail="Festival not found")

    return festival.to_dict()


@router.put("/festivals/{festival_id}")
async def update_festival(
    festival_id: str,
    request: FestivalUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Manually update festival research data.

    This endpoint allows human-in-the-loop to edit festival data,
    particularly for adding missing logos to RESEARCHED_PARTIAL festivals.

    Example:
    ```json
    {
      "research_data": {
        "name": "Festival Name",
        "description": "...",
        "logo_url": "https://...",
        "event_dates": [...]
      },
      "promote_to_researched": true,
      "reason": "Added logo from official website"
    }
    ```
    """
    result = await db.execute(
        select(Festival).where(Festival.id == UUID(festival_id)).with_for_update()
    )
    festival = result.scalar_one_or_none()

    if not festival:
        raise HTTPException(status_code=404, detail="Festival not found")

    previous_state = festival.state
    updated_fields = []

    # Update research_data fields
    if festival.research_data is None:
        festival.research_data = {}

    for key, value in request.research_data.items():
        if value is not None:
            festival.research_data[key] = value
            updated_fields.append(key)

    # If promote_to_researched is True and currently RESEARCHED_PARTIAL, promote to RESEARCHED
    new_state = previous_state
    if (
        request.promote_to_researched
        and previous_state == FestivalState.RESEARCHED_PARTIAL.value
    ):
        # Validate that we now have a logo
        festival_data_dict = festival.research_data
        if festival_data_dict.get("logo_url"):
            new_state = FestivalState.RESEARCHED.value
            festival.state = new_state
            festival.state_changed_at = utc_now()

            # Log the transition
            transition = StateTransition(
                festival_id=festival.id,
                from_state=previous_state,
                to_state=new_state,
                reason=request.reason or "Manual promotion from partial to complete",
            )
            db.add(transition)
        else:
            raise HTTPException(
                status_code=400,
                detail="Cannot promote to RESEARCHED: logo_url is still missing",
            )

    festival.updated_at = utc_now()
    await db.commit()

    return FestivalUpdateResponse(
        festival_id=festival_id,
        message=f"Festival updated successfully" + (
            f" and promoted to {new_state}" if new_state != previous_state else ""
        ),
        previous_state=previous_state,
        new_state=new_state,
        updated_fields=updated_fields,
        timestamp=utc_now().isoformat(),
    )


@router.post("/festivals/{festival_id}/deduplicate")
async def deduplicate_festival(
    festival_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Run deduplication check for a festival."""
    result = await db.execute(
        select(Festival).where(Festival.id == UUID(festival_id)).with_for_update()
    )
    festival = result.scalar_one_or_none()

    if not festival:
        raise HTTPException(status_code=404, detail="Festival not found")

    # Queue deduplication task
    task = deduplication_check.delay(festival_id=festival_id)

    return DeduplicationResultResponse(
        festival_id=festival_id,
        is_duplicate=False,  # Will be determined by task
        confidence=0.0,
        reason="Deduplication check queued",
        action_taken="deduplication_queued",
        auto_queued=False,
    )


@router.post("/festivals/{festival_id}/research")
async def research_festival(
    festival_id: str,
    request: Optional[FestivalActionRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """Queue research task for a festival."""
    result = await db.execute(
        select(Festival).where(Festival.id == UUID(festival_id)).with_for_update()
    )
    festival = result.scalar_one_or_none()

    if not festival:
        raise HTTPException(status_code=404, detail="Festival not found")

    # Update state
    previous_state = festival.state
    festival.state = FestivalState.RESEARCHING.value
    festival.state_changed_at = utc_now()

    # Log transition
    transition = StateTransition(
        festival_id=festival.id,
        from_state=previous_state,
        to_state=FestivalState.RESEARCHING.value,
        reason=request.reason if request else "Manual research trigger",
    )
    db.add(transition)
    await db.commit()

    # Queue research task
    task = research_pipeline.delay(festival_id=festival_id)

    return FestivalActionResponse(
        festival_id=UUID(festival_id),
        action=FestivalAction.RESEARCH,
        result="queued",
        message="Research queued successfully",
        previous_state=previous_state,
        new_state=FestivalState.RESEARCHING.value,
        task_id=task.id,
        queued=True,
    )


@router.post("/festivals/{festival_id}/sync")
async def sync_festival(
    festival_id: str,
    request: Optional[FestivalActionRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """Queue sync task for a festival."""
    result = await db.execute(
        select(Festival).where(Festival.id == UUID(festival_id)).with_for_update()
    )
    festival = result.scalar_one_or_none()

    if not festival:
        raise HTTPException(status_code=404, detail="Festival not found")

    # Validate festival data first
    if festival.research_data:
        validator = PartyMapSyncValidator()
        from src.core.schemas import FestivalData

        try:
            festival_data = FestivalData(**festival.research_data)
            validation = validator.validate(festival_data)

            if not validation.is_valid and validation.status == "invalid":
                raise HTTPException(
                    status_code=400,
                    detail=f"Festival validation failed: {validation.errors}",
                )
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Invalid festival data: {str(e)}"
            )

    # Update state
    previous_state = festival.state
    festival.state = FestivalState.SYNCING.value
    festival.state_changed_at = utc_now()

    # Log transition
    transition = StateTransition(
        festival_id=festival.id,
        from_state=previous_state,
        to_state=FestivalState.SYNCING.value,
        reason=request.reason if request else "Manual sync trigger",
    )
    db.add(transition)
    await db.commit()

    # Queue single festival sync task
    from src.tasks.pipeline import sync_pipeline
    task = sync_pipeline.delay(festival_id=festival_id, force=False)

    return FestivalActionResponse(
        festival_id=UUID(festival_id),
        action=FestivalAction.SYNC,
        result="queued",
        message="Sync queued successfully",
        previous_state=previous_state,
        new_state=FestivalState.SYNCING.value,
        task_id=task.id,
        queued=True,
    )


@router.post("/festivals/{festival_id}/force-sync")
async def force_sync_festival(
    festival_id: str,
    request: Optional[FestivalActionRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Force sync a festival, bypassing validation.

    This allows syncing festivals that are missing required fields like logo.
    Use with caution - only for festivals that genuinely cannot provide certain data.
    """
    result = await db.execute(
        select(Festival).where(Festival.id == UUID(festival_id)).with_for_update()
    )
    festival = result.scalar_one_or_none()

    if not festival:
        raise HTTPException(status_code=404, detail="Festival not found")

    # Update state
    previous_state = festival.state
    festival.state = FestivalState.SYNCING.value
    festival.state_changed_at = utc_now()

    # Log transition with force flag
    transition = StateTransition(
        festival_id=festival.id,
        from_state=previous_state,
        to_state=FestivalState.SYNCING.value,
        reason=(request.reason if request else "Force sync (validation bypassed)"),
    )
    db.add(transition)
    await db.commit()

    # Queue single festival sync task with force flag
    from src.tasks.pipeline import sync_pipeline
    task = sync_pipeline.delay(festival_id=festival_id, force=True)

    return FestivalActionResponse(
        festival_id=UUID(festival_id),
        action=FestivalAction.SYNC,
        result="queued",
        message="Force sync queued - validation bypassed",
        previous_state=previous_state,
        new_state=FestivalState.SYNCING.value,
        task_id=task.id,
        queued=True,
    )


@router.post("/festivals/{festival_id}/skip")
async def skip_festival(
    festival_id: str,
    reason: str = Query(..., description="Reason for skipping"),
    db: AsyncSession = Depends(get_db),
):
    """Skip a festival (mark as excluded)."""
    result = await db.execute(
        select(Festival).where(Festival.id == UUID(festival_id)).with_for_update()
    )
    festival = result.scalar_one_or_none()

    if not festival:
        raise HTTPException(status_code=404, detail="Festival not found")

    previous_state = festival.state
    festival.state = FestivalState.SKIPPED.value
    festival.skip_reason = reason
    festival.state_changed_at = utc_now()
    festival.updated_at = utc_now()

    # Log transition
    transition = StateTransition(
        festival_id=festival.id,
        from_state=previous_state,
        to_state=FestivalState.SKIPPED.value,
        reason=f"Skipped: {reason}",
    )
    db.add(transition)
    await db.commit()

    return FestivalActionResponse(
        festival_id=UUID(festival_id),
        action=FestivalAction.SKIP,
        result="completed",
        message=f"Festival skipped: {reason}",
        previous_state=previous_state,
        new_state=FestivalState.SKIPPED.value,
        queued=False,
    )


@router.post("/festivals/{festival_id}/retry")
async def retry_festival(
    festival_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retry a failed or quarantined festival."""
    result = await db.execute(
        select(Festival).where(Festival.id == UUID(festival_id)).with_for_update()
    )
    festival = result.scalar_one_or_none()

    if not festival:
        raise HTTPException(status_code=404, detail="Festival not found")

    if festival.state not in [
        FestivalState.FAILED.value,
        FestivalState.QUARANTINED.value,
        FestivalState.VALIDATION_FAILED.value,
    ]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry festival in state: {festival.state}",
        )

    previous_state = festival.state
    festival.state = FestivalState.RESEARCHING.value
    festival.retry_count += 1
    festival.last_error = None
    festival.state_changed_at = utc_now()
    festival.updated_at = utc_now()

    # Log transition
    transition = StateTransition(
        festival_id=festival.id,
        from_state=previous_state,
        to_state=FestivalState.RESEARCHING.value,
        reason=f"Manual retry (attempt {festival.retry_count})",
    )
    db.add(transition)
    await db.commit()

    # Queue research task
    task = research_pipeline.delay(festival_id=festival_id)

    return FestivalActionResponse(
        festival_id=UUID(festival_id),
        action=FestivalAction.RETRY,
        result="queued",
        message=f"Retry queued (attempt {festival.retry_count})",
        previous_state=previous_state,
        new_state=FestivalState.RESEARCHING.value,
        task_id=task.id,
        queued=True,
    )


@router.post("/festivals/{festival_id}/reset")
async def reset_festival(
    festival_id: str,
    target_state: Optional[str] = Query(None, description="Target state to reset to"),
    db: AsyncSession = Depends(get_db),
):
    """Reset festival to an earlier state."""
    result = await db.execute(
        select(Festival).where(Festival.id == UUID(festival_id)).with_for_update()
    )
    festival = result.scalar_one_or_none()

    if not festival:
        raise HTTPException(status_code=404, detail="Festival not found")

    previous_state = festival.state

    # Default to DISCOVERED if no target specified
    if not target_state:
        target_state = FestivalState.DISCOVERED.value

    # Validate target state
    valid_reset_states = [
        FestivalState.DISCOVERED.value,
        FestivalState.RESEARCHING.value,
        FestivalState.RESEARCHED.value,
        FestivalState.NEEDS_RESEARCH_NEW.value,
    ]

    if target_state not in valid_reset_states:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid reset state. Must be one of: {valid_reset_states}",
        )

    festival.state = target_state
    festival.state_changed_at = utc_now()
    festival.updated_at = utc_now()

    # Clear errors when resetting
    if target_state in [FestivalState.DISCOVERED.value, FestivalState.RESEARCHING.value]:
        festival.last_error = None
        festival.error_category = None

    # Log transition
    transition = StateTransition(
        festival_id=festival.id,
        from_state=previous_state,
        to_state=target_state,
        reason="Manual reset",
    )
    db.add(transition)
    await db.commit()

    return FestivalActionResponse(
        festival_id=UUID(festival_id),
        action=FestivalAction.RESET,
        result="completed",
        message=f"Festival reset to {target_state}",
        previous_state=previous_state,
        new_state=target_state,
        queued=False,
    )


def _get_suggested_action(festival: Festival) -> FestivalAction:
    """Determine the suggested next action based on festival state."""
    state_actions = {
        FestivalState.DISCOVERED.value: FestivalAction.DEDUPLICATE,
        FestivalState.RESEARCHED.value: FestivalAction.SYNC,
        FestivalState.RESEARCHED_PARTIAL.value: FestivalAction.SYNC,  # Can force sync or edit
        FestivalState.FAILED.value: FestivalAction.RETRY,
        FestivalState.VALIDATION_FAILED.value: FestivalAction.RETRY,
    }
    return state_actions.get(festival.state, FestivalAction.RESEARCH)


def _get_action_description(state: str) -> str:
    """Get human-readable description for an action."""
    descriptions = {
        FestivalState.DISCOVERED.value: "Check for duplicates before researching",
        FestivalState.RESEARCHED.value: "Sync to PartyMap",
        FestivalState.RESEARCHED_PARTIAL.value: "Edit to add logo, or force sync without logo",
        FestivalState.FAILED.value: "Retry research",
        FestivalState.VALIDATION_FAILED.value: "Fix validation errors and retry",
    }
    return descriptions.get(state, "Research this festival")
