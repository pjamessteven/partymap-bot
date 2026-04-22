"""Celery configuration with database-driven beat schedule."""

from celery import Celery

from src.config import get_settings

settings = get_settings()

# Use separate Redis DBs for broker and backend to avoid key collisions
# Broker (queue): DB 0, Backend (results): DB 1
_broker_url = settings.redis_url.rstrip("/")
_backend_url = _broker_url.replace("/0", "/1") if "/0" in _broker_url else f"{_broker_url}/1"

# Create Celery app
celery_app = Celery(
    "partymap_bot",
    broker=_broker_url,
    backend=_backend_url,
    include=["src.tasks.pipeline", "src.tasks.maintenance", "src.tasks.refresh_pipeline"],
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    worker_prefetch_multiplier=1,
    # Task routes
    task_routes={
        "src.tasks.pipeline.discovery_pipeline": {"queue": "discovery"},
        "src.tasks.pipeline.deduplication_check": {"queue": "dedup"},
        "src.tasks.pipeline.research_pipeline": {"queue": "research"},
        "src.tasks.pipeline.sync_pipeline": {"queue": "sync"},
        "src.tasks.maintenance.cleanup_failed": {"queue": "celery"},
        "src.tasks.refresh_pipeline.refresh_unconfirmed_dates_task": {"queue": "refresh"},
        "src.tasks.refresh_pipeline.refresh_festival_date_task": {"queue": "refresh"},
        "src.tasks.refresh_pipeline.apply_approved_refresh_task": {"queue": "refresh"},
    },
    # Use custom database scheduler - schedule is read from database
    beat_scheduler="src.tasks.scheduler:DatabaseScheduler",
    # No hardcoded beat_schedule - all schedules come from database
    beat_schedule={},
)

# Import tasks to register them
from src.tasks.pipeline import (
    deduplication_check,
    discovery_pipeline,
    research_pipeline,
    sync_pipeline,
)


# Configure structured logging when Celery workers start
@celery_app.on_after_configure.connect
def setup_structlog(sender, **kwargs):
    from src.utils.logging import configure_logging
    configure_logging()

__all__ = [
    "celery_app",
    "discovery_pipeline",
    "deduplication_check",
    "research_pipeline",
    "sync_pipeline",
]
