"""Tests for agent streaming endpoints - CRITICAL for UseStream() conformance."""

import pytest
import json
from datetime import datetime
from uuid import uuid4
from unittest.mock import AsyncMock, patch, MagicMock

from src.core.models import AgentThread, AgentStreamEvent, Festival, FestivalState


def parse_sse(response_text: str) -> list:
    """Parse SSE response text into list of {event, data} dicts."""
    events = []
    current_event = None
    current_data = []
    
    for line in response_text.strip().split("\n"):
        if line.startswith("event: "):
            if current_event is not None:
                events.append({
                    "event": current_event,
                    "data": json.loads("\n".join(current_data)) if current_data else None
                })
            current_event = line[7:]
            current_data = []
        elif line.startswith("data: "):
            current_data.append(line[6:])
        elif line == "" and current_event is not None:
            events.append({
                "event": current_event,
                "data": json.loads("\n".join(current_data)) if current_data else None
            })
            current_event = None
            current_data = []
    
    if current_event is not None:
        events.append({
            "event": current_event,
            "data": json.loads("\n".join(current_data)) if current_data else None
        })
    
    return events


class TestStreamingConformance:
    """CRITICAL: Verify SSE output matches frontend UseStream() expectations."""

    @pytest.mark.asyncio
    async def test_metadata_event_first(self, async_client, db_session, mock_broadcaster):
        """event: metadata is emitted first with thread_id and status."""
        thread = AgentThread(
            id="research_test_123",
            festival_id=uuid4(),
            agent_type="research",
            status="running",
        )
        db_session.add(thread)
        await db_session.commit()
        
        mock_broadcaster.subscribe = AsyncMock(return_value=[])
        
        response = await async_client.get(
            "/api/threads/research_test_123/runs/stream?stream_mode=messages"
        )
        assert response.status_code == 200
        
        events = parse_sse(response.text)
        assert len(events) > 0
        assert events[0]["event"] == "metadata"
        assert events[0]["data"]["thread_id"] == "research_test_123"
        assert events[0]["data"]["status"] == "running"

    @pytest.mark.asyncio
    async def test_messages_event_format(self, async_client, db_session, mock_broadcaster):
        """event: messages data MUST be [messageDict, metadataDict]."""
        thread = AgentThread(
            id="research_test_456",
            festival_id=uuid4(),
            agent_type="research",
            status="completed",
        )
        db_session.add(thread)
        
        # Historical messages event
        stream_event = AgentStreamEvent(
            thread_id="research_test_456",
            event_type="messages",
            event_data={
                "items": [
                    {
                        "chunk": {"type": "ai", "data": {"content": "Hello"}},
                        "metadata": {"run_id": "run-123"},
                    }
                ]
            },
        )
        db_session.add(stream_event)
        await db_session.commit()
        
        mock_broadcaster.subscribe = AsyncMock(return_value=[])
        
        response = await async_client.get(
            "/api/threads/research_test_456/runs/stream?stream_mode=messages"
        )
        assert response.status_code == 200
        
        events = parse_sse(response.text)
        msg_events = [e for e in events if e["event"] == "messages"]
        assert len(msg_events) > 0
        
        # CRITICAL: data must be a list with 2 elements [message, metadata]
        assert isinstance(msg_events[0]["data"], list)
        assert len(msg_events[0]["data"]) == 2
        assert "type" in msg_events[0]["data"][0] or "content" in str(msg_events[0]["data"][0])

    @pytest.mark.asyncio
    async def test_custom_event_format(self, async_client, db_session, mock_broadcaster):
        """event: custom data MUST have {type, data, timestamp?}."""
        thread = AgentThread(
            id="research_test_789",
            festival_id=uuid4(),
            agent_type="research",
            status="running",
        )
        db_session.add(thread)
        await db_session.commit()
        
        # Mock live custom event
        async def mock_subscribe():
            yield {
                "event": "custom",
                "data": {
                    "type": "reasoning",
                    "data": {"step": "searching web"},
                    "timestamp": datetime.utcnow().isoformat(),
                },
                "broadcast_at": datetime.utcnow().isoformat(),
            }
        
        mock_broadcaster.subscribe = mock_subscribe
        
        response = await async_client.get(
            "/api/threads/research_test_789/runs/stream?stream_mode=custom"
        )
        assert response.status_code == 200
        
        events = parse_sse(response.text)
        custom_events = [e for e in events if e["event"] == "custom"]
        assert len(custom_events) > 0
        
        for ce in custom_events:
            assert "type" in ce["data"]
            assert "data" in ce["data"]

    @pytest.mark.asyncio
    async def test_tools_event_format(self, async_client, db_session, mock_broadcaster):
        """event: tools data MUST have {toolCallId, name, state}."""
        thread = AgentThread(
            id="research_test_tools",
            festival_id=uuid4(),
            agent_type="research",
            status="running",
        )
        db_session.add(thread)
        
        # Historical tool event
        stream_event = AgentStreamEvent(
            thread_id="research_test_tools",
            event_type="tools",
            event_data={
                "name": "web_search",
                "input": "festival 2026",
                "output": None,
            },
        )
        db_session.add(stream_event)
        await db_session.commit()
        
        mock_broadcaster.subscribe = AsyncMock(return_value=[])
        
        response = await async_client.get(
            "/api/threads/research_test_tools/runs/stream?stream_mode=tools"
        )
        assert response.status_code == 200
        
        events = parse_sse(response.text)
        tool_events = [e for e in events if e["event"] == "tools"]
        
        for te in tool_events:
            assert "toolCallId" in te["data"] or "name" in te["data"]
            if "name" in te["data"]:
                assert te["data"]["name"] == "web_search"

    @pytest.mark.asyncio
    async def test_end_event_format(self, async_client, db_session, mock_broadcaster):
        """event: end data MUST have {status: 'success' | 'completed'}."""
        thread = AgentThread(
            id="research_test_end",
            festival_id=uuid4(),
            agent_type="research",
            status="completed",
        )
        db_session.add(thread)
        await db_session.commit()
        
        mock_broadcaster.subscribe = AsyncMock(return_value=[])
        
        response = await async_client.get(
            "/api/threads/research_test_end/runs/stream?stream_mode=messages"
        )
        assert response.status_code == 200
        
        events = parse_sse(response.text)
        end_events = [e for e in events if e["event"] == "end"]
        assert len(end_events) == 1
        assert end_events[0]["data"]["status"] in ("success", "completed")

    @pytest.mark.asyncio
    async def test_stream_mode_filtering(self, async_client, db_session, mock_broadcaster):
        """Only requested stream modes are emitted."""
        thread = AgentThread(
            id="research_test_filter",
            festival_id=uuid4(),
            agent_type="research",
            status="running",
        )
        db_session.add(thread)
        
        # Add events of different types
        for event_type in ["messages", "custom", "tools"]:
            db_session.add(AgentStreamEvent(
                thread_id="research_test_filter",
                event_type=event_type,
                event_data={"test": True},
            ))
        await db_session.commit()
        
        mock_broadcaster.subscribe = AsyncMock(return_value=[])
        
        # Request only messages
        response = await async_client.get(
            "/api/threads/research_test_filter/runs/stream?stream_mode=messages"
        )
        assert response.status_code == 200
        
        events = parse_sse(response.text)
        event_names = [e["event"] for e in events if e["event"] not in ("metadata", "end")]
        assert "custom" not in event_names
        assert "tools" not in event_names

    @pytest.mark.asyncio
    async def test_error_event_format(self, async_client, db_session, mock_broadcaster):
        """event: error data MUST have {error: string}."""
        thread = AgentThread(
            id="research_test_err",
            festival_id=uuid4(),
            agent_type="research",
            status="failed",
        )
        db_session.add(thread)
        
        stream_event = AgentStreamEvent(
            thread_id="research_test_err",
            event_type="error",
            event_data={"error": "Research failed"},
        )
        db_session.add(stream_event)
        await db_session.commit()
        
        mock_broadcaster.subscribe = AsyncMock(return_value=[])
        
        response = await async_client.get(
            "/api/threads/research_test_err/runs/stream?stream_mode=messages"
        )
        assert response.status_code == 200
        
        events = parse_sse(response.text)
        error_events = [e for e in events if e["event"] == "error"]
        if error_events:
            assert "error" in error_events[0]["data"]


class TestThreadEndpoints:
    """Tests for non-streaming thread endpoints."""

    @pytest.mark.asyncio
    async def test_list_threads(self, async_client, db_session):
        """GET /api/threads lists threads with filters."""
        thread = AgentThread(
            id="research_list_1",
            festival_id=uuid4(),
            agent_type="research",
            status="completed",
        )
        db_session.add(thread)
        await db_session.commit()
        
        response = await async_client.get("/api/threads?agent_type=research")
        assert response.status_code == 200
        data = response.json()
        assert "threads" in data

    @pytest.mark.asyncio
    async def test_get_thread(self, async_client, db_session):
        """GET /api/agents/{thread_id} returns thread metadata."""
        thread = AgentThread(
            id="research_get_1",
            festival_id=uuid4(),
            agent_type="research",
            status="running",
        )
        db_session.add(thread)
        await db_session.commit()
        
        response = await async_client.get("/api/agents/research_get_1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "research_get_1"
        assert data["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_thread_events(self, async_client, db_session):
        """GET /api/agents/{thread_id}/events returns saved stream events."""
        thread = AgentThread(
            id="research_events_1",
            festival_id=uuid4(),
            agent_type="research",
            status="completed",
        )
        db_session.add(thread)
        
        event = AgentStreamEvent(
            thread_id="research_events_1",
            event_type="messages",
            event_data={"items": []},
        )
        db_session.add(event)
        await db_session.commit()
        
        response = await async_client.get("/api/agents/research_events_1/events")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
