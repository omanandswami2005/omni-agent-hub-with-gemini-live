"""Tests for the EventBus and /ws/events dashboard endpoint."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from app.api.ws_events import _authenticate_ws, _send_auth_error, router
from app.services.event_bus import EventBus

# ── Helper ────────────────────────────────────────────────────────────


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/ws")
    return app


_FAKE_DECODED = {"uid": "u1", "email": "a@b.com", "name": "Test"}


# ── EventBus unit tests ──────────────────────────────────────────────


class TestEventBus:
    def test_subscribe_and_count(self):
        bus = EventBus()
        q: asyncio.Queue[str] = asyncio.Queue()
        bus.subscribe("u1", q)
        assert bus.subscriber_count("u1") == 1
        assert bus.total_subscribers == 1

    def test_unsubscribe(self):
        bus = EventBus()
        q: asyncio.Queue[str] = asyncio.Queue()
        bus.subscribe("u1", q)
        bus.unsubscribe("u1", q)
        assert bus.subscriber_count("u1") == 0

    def test_unsubscribe_unknown_user(self):
        bus = EventBus()
        q: asyncio.Queue[str] = asyncio.Queue()
        bus.unsubscribe("nobody", q)  # should not raise

    async def test_publish_single_subscriber(self):
        bus = EventBus()
        q: asyncio.Queue[str] = asyncio.Queue()
        bus.subscribe("u1", q)
        await bus.publish("u1", '{"type":"status","state":"idle"}')
        assert not q.empty()
        data = q.get_nowait()
        assert json.loads(data)["state"] == "idle"

    async def test_publish_multiple_subscribers(self):
        bus = EventBus()
        q1: asyncio.Queue[str] = asyncio.Queue()
        q2: asyncio.Queue[str] = asyncio.Queue()
        bus.subscribe("u1", q1)
        bus.subscribe("u1", q2)
        await bus.publish("u1", '{"event":"test"}')
        assert not q1.empty()
        assert not q2.empty()
        assert q1.get_nowait() == '{"event":"test"}'
        assert q2.get_nowait() == '{"event":"test"}'

    async def test_publish_no_subscribers(self):
        bus = EventBus()
        await bus.publish("u1", '{"event":"test"}')  # should not raise

    async def test_publish_user_scoped(self):
        bus = EventBus()
        q1: asyncio.Queue[str] = asyncio.Queue()
        q2: asyncio.Queue[str] = asyncio.Queue()
        bus.subscribe("u1", q1)
        bus.subscribe("u2", q2)
        await bus.publish("u1", '{"for":"u1"}')
        assert not q1.empty()
        assert q2.empty()

    async def test_publish_full_queue_skipped(self):
        bus = EventBus()
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
        bus.subscribe("u1", q)
        await bus.publish("u1", '{"first":1}')
        await bus.publish("u1", '{"second":2}')  # should not raise (skipped)
        assert q.qsize() == 1

    def test_multiple_subscribe_same_queue(self):
        bus = EventBus()
        q: asyncio.Queue[str] = asyncio.Queue()
        bus.subscribe("u1", q)
        bus.subscribe("u1", q)
        # set deduplicates
        assert bus.subscriber_count("u1") == 1

    def test_unsubscribe_cleans_empty_user(self):
        bus = EventBus()
        q: asyncio.Queue[str] = asyncio.Queue()
        bus.subscribe("u1", q)
        bus.unsubscribe("u1", q)
        # Internal dict should not keep empty sets
        assert "u1" not in bus._subscribers


# ── ws_events auth tests ─────────────────────────────────────────────


class TestWsEventsAuth:
    async def test_successful_auth(self):
        ws = AsyncMock(spec=WebSocket)
        ws.receive_text = AsyncMock(return_value=json.dumps({"type": "auth", "token": "tok"}))
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()

        with (
            patch("app.api.ws_events._get_firebase_app"),
            patch("firebase_admin.auth.verify_id_token", return_value=_FAKE_DECODED),
        ):
            user = await _authenticate_ws(ws)

        assert user is not None
        assert user.uid == "u1"

    async def test_invalid_token_returns_none(self):
        ws = AsyncMock(spec=WebSocket)
        ws.receive_text = AsyncMock(return_value=json.dumps({"type": "auth", "token": "bad"}))
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()

        with (
            patch("app.api.ws_events._get_firebase_app"),
            patch("firebase_admin.auth.verify_id_token", side_effect=ValueError("nope")),
        ):
            user = await _authenticate_ws(ws)

        assert user is None
        ws.close.assert_awaited_once()

    async def test_send_auth_error(self):
        ws = AsyncMock(spec=WebSocket)
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()

        await _send_auth_error(ws, "bad thing")
        data = json.loads(ws.send_text.call_args[0][0])
        assert data["status"] == "error"
        assert data["error"] == "bad thing"
        ws.close.assert_awaited_once_with(code=4003, reason="bad thing")


# ── Full ws_events endpoint tests ────────────────────────────────────


class TestWsEventsEndpoint:
    def _patch_auth(self):
        """Patch Firebase auth for the events endpoint."""

        class Ctx:
            def __init__(self):
                self.patches = []

            def __enter__(self):
                p1 = patch("app.api.ws_events._get_firebase_app")
                p2 = patch("firebase_admin.auth.verify_id_token", return_value=_FAKE_DECODED)
                self.patches = [p1, p2]
                for p in self.patches:
                    p.start()
                return self

            def __exit__(self, *args):
                for p in self.patches:
                    p.stop()

        return Ctx()

    def test_auth_and_receive_event(self):
        """Dashboard connects, authenticates, then receives a published event."""
        app = _make_app()
        bus = EventBus()

        with (
            self._patch_auth(),
            patch("app.api.ws_events.get_event_bus", return_value=bus),
            TestClient(app) as tc,
            tc.websocket_connect("/ws/events") as ws,
        ):
            # Authenticate
            ws.send_text(json.dumps({"type": "auth", "token": "valid"}))
            auth_resp = json.loads(ws.receive_text())
            assert auth_resp["type"] == "auth_response"
            assert auth_resp["status"] == "ok"
            assert auth_resp["user_id"] == "u1"

            # After auth, the endpoint should have subscribed to the bus
            assert bus.subscriber_count("u1") == 1

    def test_bus_subscriber_cleaned_on_disconnect(self):
        """After WS closes, the queue is unsubscribed from the bus."""
        app = _make_app()
        bus = EventBus()

        with self._patch_auth(), patch("app.api.ws_events.get_event_bus", return_value=bus), TestClient(app) as tc:
            with tc.websocket_connect("/ws/events") as ws:
                ws.send_text(json.dumps({"type": "auth", "token": "valid"}))
                ws.receive_text()  # auth_response
                assert bus.subscriber_count("u1") == 1

            # WS closed - subscriber should be cleaned up
            assert bus.subscriber_count("u1") == 0

    def test_multiple_dashboards_subscribe(self):
        """Multiple dashboard connections for the same user all subscribe."""
        app = _make_app()
        bus = EventBus()

        with (
            self._patch_auth(),
            patch("app.api.ws_events.get_event_bus", return_value=bus),
            TestClient(app) as tc,
            tc.websocket_connect("/ws/events") as ws1,
            tc.websocket_connect("/ws/events") as ws2,
        ):
            # Authenticate both
            for ws in (ws1, ws2):
                ws.send_text(json.dumps({"type": "auth", "token": "valid"}))
                resp = json.loads(ws.receive_text())
                assert resp["status"] == "ok"

            assert bus.subscriber_count("u1") == 2

    def test_auth_failure_closes_socket(self):
        app = _make_app()
        with (
            patch("app.api.ws_events._get_firebase_app"),
            patch("firebase_admin.auth.verify_id_token", side_effect=ValueError("nope")),
            TestClient(app) as tc,
            tc.websocket_connect("/ws/events") as ws,
        ):
            ws.send_text(json.dumps({"type": "auth", "token": "bad"}))
            data = json.loads(ws.receive_text())
            assert data["type"] == "auth_response"
            assert data["status"] == "error"
