"""Celery configuration with database-driven beat schedule."""

from celery import Celery

from src.config import get_settings

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "partymap_bot",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.tasks.pipeline", "src.tasks.goabase_sync", "src.tasks.maintenance"],
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
        "src.tasks.goabase_sync.goabase_sync_pipeline": {"queue": "celery"},
        "src.tasks.maintenance.cleanup_failed": {"queue": "celery"},
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
from src.tasks.goabase_sync import goabase_sync_pipeline

__all__ = [
    "celery_app",
    "discovery_pipeline",
    "deduplication_check",
    "research_pipeline",
    "sync_pipeline",
    "goabase_sync_pipeline",
]
