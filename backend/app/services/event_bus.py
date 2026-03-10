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


class EventBus:
    """Per-user fan-out event distribution."""

    def __init__(self) -> None:
        # { user_id: set[asyncio.Queue] }
        self._subscribers: dict[str, set[asyncio.Queue[str]]] = {}

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

        Dead queues (full) are silently skipped — the dashboard will
        get the next event instead of blocking the live pipeline.
        """
        subs = self._subscribers.get(user_id)
        if not subs:
            return
        for queue in list(subs):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event_json)

    def subscriber_count(self, user_id: str) -> int:
        """Number of active subscribers for a user."""
        return len(self._subscribers.get(user_id, set()))

    @property
    def total_subscribers(self) -> int:
        return sum(len(v) for v in self._subscribers.values())


# ── Module singleton ──────────────────────────────────────────────────

_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
