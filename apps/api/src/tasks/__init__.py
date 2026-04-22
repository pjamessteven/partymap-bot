"""Celery tasks for PartyMap Bot."""

from src.tasks.celery_app import celery_app
from src.tasks.maintenance import cleanup_failed, retry_failed
from src.tasks.pipeline import (
    deduplication_check,
    discovery_pipeline,
    research_pipeline,
    sync_pipeline,
)
from src.tasks.refresh_pipeline import (
    apply_approved_refresh_task,
    refresh_festival_date_task,
    refresh_unconfirmed_dates_task,
)

__all__ = [
    "celery_app",
    "discovery_pipeline",
    "deduplication_check",
    "research_pipeline",
    "sync_pipeline",
    "cleanup_failed",
    "retry_failed",
    "refresh_unconfirmed_dates_task",
    "refresh_festival_date_task",
    "apply_approved_refresh_task",
]
