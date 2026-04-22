"""Redis-based broadcaster for multi-user stream viewing."""

import asyncio
import json
import logging
from typing import Callable, Dict, Optional, Set

from redis.asyncio import Redis

from src.utils.utc_now import utc_now

logger = logging.getLogger(__name__)

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
        self._listener_task: Optional[asyncio.Task] = None
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

        self._subscribers[thread_id].add(callback)

        # Start a single shared listener task if not already running
        if self._listener_task is None or self._listener_task.done():
            self._listener_task = asyncio.create_task(self._listen())

    async def unsubscribe(self, thread_id: str, callback: Callable[[dict], None]):
        """Unsubscribe from a thread."""
        if thread_id in self._subscribers:
            self._subscribers[thread_id].discard(callback)
            if not self._subscribers[thread_id]:
                await self._pubsub.unsubscribe(f"stream:{thread_id}")
                del self._subscribers[thread_id]

        # If no subscribers left, cancel the listener task
        if not self._subscribers and self._listener_task is not None:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

    async def broadcast(self, thread_id: str, event: dict):
        """
        Broadcast an event to all subscribers of a thread.

        Args:
            thread_id: The thread to broadcast to
            event: The event data
        """
        await self.connect()

        # Add metadata
        event["broadcast_at"] = utc_now().isoformat()

        # Publish to Redis
        await self.redis.publish(f"stream:{thread_id}", json.dumps(event))

        # Also notify local subscribers immediately
        if thread_id in self._subscribers:
            for callback in self._subscribers[thread_id]:
                try:
                    callback(event)
                except Exception as e:
                    logger.warning(f"Error notifying subscriber: {e}")

    async def _listen(self):
        """Listen for Redis messages and dispatch to local subscribers."""
        try:
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
                                logger.warning(f"Error in subscriber callback: {e}")
        except asyncio.CancelledError:
            logger.debug("Broadcaster listener task cancelled")
            raise
        except Exception as e:
            logger.error(f"Broadcaster listener task died: {e}")
            raise


async def get_broadcaster() -> StreamBroadcaster:
    """Get singleton broadcaster."""
    broadcaster = StreamBroadcaster()
    await broadcaster.connect()
    return broadcaster
