"""Custom Celery Beat scheduler that reads schedule from database."""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from celery.beat import ScheduleEntry, Scheduler
from celery.schedules import crontab

from src.core.database import SessionLocal
from src.core.models import PipelineSchedule
from src.utils.utc_now import utc_now

logger = logging.getLogger(__name__)


class DatabaseScheduler(Scheduler):
    """Custom Celery scheduler that reads schedule from database."""

    # How often to refresh schedule from database (seconds)
    UPDATE_INTERVAL = 60

    # Task mapping: task_type -> full task path
    TASK_MAP = {
        "discovery": "src.tasks.pipeline.discovery_pipeline",
        "goabase_sync": "src.tasks.goabase_tasks.goabase_sync_task",
        "cleanup_failed": "src.tasks.maintenance.cleanup_failed",
        "refresh": "src.tasks.refresh_pipeline.refresh_unconfirmed_dates_task",
    }

    # Queue mapping: task_type -> queue name
    QUEUE_MAP = {
        "discovery": "discovery",
        "goabase_sync": "celery",
        "cleanup_failed": "celery",
        "refresh": "refresh",
    }

    def __init__(self, *args, **kwargs):
        self._last_updated: Optional[datetime] = None
        self._db_session = None
        super().__init__(*args, **kwargs)

    def setup_schedule(self):
        """Initialize schedule from database."""
        self._schedule: Dict[str, ScheduleEntry] = {}
        self.update_schedule()
        logger.info("DatabaseScheduler initialized")

    @property
    def schedule(self) -> Dict[str, ScheduleEntry]:
        """Return current schedule."""
        return self._schedule

    @schedule.setter
    def schedule(self, value):
        """Set schedule (used by parent class)."""
        self._schedule = value

    def update_schedule(self):
        """Refresh schedule from database."""
        session = SessionLocal()
        try:
            # Get all enabled schedules
            schedules = session.query(PipelineSchedule).filter_by(enabled=True).all()

            new_schedule = {}
            for sched in schedules:
                entry = self._create_entry(sched)
                if entry:
                    new_schedule[sched.task_type] = entry
                    logger.debug(f"Added schedule: {sched.task_type}")

            self._schedule = new_schedule
            self._last_updated = utc_now()

            logger.info(f"Schedule refreshed: {len(new_schedule)} active tasks")

        except Exception as e:
            logger.error(f"Failed to update schedule from database: {e}")
        finally:
            session.close()

    def _create_entry(self, sched: PipelineSchedule) -> Optional[ScheduleEntry]:
        """Convert PipelineSchedule to Celery ScheduleEntry."""
        task_path = self.TASK_MAP.get(sched.task_type)
        if not task_path:
            logger.warning(f"Unknown task type: {sched.task_type}")
            return None

        # Build crontab schedule
        try:
            if sched.day_of_week is not None:
                # Weekly schedule
                schedule = crontab(
                    hour=sched.hour, minute=sched.minute, day_of_week=sched.day_of_week
                )
            else:
                # Daily schedule
                schedule = crontab(hour=sched.hour, minute=sched.minute)
        except Exception as e:
            logger.error(f"Invalid schedule for {sched.task_type}: {e}")
            return None

        return ScheduleEntry(
            name=sched.task_type,
            task=task_path,
            schedule=schedule,
            options={"queue": self.QUEUE_MAP.get(sched.task_type, "celery")},
            last_run_at=sched.last_run_at,
        )

    def is_due(self, entry: ScheduleEntry) -> tuple:
        """Check if entry is due and update last_run_at in DB."""
        is_due, next_time = super().is_due(entry)

        if is_due:
            self._update_last_run(entry.name)
            self._calculate_and_save_next_run(entry.name)

        # Refresh from DB periodically
        if (
            self._last_updated
            and (utc_now() - self._last_updated).seconds > self.UPDATE_INTERVAL
        ):
            self.update_schedule()

        return is_due, next_time

    def _update_last_run(self, task_type: str):
        """Update last_run_at and run_count in database."""
        session = SessionLocal()
        try:
            sched = session.query(PipelineSchedule).filter_by(task_type=task_type).first()
            if sched:
                sched.last_run_at = utc_now()
                sched.run_count += 1
                session.commit()
                logger.info(f"Updated last_run_at for {task_type}")
        except Exception as e:
            logger.error(f"Failed to update last_run for {task_type}: {e}")
            session.rollback()
        finally:
            session.close()

    def _calculate_and_save_next_run(self, task_type: str):
        """Calculate and save next_run_at based on schedule."""
        session = SessionLocal()
        try:
            sched = session.query(PipelineSchedule).filter_by(task_type=task_type).first()
            if not sched:
                return

            # Calculate next run time
            now = utc_now()

            if sched.day_of_week is not None:
                # Weekly schedule - find next occurrence of this day
                days_ahead = sched.day_of_week - now.weekday()
                if days_ahead < 0:
                    days_ahead += 7
                next_run = now + timedelta(days=days_ahead)
            else:
                # Daily schedule - next day
                next_run = now + timedelta(days=1)

            # Set the time
            next_run = next_run.replace(
                hour=sched.hour, minute=sched.minute, second=0, microsecond=0
            )

            # If the resulting time is in the past (same day but earlier time), bump to next occurrence
            if next_run <= now:
                if sched.day_of_week is not None:
                    next_run += timedelta(days=7)
                else:
                    next_run += timedelta(days=1)

            sched.next_run_at = next_run
            session.commit()

        except Exception as e:
            logger.error(f"Failed to calculate next_run for {task_type}: {e}")
            session.rollback()
        finally:
            session.close()

    def sync(self):
        """Sync schedule (called periodically by Celery Beat)."""
        # Parent class sync - we handle our own updates
        pass

    def close(self):
        """Close scheduler."""
        super().close()
        logger.info("DatabaseScheduler closed")


def get_scheduler():
    """Factory function to return the DatabaseScheduler class."""
    return DatabaseScheduler
