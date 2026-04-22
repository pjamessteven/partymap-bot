"""Callback handler for persisting stream events to database."""

import json
import uuid
from typing import Any, Optional

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessageChunk, message_to_dict
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal
from src.core.models import AgentStreamEvent, AgentThread
from src.utils.utc_now import utc_now


class StreamPersistenceHandler(AsyncCallbackHandler):
    """
    LangChain callback handler that persists all stream events to PostgreSQL.
    This enables historical loading and multi-user broadcasting.
    """

    def __init__(self, thread_id: str, festival_id: Optional[uuid.UUID] = None):
        self.thread_id = thread_id
        self.festival_id = festival_id
        self.db: Optional[AsyncSession] = None
        self.step_number = 0
        self.event_buffer = []
        self.buffer_size = 10  # Flush every N events

    async def on_chain_start(self, serialized: dict, inputs: dict, **kwargs):
        """Called when graph starts."""
        self.db = AsyncSessionLocal()

        # Create thread record
        thread = AgentThread(
            thread_id=self.thread_id,
            festival_id=self.festival_id,
            agent_type="research",
            status="running",
        )
        self.db.add(thread)
        await self.db.commit()

        await self._save_event(
            event_type="chain_start",
            event_data={"inputs": self._serialize_safe(inputs)},
            run_id=kwargs.get("run_id"),
        )

    async def on_chain_end(self, outputs: dict, **kwargs):
        """Called when graph completes."""
        await self._save_event(
            event_type="chain_end",
            event_data={"outputs": self._serialize_safe(outputs)},
            run_id=kwargs.get("run_id"),
        )

        # Update thread status
        thread = await self.db.get(AgentThread, self.thread_id)
        if thread:
            thread.status = "completed"
            thread.completed_at = utc_now()
            if outputs:
                thread.result_data = self._serialize_safe(outputs)

        await self._flush_buffer()
        await self.db.commit()
        await self.db.close()

    async def on_chain_error(self, error: Exception, **kwargs):
        """Called on error."""
        await self._save_event(
            event_type="error",
            event_data={"error": str(error), "error_type": type(error).__name__},
            run_id=kwargs.get("run_id"),
        )

        thread = await self.db.get(AgentThread, self.thread_id)
        if thread:
            thread.status = "failed"
            thread.error_message = str(error)
            thread.completed_at = utc_now()

        await self._flush_buffer()
        await self.db.commit()
        await self.db.close()

    async def on_llm_start(self, serialized: dict, prompts: list, **kwargs):
        """Called when LLM starts."""
        await self._save_event(
            event_type="llm_start",
            event_data={
                "model": serialized.get("repr", {}).get("model")
                or serialized.get("kwargs", {}).get("model"),
            },
            run_id=kwargs.get("run_id"),
            model_name=serialized.get("repr", {}).get("model"),
        )

    async def on_llm_new_token(self, token: str, **kwargs):
        """Called on each token (streaming)."""
        run_id = kwargs.get("run_id")
        # Build an AIMessageChunk so historical replay works with useStream
        chunk = AIMessageChunk(content=token, id=run_id)
        # LangGraph messages-tuple format: [message_dict, metadata_dict]
        self.event_buffer.append(
            {
                "chunk": message_to_dict(chunk),
                "metadata": {
                    "run_id": run_id,
                    "tags": kwargs.get("tags", []),
                },
            }
        )

        if len(self.event_buffer) >= 50:  # Flush every 50 tokens
            await self._save_event(
                event_type="messages",
                event_data={"items": self.event_buffer},
                run_id=run_id,
            )
            self.event_buffer = []

    async def on_llm_end(self, response, **kwargs):
        """Called when LLM completes."""
        # Flush any remaining tokens
        if self.event_buffer:
            await self._save_event(
                event_type="messages",
                event_data={"items": self.event_buffer},
                run_id=kwargs.get("run_id"),
            )
            self.event_buffer = []

        # Extract usage from OpenRouter response
        usage = {}
        if hasattr(response, "generation_info"):
            usage = response.generation_info.get("token_usage", {})
        elif hasattr(response, "llm_output"):
            usage = response.llm_output.get("token_usage", {})

        event_data = {}
        if usage:
            event_data["usage"] = usage

            # Update thread with token counts
            thread = await self.db.get(AgentThread, self.thread_id)
            if thread:
                thread.prompt_tokens += usage.get("prompt_tokens", 0)
                thread.completion_tokens += usage.get("completion_tokens", 0)
                thread.total_tokens += usage.get("total_tokens", 0)

        await self._save_event(
            event_type="llm_end",
            event_data=event_data,
            run_id=kwargs.get("run_id"),
            usage=usage,
        )

        # Broadcast token usage for live counter
        if usage:
            await self._broadcast({
                "event": "metadata",
                "data": {
                    "usage": usage,
                    "thread_id": self.thread_id,
                },
            })

    async def on_tool_start(self, serialized: dict, input_str: str, **kwargs):
        """Called when tool starts."""
        await self._save_event(
            event_type="tools",
            event_data={
                "event": "on_tool_start",
                "name": serialized.get("name"),
                "input": input_str,
            },
            tool_name=serialized.get("name"),
            tool_call_id=kwargs.get("run_id"),
            run_id=kwargs.get("run_id"),
        )

    async def on_tool_end(self, output: Any, **kwargs):
        """Called when tool completes."""
        await self._save_event(
            event_type="tools",
            event_data={"event": "on_tool_end", "output": self._serialize_safe(output)},
            tool_call_id=kwargs.get("run_id"),
            run_id=kwargs.get("run_id"),
        )

    async def on_custom_event(self, name: str, data: Any, **kwargs):
        """Handle custom events from config.writer()."""
        # This handles tool_progress, reasoning, evaluation, complete events
        event_type = data.get("type", "custom")

        await self._save_event(
            event_type=event_type,
            event_data=data,
            node_name=kwargs.get("metadata", {}).get("langgraph_node"),
            run_id=kwargs.get("run_id"),
            tool_name=data.get("tool_name"),
            tool_call_id=data.get("tool_call_id"),
        )

    async def _save_event(self, **kwargs):
        """Save event to database."""
        event = AgentStreamEvent(thread_id=self.thread_id, **kwargs)
        self.db.add(event)

        # Periodic flush
        if len(self.db.new) >= self.buffer_size:
            await self._flush_buffer()

    async def _flush_buffer(self):
        """Commit pending events."""
        await self.db.commit()

    async def _broadcast(self, data: dict):
        """Broadcast event via Redis if available."""
        try:
            from src.agents.streaming.broadcaster import get_broadcaster
            broadcaster = await get_broadcaster()
            await broadcaster.broadcast(self.thread_id, data)
        except Exception:
            pass  # Broadcasting is best-effort

    def _serialize_safe(self, obj: Any) -> Any:
        """Safely serialize object to JSON-compatible format."""
        try:
            return json.loads(json.dumps(obj, default=str))
        except (TypeError, ValueError):
            return str(obj)
