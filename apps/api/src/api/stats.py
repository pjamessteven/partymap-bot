"""Stats API routes for dashboard overview."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.models import CostLog, Festival, FestivalState
from src.utils.utc_now import utc_now

router = APIRouter()


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get dashboard statistics."""
    # Total festivals
    total_result = await db.execute(select(func.count(Festival.id)))
    total_festivals = total_result.scalar() or 0

    # Count by state
    by_state = {state.value: 0 for state in FestivalState}
    state_result = await db.execute(
        select(Festival.state, func.count(Festival.id)).group_by(Festival.state)
    )
    for state, count in state_result.all():
        by_state[state] = count

    # Pending count (states requiring action)
    pending_states = [
        FestivalState.DISCOVERED.value,
        FestivalState.RESEARCHED.value,
        FestivalState.RESEARCHED_PARTIAL.value,
        FestivalState.VALIDATION_FAILED.value,
        FestivalState.FAILED.value,
    ]
    pending_result = await db.execute(
        select(func.count(Festival.id)).where(Festival.state.in_(pending_states))
    )
    pending_count = pending_result.scalar() or 0

    # Failed count
    failed_result = await db.execute(
        select(func.count(Festival.id)).where(
            Festival.state.in_([FestivalState.FAILED.value, FestivalState.QUARANTINED.value])
        )
    )
    failed_count = failed_result.scalar() or 0

    # Cost tracking
    today = utc_now().date()
    today_cost_result = await db.execute(
        select(func.sum(CostLog.cost_cents)).where(
            func.date(CostLog.created_at) == today
        )
    )
    today_cost_cents = today_cost_result.scalar() or 0

    # Week cost
    from datetime import timedelta
    week_ago = utc_now() - timedelta(days=7)
    week_cost_result = await db.execute(
        select(func.sum(CostLog.cost_cents)).where(CostLog.created_at >= week_ago)
    )
    week_cost_cents = week_cost_result.scalar() or 0

    # Month cost
    month_ago = utc_now() - timedelta(days=30)
    month_cost_result = await db.execute(
        select(func.sum(CostLog.cost_cents)).where(CostLog.created_at >= month_ago)
    )
    month_cost_cents = month_cost_result.scalar() or 0

    return {
        "total_festivals": total_festivals,
        "by_state": by_state,
        "today_cost_cents": today_cost_cents,
        "week_cost_cents": week_cost_cents,
        "month_cost_cents": month_cost_cents,
        "pending_count": pending_count,
        "failed_count": failed_count,
    }
