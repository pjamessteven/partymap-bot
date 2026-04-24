"""API routes for error tracking, dead letter queue, and circuit breaker monitoring."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.models import Festival
from src.core.schemas import FestivalData
from src.core.validators import validate_festival_for_sync
from src.services.circuit_breaker import get_all_circuit_breakers, get_circuit_breaker_metrics
from src.services.dead_letter_queue import DeadLetterQueue

router = APIRouter(prefix="/errors", tags=["errors"])


@router.get("/stats")
async def get_error_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get comprehensive error statistics including DLQ and circuit breakers."""
    # DLQ stats
    dlq = DeadLetterQueue(db)
    dlq_stats = await dlq.get_quarantine_stats()

    # Circuit breaker metrics
    cb_metrics = get_circuit_breaker_metrics()

    # Festival error summary
    result = await db.execute(
        select(Festival.error_category, func.count(Festival.id))
        .where(Festival.error_category.isnot(None))
        .group_by(Festival.error_category)
    )
    error_by_category = {cat: count for cat, count in result.all()}

    # Validation summary
    result = await db.execute(
        select(Festival.validation_status, func.count(Festival.id))
        .group_by(Festival.validation_status)
    )
    validation_summary = {status: count for status, count in result.all()}

    return {
        "dlq": dlq_stats,
        "circuit_breakers": cb_metrics,
        "errors_by_category": error_by_category,
        "validation_summary": validation_summary,
    }


@router.get("/quarantined")
async def get_quarantined_festivals(
    limit: int = 50,
    offset: int = 0,
    error_category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get quarantined festivals with filtering."""
    dlq = DeadLetterQueue(db)
    festivals = await dlq.get_quarantined(
        limit=limit, offset=offset, error_category=error_category
    )

    return {
        "items": [
            {
                "id": str(f.id),
                "name": f.name,
                "source": f.source,
                "error_category": f.error_category,
                "quarantine_reason": f.quarantine_reason,
                "quarantined_at": f.quarantined_at.isoformat() if f.quarantined_at else None,
                "retry_count": f.retry_count,
                "validation_status": f.validation_status,
            }
            for f in festivals
        ],
        "total": await dlq.get_quarantined_count(error_category),
        "limit": limit,
        "offset": offset,
    }


@router.post("/quarantined/{festival_id}/retry")
async def retry_quarantined_festival(
    festival_id: str,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Retry a quarantined festival."""
    try:
        festival_uuid = UUID(festival_id)
    except ValueError:
        raise HTTPException(400, "Invalid festival ID")

    dlq = DeadLetterQueue(db)
    result = await dlq.retry(festival_uuid, force=force)

    if not result["success"]:
        raise HTTPException(400, result["message"])

    return result


@router.post("/quarantined/bulk-retry")
async def bulk_retry_quarantined(
    festival_ids: List[str] = Body(..., description="List of festival IDs to retry"),
    force: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Retry multiple quarantined festivals."""
    try:
        uuids = [UUID(fid) for fid in festival_ids]
    except ValueError:
        raise HTTPException(400, "Invalid festival ID in list")

    dlq = DeadLetterQueue(db)
    result = await dlq.bulk_retry(uuids, force=force)

    return result


@router.post("/cleanup")
async def cleanup_expired_quarantined(
    db: AsyncSession = Depends(get_db),
):
    """Clean up quarantined festivals that have expired."""
    dlq = DeadLetterQueue(db)
    count = await dlq.cleanup_expired()

    return {
        "cleaned_up": count,
        "message": f"Removed {count} expired quarantined festivals",
    }


@router.get("/circuit-breakers")
async def get_circuit_breaker_status():
    """Get current status of all circuit breakers."""
    return {
        "breakers": get_circuit_breaker_metrics(),
    }


@router.post("/circuit-breakers/{name}/reset")
async def reset_circuit_breaker(
    name: str,
):
    """Manually reset a circuit breaker to CLOSED state."""
    breakers = get_all_circuit_breakers()
    breaker = breakers.get(name)

    if not breaker:
        raise HTTPException(404, f"Circuit breaker '{name}' not found")

    breaker.reset()

    return {
        "message": f"Circuit breaker '{name}' reset to CLOSED",
        "name": name,
    }


@router.post("/festivals/{festival_id}/validate")
async def validate_festival(
    festival_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Validate a festival's research data for PartyMap sync."""
    try:
        festival_uuid = UUID(festival_id)
    except ValueError:
        raise HTTPException(400, "Invalid festival ID")

    festival = await db.get(Festival, festival_uuid)
    if not festival:
        raise HTTPException(404, "Festival not found")

    if not festival.research_data:
        raise HTTPException(400, "Festival has no research data to validate")

    try:
        festival_data = FestivalData(**festival.research_data)
        validation_result = validate_festival_for_sync(festival_data)
    except Exception as e:
        from src.core.validators import ValidationResult
        validation_result = ValidationResult(
            is_valid=False,
            status="invalid",
            errors=[{"message": str(e)}],
            warnings=[],
            missing_fields=[],
            completeness_score=0.0,
        )

    # Update festival with validation results
    festival.validation_status = validation_result.status
    festival.validation_errors = validation_result.errors
    festival.validation_warnings = validation_result.warnings
    festival.validation_checked_at = func.now()

    await db.commit()

    return {
        "festival_id": festival_id,
        "name": festival.name,
        "validation": validation_result.dict(),
    }
