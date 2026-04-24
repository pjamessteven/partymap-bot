"""Costs API routes for cost tracking."""

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.models import CostLog
from src.utils.utc_now import utc_now

router = APIRouter()


@router.get("/costs")
async def get_costs(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Get cost logs for the last N days."""
    since = utc_now() - timedelta(days=days)

    result = await db.execute(
        select(CostLog)
        .where(CostLog.created_at >= since)
        .order_by(CostLog.created_at.desc())
    )
    logs = result.scalars().all()

    return [
        {
            "id": str(log.id),
            "festival_id": str(log.festival_id) if log.festival_id else None,
            "agent_type": log.agent_type,
            "operation": log.service,
            "cost_cents": log.cost_cents,
            "details": {"description": log.description},
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]
