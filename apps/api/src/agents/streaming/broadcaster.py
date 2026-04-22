"""Redis-based broadcaster for multi-user stream viewing."""

import json
import asyncio
from typing import Set, Dict, Callable, Optional
from datetime import datetime
from redis.asyncio import Redis

from src.config import get_settings


class StreamBroadcaster:
    """
    Broadcasts stream events to multiple connected clients via Redis Pub/Sub.
    Enables multiple users to watch the same agent stream in real-time.
    """

    _instance: Optional["StreamBroadcaster"] = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if StreamBroadcaster._initialized:
            return

        self.settings = get_settings()
        self.redis: Optional[Redis] = None
        self._subscribers: Dict[str, Set[Callable]] = {}  # thread_id -> callbacks
        self._pubsub = None
        StreamBroadcaster._initialized = True

    async def connect(self):
        """Initialize Redis connection."""
        if self.redis is None:
            self.redis = Redis.from_url(self.settings.redis_url, decode_responses=True)
            self._pubsub = self.redis.pubsub()

    async def subscribe(self, thread_id: str, callback: Callable[[dict], None]):
        """
        Subscribe to a thread's stream events.

        Args:
            thread_id: The agent thread to watch
            callback: Function to call with each event
        """
        await self.connect()

        if thread_id not in self._subscribers:
            self._subscribers[thread_id] = set()
            # Subscribe to Redis channel
            await self._pubsub.subscribe(f"stream:{thread_id}")
            # Start listener task
            asyncio.create_task(self._listen(thread_id))

        self._subscribers[thread_id].add(callback)

    async def unsubscribe(self, thread_id: str, callback: Callable[[dict], None]):
        """Unsubscribe from a thread."""
        if thread_id in self._subscribers:
            self._subscribers[thread_id].discard(callback)
            if not self._subscribers[thread_id]:
                await self._pubsub.unsubscribe(f"stream:{thread_id}")
                del self._subscribers[thread_id]

    async def broadcast(self, thread_id: str, event: dict):
        """
        Broadcast an event to all subscribers of a thread.

        Args:
            thread_id: The thread to broadcast to
            event: The event data
        """
        await self.connect()

        # Add metadata
        event["broadcast_at"] = datetime.utcnow().isoformat()

        # Publish to Redis
        await self.redis.publish(f"stream:{thread_id}", json.dumps(event))

        # Also notify local subscribers immediately
        if thread_id in self._subscribers:
            for callback in self._subscribers[thread_id]:
                try:
                    callback(event)
                except Exception as e:
                    print(f"Error notifying subscriber: {e}")

    async def _listen(self, thread_id: str):
        """Listen for Redis messages and dispatch to local subscribers."""
        async for message in self._pubsub.listen():
            if message["type"] == "message":
                channel = message["channel"]
                event_thread_id = channel.replace("stream:", "")

                if event_thread_id in self._subscribers:
                    data = json.loads(message["data"])
                    for callback in self._subscribers[event_thread_id]:
                        try:
                            callback(data)
                        except Exception as e:
                            print(f"Error in subscriber callback: {e}")


async def get_broadcaster() -> StreamBroadcaster:
    """Get singleton broadcaster."""
    broadcaster = StreamBroadcaster()
    await broadcaster.connect()
    return broadcaster
