"""Tests for ConnectionManager — connect, disconnect, broadcast, routing."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.models.client import ClientType
from app.services.connection_manager import ConnectionManager

# ── Helpers ───────────────────────────────────────────────────────────


def _mock_ws() -> AsyncMock:
    """Return an AsyncMock that behaves like a FastAPI WebSocket."""
    ws = AsyncMock()
    ws.send_text = AsyncMock()
    ws.close = AsyncMock()
    return ws


# ── Tests ─────────────────────────────────────────────────────────────


@pytest.fixture
def mgr() -> ConnectionManager:
    return ConnectionManager()


class TestConnect:
    async def test_connect_registers_client(self, mgr):
        ws = _mock_ws()
        await mgr.connect(ws, "u1", ClientType.WEB)
        assert mgr.is_online("u1")
        assert mgr.is_online("u1", ClientType.WEB)

    async def test_connect_replaces_existing_same_type(self, mgr):
        ws1 = _mock_ws()
        ws2 = _mock_ws()
        await mgr.connect(ws1, "u1", ClientType.WEB)
        await mgr.connect(ws2, "u1", ClientType.WEB)
        # Old socket should have been closed
        ws1.close.assert_awaited_once()
        assert mgr.total_connections == 1

    async def test_connect_multiple_client_types(self, mgr):
        await mgr.connect(_mock_ws(), "u1", ClientType.WEB)
        await mgr.connect(_mock_ws(), "u1", ClientType.DESKTOP)
        clients = mgr.get_connected_clients("u1")
        assert len(clients) == 2
        types = {c.client_type for c in clients}
        assert types == {ClientType.WEB, ClientType.DESKTOP}


class TestDisconnect:
    async def test_disconnect_removes_client(self, mgr):
        ws = _mock_ws()
        await mgr.connect(ws, "u1", ClientType.WEB)
        await mgr.disconnect("u1", ClientType.WEB)
        assert not mgr.is_online("u1", ClientType.WEB)
        assert not mgr.is_online("u1")

    async def test_disconnect_nonexistent_is_noop(self, mgr):
        await mgr.disconnect("ghost", ClientType.WEB)  # no error

    async def test_disconnect_one_keeps_others(self, mgr):
        await mgr.connect(_mock_ws(), "u1", ClientType.WEB)
        await mgr.connect(_mock_ws(), "u1", ClientType.MOBILE)
        await mgr.disconnect("u1", ClientType.WEB)
        assert not mgr.is_online("u1", ClientType.WEB)
        assert mgr.is_online("u1", ClientType.MOBILE)


class TestMessaging:
    async def test_send_to_user_broadcasts(self, mgr):
        ws_web = _mock_ws()
        ws_desk = _mock_ws()
        await mgr.connect(ws_web, "u1", ClientType.WEB)
        await mgr.connect(ws_desk, "u1", ClientType.DESKTOP)

        await mgr.send_to_user("u1", '{"type":"status","state":"idle"}')
        ws_web.send_text.assert_awaited_once_with('{"type":"status","state":"idle"}')
        ws_desk.send_text.assert_awaited_once_with('{"type":"status","state":"idle"}')

    async def test_send_to_client_targets_one(self, mgr):
        ws_web = _mock_ws()
        ws_desk = _mock_ws()
        await mgr.connect(ws_web, "u1", ClientType.WEB)
        await mgr.connect(ws_desk, "u1", ClientType.DESKTOP)

        await mgr.send_to_client("u1", ClientType.DESKTOP, '{"msg":"hi"}')
        ws_desk.send_text.assert_awaited_once_with('{"msg":"hi"}')
        ws_web.send_text.assert_not_awaited()

    async def test_send_to_nonexistent_client_is_noop(self, mgr):
        await mgr.send_to_client("u1", ClientType.CHROME, '{"x":1}')  # no error

    async def test_dead_socket_cleaned_on_broadcast(self, mgr):
        ws = _mock_ws()
        ws.send_text.side_effect = RuntimeError("closed")
        await mgr.connect(ws, "u1", ClientType.WEB)

        await mgr.send_to_user("u1", '{"ping":true}')
        # Dead socket should be disconnected
        assert not mgr.is_online("u1", ClientType.WEB)

    async def test_dead_socket_cleaned_on_targeted_send(self, mgr):
        ws = _mock_ws()
        ws.send_text.side_effect = RuntimeError("closed")
        await mgr.connect(ws, "u1", ClientType.MOBILE)

        await mgr.send_to_client("u1", ClientType.MOBILE, '{"x":1}')
        assert not mgr.is_online("u1", ClientType.MOBILE)


class TestQueries:
    async def test_get_connected_clients_empty(self, mgr):
        assert mgr.get_connected_clients("nobody") == []

    async def test_get_connected_clients_returns_info(self, mgr):
        await mgr.connect(_mock_ws(), "u1", ClientType.CHROME)
        clients = mgr.get_connected_clients("u1")
        assert len(clients) == 1
        c = clients[0]
        assert c.user_id == "u1"
        assert c.client_type == ClientType.CHROME
        assert isinstance(c.connected_at, datetime)

    async def test_is_online_false_for_unknown_user(self, mgr):
        assert not mgr.is_online("unknown")

    async def test_total_connections(self, mgr):
        await mgr.connect(_mock_ws(), "u1", ClientType.WEB)
        await mgr.connect(_mock_ws(), "u2", ClientType.DESKTOP)
        await mgr.connect(_mock_ws(), "u2", ClientType.MOBILE)
        assert mgr.total_connections == 3
