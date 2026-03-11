"""EventBus - fan-out pub/sub for dashboard event channels.

The live audio pipeline (``ws_live``) publishes events via
``event_bus.publish(user_id, json_str)``.  Each connected
dashboard WebSocket (``ws_events``) subscribes an ``asyncio.Queue``
that receives a copy of every event for that user.

Thread-safety: single asyncio event loop, plain dicts are safe.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from app.utils.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

__all__ = ["EventBus", "get_event_bus"]

# Max events buffered per subscriber queue before back-pressure kicks in.
_DEFAULT_QUEUE_MAXSIZE = 256


class EventBus:
    """Per-user fan-out event distribution with bounded queues."""

    def __init__(self, queue_maxsize: int = _DEFAULT_QUEUE_MAXSIZE) -> None:
        # { user_id: set[asyncio.Queue] }
        self._subscribers: dict[str, set[asyncio.Queue[str]]] = {}
        self._queue_maxsize = queue_maxsize
        self._drop_count: int = 0

    def create_queue(self) -> asyncio.Queue[str]:
        """Create a bounded queue for a new subscriber."""
        return asyncio.Queue(maxsize=self._queue_maxsize)

    def subscribe(self, user_id: str, queue: asyncio.Queue[str]) -> None:
        """Register a queue to receive events for *user_id*."""
        self._subscribers.setdefault(user_id, set()).add(queue)
        logger.debug("event_bus_subscribe", user_id=user_id, total=len(self._subscribers.get(user_id, set())))

    def unsubscribe(self, user_id: str, queue: asyncio.Queue[str]) -> None:
        """Remove a queue from *user_id*'s subscribers."""
        subs = self._subscribers.get(user_id)
        if subs is None:
            return
        subs.discard(queue)
        if not subs:
            self._subscribers.pop(user_id, None)

    async def publish(self, user_id: str, event_json: str) -> None:
        """Send *event_json* to all subscribers for *user_id*.

        Full queues are drained of their oldest item to make room for the
        newest event, so the dashboard always receives the most recent state.
        """
        subs = self._subscribers.get(user_id)
        if not subs:
            return
        for queue in list(subs):
            if queue.full():
                # Drop the oldest event to make room
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                self._drop_count += 1
                if self._drop_count % 100 == 1:
                    logger.warning(
                        "event_bus_queue_full_drop",
                        user_id=user_id,
                        total_drops=self._drop_count,
                    )
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event_json)

    def subscriber_count(self, user_id: str) -> int:
        """Number of active subscribers for a user."""
        return len(self._subscribers.get(user_id, set()))

    @property
    def total_subscribers(self) -> int:
        return sum(len(v) for v in self._subscribers.values())

    @property
    def total_drops(self) -> int:
        return self._drop_count


# ── Module singleton ──────────────────────────────────────────────────

_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
