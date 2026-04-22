"""Pipeline control manager for manual start/stop of all services."""

import logging
from typing import Dict, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from src.utils.utc_now import utc_now
from enum import Enum

logger = logging.getLogger(__name__)


class PipelineStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"  # Stop requested, finishing current work
    ERROR = "error"


@dataclass
class PipelineInfo:
    """Information about a pipeline/service."""
    name: str
    description: str
    status: PipelineStatus = PipelineStatus.IDLE
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress_percentage: int = 0
    current_operation: Optional[str] = None
    total_items: int = 0
    processed_items: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    result_summary: Dict[str, Any] = field(default_factory=dict)
    stop_requested: bool = False
    # Callbacks
    on_start: Optional[Callable] = None
    on_stop: Optional[Callable] = None
    on_status_check: Optional[Callable] = None


class PipelineControlManager:
    """
    Central manager for controlling all pipelines and services.
    
    Provides:
    - Manual start/stop for all services
    - Status tracking and progress
    - Stop signal propagation
    - Result summaries
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._pipelines: Dict[str, PipelineInfo] = {}
            cls._instance._initialize_pipelines()
        return cls._instance
    
    def _initialize_pipelines(self):
        """Initialize all pipeline definitions."""
        self._pipelines = {
            "discovery": PipelineInfo(
                name="Discovery",
                description="Discover new festivals from Exa search",
                on_start=self._start_discovery,
                on_stop=self._stop_discovery,
            ),
            "goabase_sync": PipelineInfo(
                name="Goabase Sync",
                description="Sync festivals from Goabase API",
                on_start=self._start_goabase_sync,
                on_stop=self._stop_goabase_sync,
            ),
            "research": PipelineInfo(
                name="Research",
                description="Research festival details via agents",
                on_start=self._start_research,
                on_stop=self._stop_research,
            ),
            "sync": PipelineInfo(
                name="PartyMap Sync",
                description="Sync festivals to PartyMap",
                on_start=self._start_sync,
                on_stop=self._stop_sync,
            ),
            "deduplication": PipelineInfo(
                name="Deduplication",
                description="Check PartyMap for duplicates",
                on_start=self._start_deduplication,
                on_stop=self._stop_deduplication,
            ),
        }
    
    def get_all_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all pipelines."""
        return {
            key: {
                "name": info.name,
                "description": info.description,
                "status": info.status.value,
                "started_at": info.started_at.isoformat() if info.started_at else None,
                "completed_at": info.completed_at.isoformat() if info.completed_at else None,
                "progress_percentage": info.progress_percentage,
                "current_operation": info.current_operation,
                "total_items": info.total_items,
                "processed_items": info.processed_items,
                "error_count": info.error_count,
                "last_error": info.last_error,
                "result_summary": info.result_summary,
                "stop_requested": info.stop_requested,
                "is_running": info.status == PipelineStatus.RUNNING,
                "can_start": info.status in [PipelineStatus.IDLE, PipelineStatus.ERROR],
                "can_stop": info.status == PipelineStatus.RUNNING,
            }
            for key, info in self._pipelines.items()
        }
    
    def get_status(self, pipeline_key: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific pipeline."""
        if pipeline_key not in self._pipelines:
            return None
        info = self._pipelines[pipeline_key]
        return {
            "name": info.name,
            "description": info.description,
            "status": info.status.value,
            "started_at": info.started_at.isoformat() if info.started_at else None,
            "completed_at": info.completed_at.isoformat() if info.completed_at else None,
            "progress_percentage": info.progress_percentage,
            "current_operation": info.current_operation,
            "total_items": info.total_items,
            "processed_items": info.processed_items,
            "error_count": info.error_count,
            "last_error": info.last_error,
            "result_summary": info.result_summary,
            "stop_requested": info.stop_requested,
        }
    
    async def start_pipeline(self, pipeline_key: str) -> Dict[str, str]:
        """Start a pipeline."""
        if pipeline_key not in self._pipelines:
            return {"status": "error", "message": f"Unknown pipeline: {pipeline_key}"}
        
        info = self._pipelines[pipeline_key]
        
        if info.status == PipelineStatus.RUNNING:
            return {"status": "already_running", "message": f"{info.name} is already running"}
        
        # Reset state
        info.status = PipelineStatus.RUNNING
        info.started_at = utc_now()
        info.completed_at = None
        info.progress_percentage = 0
        info.current_operation = "Starting..."
        info.total_items = 0
        info.processed_items = 0
        info.error_count = 0
        info.last_error = None
        info.result_summary = {}
        info.stop_requested = False
        
        logger.info(f"Starting pipeline: {info.name}")
        
        # Trigger the actual start
        if info.on_start:
            try:
                result = await info.on_start()
                return {"status": "started", "message": f"{info.name} started", "result": result}
            except Exception as e:
                info.status = PipelineStatus.ERROR
                info.last_error = str(e)
                logger.error(f"Failed to start {info.name}: {e}")
                return {"status": "error", "message": str(e)}
        
        return {"status": "started", "message": f"{info.name} started"}
    
    async def stop_pipeline(self, pipeline_key: str) -> Dict[str, str]:
        """Request a pipeline to stop."""
        if pipeline_key not in self._pipelines:
            return {"status": "error", "message": f"Unknown pipeline: {pipeline_key}"}
        
        info = self._pipelines[pipeline_key]
        
        if info.status != PipelineStatus.RUNNING:
            return {"status": "not_running", "message": f"{info.name} is not running"}
        
        info.stop_requested = True
        info.status = PipelineStatus.STOPPING
        info.current_operation = "Stopping..."
        
        logger.info(f"Stop requested for pipeline: {info.name}")
        
        # Trigger the actual stop
        if info.on_stop:
            try:
                result = await info.on_stop()
                return {"status": "stop_requested", "message": f"{info.name} stopping...", "result": result}
            except Exception as e:
                logger.error(f"Error stopping {info.name}: {e}")
                return {"status": "error", "message": str(e)}
        
        return {"status": "stop_requested", "message": f"{info.name} stopping..."}
    
    def update_progress(self, pipeline_key: str, 
                       progress: Optional[int] = None,
                       current: Optional[int] = None,
                       total: Optional[int] = None,
                       operation: Optional[str] = None,
                       error: Optional[str] = None):
        """Update progress for a running pipeline."""
        if pipeline_key not in self._pipelines:
            return
        
        info = self._pipelines[pipeline_key]
        
        if current is not None:
            info.processed_items = current
        if total is not None:
            info.total_items = total
        if operation:
            info.current_operation = operation
        if error:
            info.error_count += 1
            info.last_error = error
        
        # Calculate progress percentage
        if info.total_items > 0:
            info.progress_percentage = min(100, int((info.processed_items / info.total_items) * 100))
        elif progress is not None:
            info.progress_percentage = progress
    
    def complete_pipeline(self, pipeline_key: str, result: Optional[Dict] = None):
        """Mark a pipeline as complete."""
        if pipeline_key not in self._pipelines:
            return
        
        info = self._pipelines[pipeline_key]
        info.status = PipelineStatus.IDLE
        info.completed_at = utc_now()
        info.current_operation = "Complete"
        info.progress_percentage = 100
        info.stop_requested = False
        
        if result:
            info.result_summary = result
        
        logger.info(f"Pipeline completed: {info.name}")
    
    # Pipeline-specific start/stop implementations
    
    async def _start_discovery(self) -> str:
        """Start discovery pipeline."""
        from src.tasks.pipeline import discovery_pipeline
        task = discovery_pipeline.delay()
        return task.id
    
    async def _stop_discovery(self) -> str:
        """Stop discovery pipeline."""
        # Discovery is fast, just let it finish
        return "discovery_stopped"
    
    async def _start_goabase_sync(self) -> str:
        """Start Goabase sync."""
        from src.tasks.goabase_tasks import goabase_sync_task
        task = goabase_sync_task.delay()
        return task.id
    
    async def _stop_goabase_sync(self) -> str:
        """Stop Goabase sync."""
        from src.tasks.goabase_tasks import goabase_sync_stop_task
        task = goabase_sync_stop_task.delay()
        return task.id
    
    async def _start_research(self) -> str:
        """Start research pipeline."""
        from src.tasks.pipeline import research_pipeline
        # Research runs per-festival, queue all pending
        # This would need to be implemented based on your queue system
        return "research_started"
    
    async def _stop_research(self) -> str:
        """Stop research pipeline."""
        return "research_stopped"
    
    async def _start_sync(self) -> str:
        """Start sync pipeline."""
        from src.tasks.pipeline import sync_pipeline
        return "sync_started"
    
    async def _stop_sync(self) -> str:
        """Stop sync pipeline."""
        return "sync_stopped"
    
    async def _start_deduplication(self) -> str:
        """Start deduplication process."""
        # Deduplication happens during discovery
        return "deduplication_started"
    
    async def _stop_deduplication(self) -> str:
        """Stop deduplication."""
        return "deduplication_stopped"


# Singleton instance
pipeline_manager = PipelineControlManager()