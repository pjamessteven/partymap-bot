"""Discovery Query API routes for query management."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.models import DiscoveryQuery

router = APIRouter()


@router.get("/queries")
async def get_queries(
    enabled_only: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    """List discovery queries."""
    query = select(DiscoveryQuery)

    if enabled_only is not None:
        query = query.where(DiscoveryQuery.enabled == enabled_only)

    query = query.order_by(DiscoveryQuery.priority.desc(), DiscoveryQuery.created_at.desc())

    result = await db.execute(query)
    queries = result.scalars().all()

    return [
        {
            "id": str(q.id),
            "query_text": q.query,
            "category": q.category,
            "enabled": q.enabled,
            "last_run_at": q.last_run_at.isoformat() if q.last_run_at else None,
            "run_count": q.run_count,
            "created_at": q.created_at.isoformat() if q.created_at else None,
            "updated_at": q.updated_at.isoformat() if q.updated_at else None,
        }
        for q in queries
    ]


@router.post("/queries")
async def create_query(
    query_text: str = Query(..., alias="query_text"),
    category: str = Query("general"),
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
        "last_run_at": None,
        "run_count": 0,
        "created_at": query.created_at.isoformat() if query.created_at else None,
        "updated_at": query.updated_at.isoformat() if query.updated_at else None,
    }


@router.put("/queries/{query_id}")
async def update_query(
    query_id: str,
    query_text: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Update a discovery query."""
    result = await db.execute(
        select(DiscoveryQuery).where(DiscoveryQuery.id == UUID(query_id))
    )
    query = result.scalar_one_or_none()

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
        "last_run_at": query.last_run_at.isoformat() if query.last_run_at else None,
        "run_count": query.run_count,
        "created_at": query.created_at.isoformat() if query.created_at else None,
        "updated_at": query.updated_at.isoformat() if query.updated_at else None,
    }


@router.delete("/queries/{query_id}")
async def delete_query(query_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a discovery query."""
    result = await db.execute(
        select(DiscoveryQuery).where(DiscoveryQuery.id == UUID(query_id))
    )
    query = result.scalar_one_or_none()

    if not query:
        raise HTTPException(status_code=404, detail="Query not found")

    await db.delete(query)
    await db.commit()

    return {"message": "Query deleted", "id": query_id}


@router.delete("/queries")
async def delete_all_queries(confirm: bool = Query(False), db: AsyncSession = Depends(get_db)):
    """Delete all discovery queries."""
    if not confirm:
        raise HTTPException(status_code=400, detail="Must pass confirm=true")

    result = await db.execute(select(DiscoveryQuery))
    queries = result.scalars().all()
    count = len(queries)

    for q in queries:
        await db.delete(q)
    await db.commit()

    return {"message": f"Deleted {count} queries", "count": count}


@router.post("/queries/{query_id}/enable")
async def enable_query(query_id: str, db: AsyncSession = Depends(get_db)):
    """Enable a discovery query."""
    result = await db.execute(
        select(DiscoveryQuery).where(DiscoveryQuery.id == UUID(query_id))
    )
    query = result.scalar_one_or_none()

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
        "last_run_at": query.last_run_at.isoformat() if query.last_run_at else None,
        "run_count": query.run_count,
        "created_at": query.created_at.isoformat() if query.created_at else None,
        "updated_at": query.updated_at.isoformat() if query.updated_at else None,
    }


@router.post("/queries/{query_id}/disable")
async def disable_query(query_id: str, db: AsyncSession = Depends(get_db)):
    """Disable a discovery query."""
    result = await db.execute(
        select(DiscoveryQuery).where(DiscoveryQuery.id == UUID(query_id))
    )
    query = result.scalar_one_or_none()

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
        "last_run_at": query.last_run_at.isoformat() if query.last_run_at else None,
        "run_count": query.run_count,
        "created_at": query.created_at.isoformat() if query.created_at else None,
        "updated_at": query.updated_at.isoformat() if query.updated_at else None,
    }
