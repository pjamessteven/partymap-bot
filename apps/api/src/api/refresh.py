"""API routes for refresh pipeline approvals."""

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.models import RefreshApproval
from src.tasks.refresh_pipeline import apply_approved_refresh_task
from src.utils.utc_now import utc_now

router = APIRouter()


@router.get("/refresh/approvals")
async def list_refresh_approvals(
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List refresh approvals awaiting review."""
    query = select(RefreshApproval).order_by(desc(RefreshApproval.created_at))

    if status:
        query = query.where(RefreshApproval.status == status)
    else:
        # Default to pending
        query = query.where(RefreshApproval.status.in_(["pending", "auto_approved"]))

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    approvals = result.scalars().all()

    return {
        "items": [
            {
                "id": str(a.id),
                "event_id": a.event_id,
                "event_date_id": a.event_date_id,
                "event_name": a.event_name,
                "status": a.status,
                "change_summary": a.change_summary,
                "research_confidence": a.research_confidence,
                "current_data": a.current_data,
                "proposed_changes": a.proposed_changes,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in approvals
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/refresh/approvals/{approval_id}")
async def get_refresh_approval(
    approval_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get details of a specific refresh approval."""
    from uuid import UUID

    try:
        approval_uuid = UUID(approval_id)
    except ValueError:
        raise HTTPException(400, "Invalid approval ID")

    result = await db.execute(
        select(RefreshApproval).where(RefreshApproval.id == approval_uuid)
    )
    approval = result.scalar_one_or_none()

    if not approval:
        raise HTTPException(404, "Approval not found")

    return {
        "id": str(approval.id),
        "event_id": approval.event_id,
        "event_date_id": approval.event_date_id,
        "event_name": approval.event_name,
        "status": approval.status,
        "current_data": approval.current_data,
        "proposed_changes": approval.proposed_changes,
        "change_summary": approval.change_summary,
        "research_confidence": approval.research_confidence,
        "research_sources": approval.research_sources,
        "created_at": approval.created_at.isoformat() if approval.created_at else None,
        "expires_at": approval.expires_at.isoformat() if approval.expires_at else None,
    }


@router.post("/refresh/approvals/{approval_id}/approve")
async def approve_refresh(
    approval_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Approve a refresh and apply changes to PartyMap."""
    from uuid import UUID

    try:
        approval_uuid = UUID(approval_id)
    except ValueError:
        raise HTTPException(400, "Invalid approval ID")

    result = await db.execute(
        select(RefreshApproval).where(RefreshApproval.id == approval_uuid)
    )
    approval = result.scalar_one_or_none()

    if not approval:
        raise HTTPException(404, "Approval not found")

    if approval.status not in ["pending", "auto_approved"]:
        raise HTTPException(400, f"Cannot approve approval with status: {approval.status}")

    # Update approval
    approval.status = "approved"
    approval.approved_at = utc_now()
    approval.approved_by = "api"  # TODO: Get from auth
    await db.commit()

    # Queue task to apply changes
    apply_approved_refresh_task.delay(approval_id)

    return {
        "message": "Refresh approved and changes being applied",
        "approval_id": approval_id,
        "event_name": approval.event_name,
    }


@router.post("/refresh/approvals/{approval_id}/reject")
async def reject_refresh(
    approval_id: str,
    reason: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Reject a refresh approval."""
    from uuid import UUID

    try:
        approval_uuid = UUID(approval_id)
    except ValueError:
        raise HTTPException(400, "Invalid approval ID")

    result = await db.execute(
        select(RefreshApproval).where(RefreshApproval.id == approval_uuid)
    )
    approval = result.scalar_one_or_none()

    if not approval:
        raise HTTPException(404, "Approval not found")

    if approval.status != "pending":
        raise HTTPException(400, f"Cannot reject approval with status: {approval.status}")

    approval.status = "rejected"
    approval.rejection_reason = reason
    await db.commit()

    return {
        "message": "Refresh rejected",
        "approval_id": approval_id,
        "event_name": approval.event_name,
    }


@router.post("/refresh/trigger")
async def trigger_refresh(
    days_ahead: int = 120,
):
    """Manually trigger the refresh pipeline."""
    from src.tasks.refresh_pipeline import refresh_unconfirmed_dates_task

    task = refresh_unconfirmed_dates_task.delay(days_ahead=days_ahead)

    return {
        "message": "Refresh pipeline triggered",
        "task_id": task.id,
        "days_ahead": days_ahead,
    }


@router.get("/refresh/stats")
async def get_refresh_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get refresh pipeline statistics."""
    from sqlalchemy import func

    # Count by status
    result = await db.execute(
        select(RefreshApproval.status, func.count(RefreshApproval.id))
        .group_by(RefreshApproval.status)
    )
    counts = dict(result.all())

    # Pending approvals
    pending = await db.execute(
        select(func.count(RefreshApproval.id))
        .where(RefreshApproval.status == "pending")
    )
    pending_count = pending.scalar()

    # Recent approvals (last 7 days)
    recent = await db.execute(
        select(func.count(RefreshApproval.id))
        .where(RefreshApproval.status.in_(["approved", "applied"]))
        .where(RefreshApproval.created_at >= utc_now() - timedelta(days=7))
    )
    recent_count = recent.scalar()

    return {
        "counts": counts,
        "pending": pending_count,
        "approved_last_7_days": recent_count,
    }
