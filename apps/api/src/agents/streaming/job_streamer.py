"""Generic streaming utilities for all pipeline jobs.

This module provides a unified streaming interface for discovery, sync, goabase,
and other background jobs to stream progress to the UI.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from src.agents.streaming import get_broadcaster, StreamPersistenceHandler
from src.core.database import AsyncSessionLocal
from src.core.models import AgentThread
from src.utils.utc_now import utc_now

logger = logging.getLogger(__name__)


class JobStreamer:
    """
    Unified streaming interface for background jobs.
    
    Usage:
        async with JobStreamer("discovery", "discovery_abc123") as streamer:
            streamer.info("Starting discovery...")
            streamer.progress(current=5, total=10)
            streamer.festival_found({"name": "Festival Name", "source_url": "..."})
            streamer.complete(total_found=10)
    """

    def __init__(
        self,
        job_type: str,  # 'discovery', 'sync', 'goabase', 'research'
        thread_id: str,
        festival_id: Optional[str] = None,
    ):
        self.job_type = job_type
        self.thread_id = thread_id
        self.festival_id = festival_id
        self.broadcaster = None
        self.persistence = None
        self.db = None
        self._event_buffer = []
        self._buffer_size = 5

    async def __aenter__(self):
        """Initialize streaming infrastructure."""
        # Initialize broadcaster
        self.broadcaster = await get_broadcaster()
        
        # Initialize persistence
        from uuid import UUID
        fest_id = UUID(self.festival_id) if self.festival_id else None
        self.persistence = StreamPersistenceHandler(self.thread_id, fest_id)
        
        # Create thread record
        self.db = AsyncSessionLocal()
        try:
            thread = AgentThread(
                thread_id=self.thread_id,
                agent_type=self.job_type,
                status="running",
                started_at=utc_now(),
                festival_id=fest_id,
            )
            self.db.add(thread)
            await self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to create job thread record: {e}")
            await self.db.rollback()
        
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup streaming infrastructure."""
        # Flush remaining events
        await self._flush_buffer()
        
        # Update thread status
        if self.db:
            try:
                thread = await self.db.get(AgentThread, self.thread_id)
                if thread:
                    if exc_type:
                        thread.status = "failed"
                        thread.error_message = str(exc_val)
                    else:
                        thread.status = "completed"
                    thread.completed_at = utc_now()
                    await self.db.commit()
            except Exception as e:
                logger.warning(f"Failed to update job thread status: {e}")
            finally:
                await self.db.close()

    async def _emit(self, event_type: str, data: dict):
        """Emit event to both broadcaster and persistence."""
        event = {
            "event": event_type,
            "data": data,
            "timestamp": utc_now().isoformat(),
            "thread_id": self.thread_id,
        }
        
        # Buffer for persistence
        self._event_buffer.append((event_type, data))
        if len(self._event_buffer) >= self._buffer_size:
            await self._flush_buffer()
        
        # Broadcast immediately
        if self.broadcaster:
            try:
                await self.broadcaster.broadcast(self.thread_id, event)
            except Exception as e:
                logger.warning(f"Failed to broadcast job event: {e}")

    async def _flush_buffer(self):
        """Persist buffered events."""
        if not self._event_buffer or not self.persistence:
            return
        
        for event_type, data in self._event_buffer:
            try:
                await self.persistence.on_event({
                    "event": event_type,
                    "data": data,
                })
            except Exception as e:
                logger.warning(f"Failed to persist job event: {e}")
        
        self._event_buffer = []

    # === Convenience methods for common events ===
    
    async def info(self, message: str, **extra):
        """Send an informational message."""
        await self._emit("info", {"message": message, **extra})

    async def progress(self, current: int, total: int, message: str = ""):
        """Send progress update."""
        await self._emit("progress", {
            "current": current,
            "total": total,
            "percent": int((current / total) * 100) if total > 0 else 0,
            "message": message,
        })

    async def festival_found(self, festival_data: dict):
        """Send festival found event."""
        await self._emit("festival_found", festival_data)

    async def festival_synced(self, festival_data: dict):
        """Send festival synced event."""
        await self._emit("festival_synced", festival_data)

    async def complete(self, **result_data):
        """Send completion event."""
        await self._emit("complete", {
            "status": "success",
            **result_data
        })

    async def error(self, error_message: str, **extra):
        """Send error event."""
        await self._emit("error", {
            "message": error_message,
            **extra
        })


async def create_job_thread(job_type: str) -> str:
    """Create a new job thread and return the thread_id."""
    import uuid
    thread_id = f"{job_type}_{uuid.uuid4().hex[:8]}"
    return thread_id
