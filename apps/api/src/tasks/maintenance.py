"""Maintenance tasks for cleanup and housekeeping."""

import logging
from datetime import datetime, timedelta

from celery import shared_task
from sqlalchemy import delete, select

from src.config import get_settings
from src.core.database import AsyncSessionLocal
from src.core.models import Festival, FestivalState

logger = logging.getLogger(__name__)
settings = get_settings()


@shared_task
def cleanup_failed():
    """Clean up old failed festivals."""
    import asyncio

    async def _cleanup():
        async with AsyncSessionLocal() as session:
            # Find festivals past purge date
            cutoff = datetime.utcnow() - timedelta(days=settings.failed_festival_retention_days)

            # Delete old failed festivals
            result = await session.execute(
                delete(Festival)
                .where(Festival.state == FestivalState.FAILED)
                .where(Festival.purge_after < datetime.utcnow())
            )

            await session.commit()

            deleted = result.rowcount
            logger.info(f"Cleaned up {deleted} old failed festivals")

            return {"deleted": deleted}

    return asyncio.run(_cleanup())


@shared_task
def retry_failed():
    """Retry festivals in FAILED state (manual trigger)."""
    import asyncio

    async def _retry():
        async with AsyncSessionLocal() as session:
            from src.tasks.pipeline import research_pipeline

            # Find failed festivals not yet purged
            result = await session.execute(
                select(Festival)
                .where(Festival.state == FestivalState.FAILED)
                .where(Festival.purge_after > datetime.utcnow())
            )
            festivals = result.scalars().all()

            retried = 0
            for festival in festivals:
                # Reset for retry
                festival.state = FestivalState.RESEARCHING
                festival.retry_count = 0
                festival.last_error = None

                # Queue for research
                research_pipeline.delay(str(festival.id))
                retried += 1

            await session.commit()

            logger.info(f"Queued {retried} failed festivals for retry")
            return {"retried": retried}

    return asyncio.run(_cleanup())
