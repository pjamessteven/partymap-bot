"""Discovery API routes for triggering discovery runs."""

import uuid

from fastapi import APIRouter

from src.tasks.pipeline import discovery_pipeline

router = APIRouter()


@router.post("/discovery/run")
async def run_discovery(query: str = None):
    """Trigger a discovery run."""
    thread_id = f"discovery_{uuid.uuid4().hex[:8]}"
    task = discovery_pipeline.delay(manual_query=query, thread_id=thread_id)

    return {
        "message": "Discovery started",
        "task_id": task.id,
        "thread_id": thread_id,
        "query": query,
    }
