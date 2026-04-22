"""API routes for agent streaming."""

import json
import uuid
import asyncio
import logging
from typing import Optional, AsyncGenerator
from datetime import datetime
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from langchain_core.messages import message_to_dict

logger = logging.getLogger(__name__)

from src.agents.research.graph import get_research_graph
from src.agents.research.state import ResearchState
from src.agents.streaming import StreamPersistenceHandler, get_broadcaster
from src.core.database import get_db
from src.core.models import AgentThread, AgentStreamEvent, Festival
from src.config import get_settings

router = APIRouter()


@router.post("/agents/{festival_id}/research/start")
async def start_research_agent(
    festival_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Start a new research agent for a festival.
    Returns a thread_id that can be used to stream or watch the agent.
    """
    # Get festival
    festival = await db.get(Festival, festival_id)
    if not festival:
        raise HTTPException(404, "Festival not found")

    # Generate thread ID
    thread_id = f"research_{festival_id}_{uuid.uuid4().hex[:8]}"

    # Update festival with current thread
    festival.current_thread_id = thread_id
    await db.commit()

    # Create initial state
    initial_state = ResearchState(
        festival_name=festival.name,
        source_url=festival.source_url or "",
        discovered_data=festival.discovered_data,
    )

    # Start graph in background (non-blocking)
    asyncio.create_task(
        _run_research_graph(
            thread_id=thread_id,
            festival_id=festival_id,
            initial_state=initial_state,
        )
    )

    return {
        "thread_id": thread_id,
        "festival_id": str(festival_id),
        "status": "started",
    }


async def _run_research_graph(
    thread_id: str,
    festival_id: uuid.UUID,
    initial_state: ResearchState,
):
    """Run the research graph with persistence and broadcasting."""

    settings = get_settings()

    # Initialize services
    from src.services.browser_service import BrowserService
    from src.services.llm_client import LLMClient
    from src.services.exa_client import ExaClient
    from src.partymap.client import PartyMapClient
    from src.services.musicbrainz_client import MusicBrainzClient
    from src.services.vision_client import VisionClient
    from src.agents.shared.playwright_toolkit import create_playwright_tools

    browser = BrowserService(settings)
    llm = LLMClient(settings)
    exa = ExaClient(settings)
    partymap = PartyMapClient(settings)
    musicbrainz = MusicBrainzClient(settings)
    vision = VisionClient(settings)  # GPT-4o-mini for image description
    
    # Create Playwright tools from toolkit
    try:
        playwright_tools = await create_playwright_tools(
            headless=settings.browser_headless,
            slow_mo=settings.browser_slow_mo
        )
        logger.info(f"Created {len(playwright_tools)} Playwright toolkit tools")
    except Exception as e:
        logger.warning(f"Could not create Playwright toolkit tools: {e}")
        playwright_tools = []

    # Start browser
    await browser.start()

    # Persistence handler
    persistence = StreamPersistenceHandler(thread_id, festival_id)

    # Broadcaster
    broadcaster = await get_broadcaster()

    try:
        # Get graph
        graph = get_research_graph()

        # Configuration
        config = {
            "configurable": {"thread_id": thread_id},
            "browser": browser,
            "llm": llm,
            "exa": exa,
            "partymap": partymap,
            "musicbrainz": musicbrainz,
            "vision": vision,  # GPT-4o-mini for image description
            "settings": settings,
            "callbacks": [persistence],
            "writer": lambda data: asyncio.create_task(
                broadcaster.broadcast(thread_id, data)
            ),
        }

        # Run graph with streaming
        async for event in graph.astream(
            initial_state,
            config=config,
            stream_mode=["updates", "messages", "tools", "custom"],
        ):
            # Broadcast to all connected clients
            await broadcaster.broadcast(
                thread_id, {"type": "stream_event", "event": event}
            )

        # Final success broadcast
        await broadcaster.broadcast(
            thread_id, {"type": "stream_complete", "status": "success"}
        )

    except Exception as e:
        await broadcaster.broadcast(
            thread_id, {"type": "stream_error", "error": str(e)}
        )
        raise
    finally:
        await browser.close()
        await llm.close()
        await exa.close()
        await partymap.close()
        await musicbrainz.close()
        await vision.close()


@router.websocket("/agents/{thread_id}/ws")
async def agent_websocket(websocket: WebSocket, thread_id: str):
    """
    WebSocket endpoint for real-time stream viewing.
    Supports multiple concurrent viewers of the same stream.
    """
    await websocket.accept()

    # Get broadcaster
    broadcaster = await get_broadcaster()

    # Callback to forward events to this WebSocket
    async def on_event(event: dict):
        try:
            await websocket.send_json(event)
        except:
            pass  # Client disconnected

    # Subscribe to thread
    await broadcaster.subscribe(thread_id, on_event)

    try:
        # Keep connection alive and handle client messages
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            if data.get("action") == "stop":
                # Handle stop request
                pass
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.unsubscribe(thread_id, on_event)


@router.get("/agents/{thread_id}/events")
async def get_stream_events(
    thread_id: str,
    after: Optional[str] = None,  # ISO timestamp
    db: AsyncSession = Depends(get_db),
):
    """
    Get all events for a stream (for historical loading).
    This is NOT a replay - it just loads the saved events.
    """
    query = select(AgentStreamEvent).where(AgentStreamEvent.thread_id == thread_id)

    if after:
        from datetime import datetime

        after_dt = datetime.fromisoformat(after)
        query = query.where(AgentStreamEvent.timestamp > after_dt)

    query = query.order_by(AgentStreamEvent.timestamp)

    result = await db.execute(query)
    events = result.scalars().all()

    return {
        "thread_id": thread_id,
        "events": [
            {
                "id": str(e.id),
                "type": e.event_type,
                "data": e.event_data,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "node_name": e.node_name,
                "tool_name": e.tool_name,
                "tool_call_id": e.tool_call_id,
            }
            for e in events
        ],
    }


@router.get("/agents/{thread_id}")
async def get_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get thread metadata and status."""
    result = await db.execute(
        select(AgentThread).where(AgentThread.thread_id == thread_id)
    )
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(404, "Thread not found")

    return {
        "thread_id": thread.thread_id,
        "festival_id": str(thread.festival_id) if thread.festival_id else None,
        "agent_type": thread.agent_type,
        "status": thread.status,
        "started_at": thread.started_at.isoformat() if thread.started_at else None,
        "completed_at": thread.completed_at.isoformat() if thread.completed_at else None,
        "total_tokens": thread.total_tokens,
        "cost_cents": thread.cost_cents,
        "result_data": thread.result_data,
    }


@router.get("/festivals/{festival_id}/streams")
async def get_festival_streams(
    festival_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get all streams for a festival."""
    result = await db.execute(
        select(AgentThread)
        .where(AgentThread.festival_id == festival_id)
        .order_by(AgentThread.started_at.desc())
    )
    threads = result.scalars().all()

    return {
        "items": [
            {
                "thread_id": t.thread_id,
                "agent_type": t.agent_type,
                "status": t.status,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "total_tokens": t.total_tokens,
            }
            for t in threads
        ]
    }


# ==================== LangGraph-Compatible Streaming Endpoints ====================


@router.get("/threads")
async def list_threads(
    status: Optional[str] = Query(None, description="Filter by status: running, completed, failed"),
    agent_type: Optional[str] = Query(None, description="Filter by agent type: research, discovery"),
    festival_id: Optional[uuid.UUID] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List agent threads for UI thread selector.
    
    Compatible with LangGraph's thread listing API.
    """
    query = select(AgentThread).order_by(desc(AgentThread.started_at))

    if status:
        query = query.where(AgentThread.status == status)
    if agent_type:
        query = query.where(AgentThread.agent_type == agent_type)
    if festival_id:
        query = query.where(AgentThread.festival_id == festival_id)

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    threads = result.scalars().all()

    return {
        "threads": [
            {
                "thread_id": t.thread_id,
                "agent_type": t.agent_type,
                "status": t.status,
                "festival_id": str(t.festival_id) if t.festival_id else None,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                "total_tokens": t.total_tokens,
                "cost_cents": t.cost_cents,
                "result_data": t.result_data,
            }
            for t in threads
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/threads/{thread_id}/runs/stream")
async def stream_run(
    thread_id: str,
    stream_mode: str = Query("messages", description="Stream mode: messages, updates, values, events, debug"),
    db: AsyncSession = Depends(get_db),
):
    """
    LangGraph-compatible SSE streaming endpoint.
    
    Streams agent events in real-time using Server-Sent Events (SSE).
    Compatible with LangGraph's useStream hook and AI Elements.
    
    Args:
        thread_id: The thread ID to stream
        stream_mode: Comma-separated list of stream modes (messages,updates,values,events,debug)
    
    Returns:
        text/event-stream with LangGraph-formatted events
    """
    # Check if thread exists
    result = await db.execute(
        select(AgentThread).where(AgentThread.thread_id == thread_id)
    )
    thread = result.scalar_one_or_none()
    
    if not thread:
        raise HTTPException(404, "Thread not found")

    async def event_stream() -> AsyncGenerator[str, None]:
        """Generate SSE events from stored events and live updates."""
        
        # Parse stream modes
        modes = set(stream_mode.split(","))
        
        # Send initial connection event
        yield f"event: metadata\ndata: {json.dumps({'thread_id': thread_id, 'status': thread.status})}\n\n"
        
        # Get historical events for replay
        events_result = await db.execute(
            select(AgentStreamEvent)
            .where(AgentStreamEvent.thread_id == thread_id)
            .order_by(AgentStreamEvent.timestamp)
        )
        historical_events = events_result.scalars().all()
        
        # Replay historical events in LangGraph format
        for event in historical_events:
            langgraph_event = _convert_to_langgraph_event(event, modes)
            if langgraph_event:
                yield f"event: {langgraph_event['event']}\ndata: {json.dumps(langgraph_event['data'])}\n\n"
        
        # If thread is still running, subscribe to live updates
        if thread.status == "running":
            broadcaster = await get_broadcaster()
            event_queue = asyncio.Queue()
            
            def on_live_event(data: dict):
                # Use asyncio.create_task to safely add to queue from sync callback
                try:
                    asyncio.get_event_loop().create_task(event_queue.put(data))
                except:
                    pass
            
            # Subscribe to live updates
            await broadcaster.subscribe(thread_id, on_live_event)
            
            try:
                while True:
                    # Wait for live events with timeout
                    try:
                        live_data = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                        
                        # Convert live event to LangGraph format
                        if "event" in live_data:
                            langgraph_event = _convert_live_event_to_langgraph(live_data, modes)
                            if langgraph_event:
                                yield f"event: {langgraph_event['event']}\ndata: {json.dumps(langgraph_event['data'])}\n\n"
                        
                        # Check if thread completed
                        if live_data.get("type") == "stream_complete":
                            yield f"event: end\ndata: {json.dumps({'status': 'success'})}\n\n"
                            break
                        elif live_data.get("type") == "stream_error":
                            yield f"event: error\ndata: {json.dumps({'error': live_data.get('error')})}\n\n"
                            break
                            
                    except asyncio.TimeoutError:
                        # Send keepalive
                        yield f"event: ping\ndata: {json.dumps({'timestamp': datetime.utcnow().isoformat()})}\n\n"
                        
            finally:
                await broadcaster.unsubscribe(thread_id, on_live_event)
        else:
            # Thread already completed, send end event
            yield f"event: end\ndata: {json.dumps({'status': thread.status})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        },
    )


def _convert_to_langgraph_event(event: AgentStreamEvent, modes: set) -> Optional[dict]:
    """Convert stored AgentStreamEvent to LangGraph SSE format."""
    
    # Map internal event types to LangGraph events
    if event.event_type == "messages" and "messages" in modes:
        return {
            "event": "messages",
            "data": {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": event.event_data,
                },
                "run_id": event.run_id,
            }
        }
    
    elif event.event_type == "tools" and "updates" in modes:
        tool_event = event.event_data.get("event", "on_tool_start")
        return {
            "event": "updates",
            "data": {
                "event": tool_event,
                "name": event.tool_name or event.event_data.get("name"),
                "data": event.event_data,
                "run_id": event.run_id,
            }
        }
    
    elif event.event_type in ("reasoning", "evaluation") and "custom" in modes:
        return {
            "event": "custom",
            "data": {
                "type": event.event_type,
                "data": event.event_data,
                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
            }
        }
    
    elif event.event_type == "chain_start" and "debug" in modes:
        return {
            "event": "debug",
            "data": {
                "type": "chain_start",
                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
            }
        }
    
    elif event.event_type == "chain_end" and "debug" in modes:
        return {
            "event": "debug",
            "data": {
                "type": "chain_end",
                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
            }
        }
    
    return None


def _convert_live_event_to_langgraph(live_data: dict, modes: set) -> Optional[dict]:
    """Convert live broadcast event to LangGraph SSE format."""
    event_data = live_data.get("event", {})
    
    # Already in LangGraph format from graph.astream
    if isinstance(event_data, tuple) and len(event_data) >= 2:
        event_type, data = event_data[0], event_data[1]
        
        if event_type == "messages" and "messages" in modes:
            return {
                "event": "messages",
                "data": {
                    "event": "on_chat_model_stream",
                    "data": {"chunk": data},
                }
            }
        elif event_type == "updates" and "updates" in modes:
            return {
                "event": "updates",
                "data": data,
            }
        elif event_type == "tools" and "updates" in modes:
            return {
                "event": "updates",
                "data": {
                    "event": "on_tool_call",
                    "data": data,
                }
            }
        elif event_type == "custom" and "custom" in modes:
            return {
                "event": "custom",
                "data": data,
            }
    
    return None


@router.post("/threads/{festival_id}/runs")
async def start_thread_run(
    festival_id: uuid.UUID,
    agent_type: str = Query("research", description="Agent type: research, discovery"),
    db: AsyncSession = Depends(get_db),
):
    """
    Start a new agent run (LangGraph-compatible).
    
    Creates a new thread and starts the agent, returning the thread_id
    for streaming via /threads/{id}/runs/stream.
    """
    # Get festival
    festival = await db.get(Festival, festival_id)
    if not festival:
        raise HTTPException(404, "Festival not found")

    # Generate thread ID
    thread_id = f"{agent_type}_{festival_id}_{uuid.uuid4().hex[:8]}"

    # Update festival with current thread
    festival.current_thread_id = thread_id

    # Create thread record
    thread = AgentThread(
        thread_id=thread_id,
        festival_id=festival_id,
        agent_type=agent_type,
        status="running",
    )
    db.add(thread)
    await db.commit()

    # Start agent based on type
    if agent_type == "research":
        initial_state = ResearchState(
            festival_name=festival.name,
            source_url=festival.source_url or "",
            discovered_data=festival.discovered_data,
        )

        asyncio.create_task(
            _run_research_graph(
                thread_id=thread_id,
                festival_id=festival_id,
                initial_state=initial_state,
            )
        )
    else:
        raise HTTPException(400, f"Unsupported agent type: {agent_type}")

    return {
        "thread_id": thread_id,
        "festival_id": str(festival_id),
        "agent_type": agent_type,
        "status": "running",
        "stream_url": f"/api/v1/threads/{thread_id}/runs/stream",
    }
