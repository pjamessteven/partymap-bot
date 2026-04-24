"""Celery signals for automatic job tracking.

These handlers automatically sync JobTracker Redis state with actual
Celery task lifecycle events, so the UI always reflects ground truth.
"""

import logging

from celery.signals import task_failure, task_postrun, task_prerun

from src.core.job_tracker import JobTracker, JobType

logger = logging.getLogger(__name__)

# Map fully-qualified Celery task names to JobType enum values
_TASK_TO_JOB_TYPE = {
    "src.tasks.pipeline.discovery_pipeline": JobType.DISCOVERY,
    "src.tasks.pipeline.research_pipeline": JobType.RESEARCH,
    "src.tasks.pipeline.sync_pipeline": JobType.SYNC,
    "src.tasks.pipeline.run_sync_task": JobType.SYNC,
    "src.tasks.goabase_tasks.goabase_sync_task": JobType.GOABASE_SYNC,
    "src.tasks.refresh_pipeline.refresh_unconfirmed_dates_task": JobType.REFRESH,
    "src.tasks.refresh_pipeline.refresh_festival_date_task": JobType.REFRESH,
}


@task_prerun.connect
def on_task_prerun(sender, task_id, task, args, kwargs, **_):
    """Mark job as running when Celery task starts."""
    job_type = _TASK_TO_JOB_TYPE.get(task.name)
    if not job_type:
        return

    try:
        JobTracker.start_job_sync(
            job_type=job_type,
            task_id=task_id,
            metadata={"args": str(args), "kwargs": str(kwargs)},
        )
    except (ConnectionError, TimeoutError, OSError) as e:
        # Redis connectivity issue — log but don't fail the task
        logger.warning(f"JobTracker start_job_sync failed for {job_type.value}: {e}")
    except Exception as e:
        # Unexpected error — log for diagnostics but don't fail the task
        logger.error(f"Unexpected error in on_task_prerun for {job_type.value}: {e}", exc_info=True)


@task_postrun.connect
def on_task_postrun(sender, task_id, task, args, kwargs, retval, state, **_):
    """Mark job as completed when Celery task finishes successfully."""
    job_type = _TASK_TO_JOB_TYPE.get(task.name)
    if not job_type:
        return

    try:
        if state == "SUCCESS":
            JobTracker.complete_job_sync(
                job_type=job_type,
                result={"retval": str(retval) if retval is not None else None},
            )
        elif state == "FAILURE":
            # task_failure signal will provide the actual exception
            pass
        elif state == "RETRY":
            # Keep as running
            pass
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.warning(f"JobTracker complete_job_sync failed for {job_type.value}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in on_task_postrun for {job_type.value}: {e}", exc_info=True)


@task_failure.connect
def on_task_failure(sender, task_id, exception, args, kwargs, traceback, einfo, **_):
    """Mark job as failed when Celery task fails."""
    job_type = _TASK_TO_JOB_TYPE.get(sender.name)
    if not job_type:
        return

    try:
        error_msg = str(exception) if exception else "Task failed"
        JobTracker.fail_job_sync(job_type=job_type, error=error_msg)
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.warning(f"JobTracker fail_job_sync failed for {job_type.value}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in on_task_failure for {job_type.value}: {e}", exc_info=True)
