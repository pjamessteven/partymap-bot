"""API routes for pipeline control - manual start/stop of all services."""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any

from src.pipeline_control import pipeline_manager

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.get("/status")
async def get_all_pipeline_statuses() -> Dict[str, Any]:
    """
    Get status of all pipelines and services.
    
    Returns status, progress, and control options for:
    - Discovery (Exa search)
    - Goabase Sync
    - Research
    - PartyMap Sync
    - Deduplication
    """
    return {
        "status": "success",
        "pipelines": pipeline_manager.get_all_statuses()
    }


@router.get("/{pipeline_key}/status")
async def get_pipeline_status(pipeline_key: str) -> Dict[str, Any]:
    """
    Get status of a specific pipeline.
    
    Valid pipeline keys:
    - discovery
    - goabase_sync
    - research
    - sync
    - deduplication
    """
    status = pipeline_manager.get_status(pipeline_key)
    if not status:
        raise HTTPException(status_code=404, detail=f"Pipeline not found: {pipeline_key}")
    
    return {
        "status": "success",
        "pipeline": status
    }


@router.post("/{pipeline_key}/start")
async def start_pipeline(pipeline_key: str) -> Dict[str, str]:
    """
    Manually start a pipeline.
    
    Valid pipeline keys:
    - discovery: Search for new festivals via Exa
    - goabase_sync: Sync from Goabase API
    - research: Run research agents on pending festivals
    - sync: Sync completed research to PartyMap
    - deduplication: Check PartyMap for duplicates
    """
    valid_pipelines = ["discovery", "goabase_sync", "research", "sync", "deduplication"]
    
    if pipeline_key not in valid_pipelines:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pipeline. Valid options: {', '.join(valid_pipelines)}"
        )
    
    result = await pipeline_manager.start_pipeline(pipeline_key)
    return result


@router.post("/{pipeline_key}/stop")
async def stop_pipeline(pipeline_key: str) -> Dict[str, str]:
    """
    Request a pipeline to stop gracefully.
    
    Sends stop signal to running pipeline. 
    May take a few moments to complete current work.
    """
    valid_pipelines = ["discovery", "goabase_sync", "research", "sync", "deduplication"]
    
    if pipeline_key not in valid_pipelines:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pipeline. Valid options: {', '.join(valid_pipelines)}"
        )
    
    result = await pipeline_manager.stop_pipeline(pipeline_key)
    return result


@router.post("/stop-all")
async def stop_all_pipelines() -> Dict[str, Any]:
    """
    Stop all running pipelines.
    
    Useful for emergency shutdown or maintenance.
    """
    results = {}
    for key in ["discovery", "goabase_sync", "research", "sync", "deduplication"]:
        status = pipeline_manager.get_status(key)
        if status and status["status"] == "running":
            result = await pipeline_manager.stop_pipeline(key)
            results[key] = result
    
    return {
        "status": "success",
        "message": "Stop signals sent to all running pipelines",
        "stopped_pipelines": results
    }
