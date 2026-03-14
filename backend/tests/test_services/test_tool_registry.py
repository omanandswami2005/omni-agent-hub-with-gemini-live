"""Tests for ConnectionManager capabilities, ToolRegistry, and T3 proxy tools.

Covers:
- ConnectionManager.store_capabilities / get_capabilities / update_capabilities
- Capability cleanup on disconnect
- ToolRegistry.build_for_session (T2 + T3 assembly)
- T3 proxy tool creation and reverse-RPC resolution
- Extended ClientType enum
- Extended WS message models
"""

from __future__ import annotations

import asyncio
import json

import pytest

# ── ConnectionManager Capability Tests ───────────────────────────────


class TestConnectionManagerCapabilities:
    """Tests for the capabilities extension on ConnectionManager."""

    def _make_mgr(self):
        from app.services.connection_manager import ConnectionManager
        return ConnectionManager()

    def test_store_and_get_capabilities(self):
        from app.models.client import ClientType
        mgr = self._make_mgr()

        mgr.store_capabilities(
            "user1",
            ClientType.DESKTOP,
            capabilities=["write_file", "read_file", "capture_screen"],
            local_tools=[
                {"name": "write_file", "description": "Write to disk", "parameters": {"path": {"type": "string"}, "content": {"type": "string"}}},
                {"name": "read_file", "description": "Read from disk", "parameters": {"path": {"type": "string"}}},
            ],
        )

        caps = mgr.get_capabilities("user1")
        assert ClientType.DESKTOP in caps
        assert caps[ClientType.DESKTOP]["capabilities"] == ["write_file", "read_file", "capture_screen"]
        assert len(caps[ClientType.DESKTOP]["local_tools"]) == 2

    def test_get_capabilities_empty_user(self):
        mgr = self._make_mgr()
        assert mgr.get_capabilities("nonexistent") == {}

    def test_store_multiple_clients(self):
        from app.models.client import ClientType
        mgr = self._make_mgr()

        mgr.store_capabilities("user1", ClientType.DESKTOP, ["write_file"], [{"name": "write_file"}])
        mgr.store_capabilities("user1", ClientType.MOBILE, ["send_sms"], [{"name": "send_sms"}])

        caps = mgr.get_capabilities("user1")
        assert len(caps) == 2
        assert ClientType.DESKTOP in caps
        assert ClientType.MOBILE in caps

    def test_update_capabilities_add(self):
        from app.models.client import ClientType
        mgr = self._make_mgr()

        mgr.store_capabilities("user1", ClientType.MOBILE, ["camera"], [])
        mgr.update_capabilities("user1", ClientType.MOBILE, added=["gps", "accelerometer"])

        caps = mgr.get_capabilities("user1")
        assert "camera" in caps[ClientType.MOBILE]["capabilities"]
        assert "gps" in caps[ClientType.MOBILE]["capabilities"]
        assert "accelerometer" in caps[ClientType.MOBILE]["capabilities"]

    def test_update_capabilities_remove(self):
        from app.models.client import ClientType
        mgr = self._make_mgr()

        mgr.store_capabilities("user1", ClientType.MOBILE, ["camera", "gps", "nfc"], [])
        mgr.update_capabilities("user1", ClientType.MOBILE, removed=["nfc"])

        caps = mgr.get_capabilities("user1")
        assert "nfc" not in caps[ClientType.MOBILE]["capabilities"]
        assert "camera" in caps[ClientType.MOBILE]["capabilities"]

    def test_update_capabilities_add_tools(self):
        from app.models.client import ClientType
        mgr = self._make_mgr()

        mgr.store_capabilities("user1", ClientType.DESKTOP, [], [{"name": "write_file"}])
        mgr.update_capabilities(
            "user1", ClientType.DESKTOP,
            added_tools=[{"name": "run_command", "description": "Run shell command"}],
        )

        caps = mgr.get_capabilities("user1")
        tool_names = [t["name"] for t in caps[ClientType.DESKTOP]["local_tools"]]
        assert "write_file" in tool_names
        assert "run_command" in tool_names

    def test_update_capabilities_remove_tools(self):
        from app.models.client import ClientType
        mgr = self._make_mgr()

        mgr.store_capabilities("user1", ClientType.DESKTOP, [], [
            {"name": "write_file"},
            {"name": "read_file"},
        ])
        mgr.update_capabilities("user1", ClientType.DESKTOP, removed_tools=["read_file"])

        caps = mgr.get_capabilities("user1")
        tool_names = [t["name"] for t in caps[ClientType.DESKTOP]["local_tools"]]
        assert "write_file" in tool_names
        assert "read_file" not in tool_names

    def test_update_no_duplicate_tools(self):
        from app.models.client import ClientType
        mgr = self._make_mgr()

        mgr.store_capabilities("user1", ClientType.DESKTOP, [], [{"name": "write_file"}])
        mgr.update_capabilities(
            "user1", ClientType.DESKTOP,
            added_tools=[{"name": "write_file", "description": "duplicate"}],
        )

        caps = mgr.get_capabilities("user1")
        assert len(caps[ClientType.DESKTOP]["local_tools"]) == 1

    @pytest.mark.asyncio
    async def test_disconnect_cleans_capabilities(self):
        from unittest.mock import AsyncMock, MagicMock

        from app.models.client import ClientType

        mgr = self._make_mgr()

        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()
        mock_ws.close = AsyncMock()

        await mgr.connect(mock_ws, "user1", ClientType.DESKTOP)
        mgr.store_capabilities("user1", ClientType.DESKTOP, ["write_file"], [{"name": "write_file"}])

        assert ClientType.DESKTOP in mgr.get_capabilities("user1")

        await mgr.disconnect("user1", ClientType.DESKTOP)

        # Capabilities should be cleaned up
        caps = mgr.get_capabilities("user1")
        assert ClientType.DESKTOP not in caps


# ── ClientType Enum Tests ────────────────────────────────────────────


class TestClientType:
    """Verify extended ClientType enum."""

    def test_original_types(self):
        from app.models.client import ClientType
        assert ClientType.WEB == "web"
        assert ClientType.DESKTOP == "desktop"
        assert ClientType.CHROME == "chrome"
        assert ClientType.MOBILE == "mobile"
        assert ClientType.GLASSES == "glasses"

    def test_new_types(self):
        from app.models.client import ClientType
        assert ClientType.CLI == "cli"
        assert ClientType.TV == "tv"
        assert ClientType.CAR == "car"
        assert ClientType.IOT == "iot"
        assert ClientType.VSCODE == "vscode"
        assert ClientType.BOT == "bot"

    def test_total_count(self):
        from app.models.client import ClientType
        assert len(ClientType) == 11


# ── WS Message Model Tests ──────────────────────────────────────────


class TestWSMessages:
    """Verify new WS message types."""

    def test_auth_message_with_capabilities(self):
        from app.models.ws_messages import AuthMessage
        msg = AuthMessage(
            token="jwt",
            client_type="cli",
            capabilities=["read_file", "write_file"],
            local_tools=[{"name": "write_file", "description": "Write a file"}],
        )
        assert msg.capabilities == ["read_file", "write_file"]
        assert len(msg.local_tools) == 1

    def test_auth_response_with_tools(self):
        from app.models.ws_messages import AuthResponse
        msg = AuthResponse(
            status="ok",
            user_id="u1",
            session_id="s1",
            available_tools=["search", "write_file"],
            other_clients_online=["web", "desktop"],
        )
        data = json.loads(msg.model_dump_json())
        assert data["available_tools"] == ["search", "write_file"]
        assert data["other_clients_online"] == ["web", "desktop"]

    def test_capability_update_message(self):
        from app.models.ws_messages import CapabilityUpdateMessage
        msg = CapabilityUpdateMessage(
            added=["camera"],
            removed=["nfc"],
            added_tools=[{"name": "take_photo"}],
            removed_tools=["scan_nfc"],
        )
        data = json.loads(msg.model_dump_json())
        assert data["type"] == "capability_update"
        assert data["added"] == ["camera"]

    def test_tool_invocation_message(self):
        from app.models.ws_messages import ToolInvocationMessage
        msg = ToolInvocationMessage(
            call_id="abc123",
            tool="write_file",
            args={"path": "/tmp/test.txt", "content": "hello"},
        )
        data = json.loads(msg.model_dump_json())
        assert data["type"] == "tool_invocation"
        assert data["call_id"] == "abc123"
        assert data["tool"] == "write_file"

    def test_tool_result_message(self):
        from app.models.ws_messages import ToolResultMessage
        msg = ToolResultMessage(
            call_id="abc123",
            result={"success": True},
        )
        data = json.loads(msg.model_dump_json())
        assert data["type"] == "tool_result"
        assert data["call_id"] == "abc123"

    def test_tool_result_error(self):
        from app.models.ws_messages import ToolResultMessage
        msg = ToolResultMessage(
            call_id="abc123",
            error="Permission denied",
        )
        data = json.loads(msg.model_dump_json())
        assert data["error"] == "Permission denied"


# ── ToolRegistry Tests ───────────────────────────────────────────────


class TestToolRegistry:
    """Tests for the ToolRegistry orchestrator."""

    def test_singleton(self):
        from app.services.tool_registry import get_tool_registry
        r1 = get_tool_registry()
        r2 = get_tool_registry()
        assert r1 is r2

    def test_get_t3_tool_names_empty(self):
        from app.services.tool_registry import ToolRegistry
        reg = ToolRegistry()
        assert reg.get_t3_tool_names("nonexistent") == []

    def test_get_t3_tool_names_with_capabilities(self):
        import app.services.connection_manager as cm_mod
        import app.services.tool_registry as tr_mod
        from app.models.client import ClientType
        from app.services.connection_manager import ConnectionManager
        from app.services.tool_registry import ToolRegistry

        # Set up a temporary ConnectionManager with capabilities
        mgr = ConnectionManager()
        old_fn = cm_mod.get_connection_manager
        cm_mod.get_connection_manager = lambda: mgr

        try:
            mgr.store_capabilities("user1", ClientType.DESKTOP, [], [
                {"name": "write_file"},
                {"name": "read_file"},
            ])
            mgr.store_capabilities("user1", ClientType.MOBILE, [], [
                {"name": "send_sms"},
            ])

            # Temporarily patch the cm import in tool_registry
            old_cm = tr_mod.get_connection_manager
            tr_mod.get_connection_manager = lambda: mgr

            reg = ToolRegistry()
            names = reg.get_t3_tool_names("user1")
            assert sorted(names) == ["read_file", "send_sms", "write_file"]
        finally:
            cm_mod.get_connection_manager = old_fn
            tr_mod.get_connection_manager = old_cm


# ── T3 Proxy Tool & Reverse-RPC Tests ───────────────────────────────


class TestT3ProxyTools:
    """Tests for T3 proxy tool creation and reverse-RPC resolution."""

    def test_create_proxy_tool(self):
        from app.models.client import ClientType
        from app.services.tool_registry import _create_proxy_tool

        tool_def = {
            "name": "write_file",
            "description": "Write content to a file on the user's desktop",
            "parameters": {
                "path": {"type": "string", "description": "File path"},
                "content": {"type": "string", "description": "File content"},
            },
        }
        tool = _create_proxy_tool(tool_def, "user1", ClientType.DESKTOP)

        # Verify the tool has the right metadata
        assert tool.name == "write_file"

    def test_resolve_tool_result_success(self):
        import asyncio

        from app.services.tool_registry import _pending_results, resolve_tool_result

        loop = asyncio.new_event_loop()
        fut = loop.create_future()
        _pending_results["test_call_1"] = fut

        resolved = resolve_tool_result("test_call_1", {"success": True})
        assert resolved is True
        assert fut.result() == {"success": True}

        # Cleanup
        _pending_results.pop("test_call_1", None)
        loop.close()

    def test_resolve_tool_result_error(self):
        import asyncio

        from app.services.tool_registry import _pending_results, resolve_tool_result

        loop = asyncio.new_event_loop()
        fut = loop.create_future()
        _pending_results["test_call_2"] = fut

        resolved = resolve_tool_result("test_call_2", {}, error="Permission denied")
        assert resolved is True
        assert fut.result() == {"error": "Permission denied"}

        _pending_results.pop("test_call_2", None)
        loop.close()

    def test_resolve_orphaned_call(self):
        from app.services.tool_registry import resolve_tool_result
        resolved = resolve_tool_result("nonexistent_call", {"data": 1})
        assert resolved is False

    @pytest.mark.asyncio
    async def test_await_tool_result_timeout(self):
        from app.services.tool_registry import _await_tool_result

        result = await _await_tool_result("timeout_call", timeout=0.1)
        assert "error" in result
        assert "did not respond" in result["error"]

    @pytest.mark.asyncio
    async def test_await_tool_result_resolved(self):
        from app.services.tool_registry import _await_tool_result, resolve_tool_result

        async def resolve_after_delay():
            await asyncio.sleep(0.05)
            resolve_tool_result("resolved_call", {"file": "/tmp/test.txt"})

        task = asyncio.create_task(resolve_after_delay())
        result = await _await_tool_result("resolved_call", timeout=2)
        await task
        assert result == {"file": "/tmp/test.txt"}

    @pytest.mark.asyncio
    async def test_proxy_tool_client_offline(self):
        import app.services.tool_registry as tr_mod
        from app.models.client import ClientType
        from app.services.connection_manager import ConnectionManager
        from app.services.tool_registry import _create_proxy_tool

        mgr = ConnectionManager()
        old_fn = tr_mod.get_connection_manager
        tr_mod.get_connection_manager = lambda: mgr

        try:
            tool_def = {"name": "write_file", "description": "Write a file", "parameters": {}}
            tool = _create_proxy_tool(tool_def, "user1", ClientType.DESKTOP)

            # Get the underlying function
            fn = tool._func if hasattr(tool, '_func') else None
            if fn:
                result = await fn(path="/tmp/test.txt")
                assert "not connected" in str(result)
        finally:
            tr_mod.get_connection_manager = old_fn


# ── Integration: ToolRegistry Build Session ──────────────────────────


class TestToolRegistryBuildSession:
    """Integration test for ToolRegistry.build_for_session."""

    @pytest.mark.asyncio
    async def test_build_with_t3_tools(self):
        import app.services.tool_registry as tr_mod
        from app.models.client import ClientType
        from app.services.connection_manager import ConnectionManager
        from app.services.tool_registry import ToolRegistry

        mgr = ConnectionManager()
        old_cm = tr_mod.get_connection_manager
        tr_mod.get_connection_manager = lambda: mgr

        try:
            mgr.store_capabilities("user1", ClientType.DESKTOP, [], [
                {"name": "write_file", "description": "Write a file", "parameters": {"path": {"type": "string"}}},
                {"name": "capture_screen", "description": "Take screenshot", "parameters": {}},
            ])

            reg = ToolRegistry()
            tools = await reg.build_for_session("user1")

            # Should contain T3 proxy tools (T2 may be empty if no plugins enabled)
            tool_names = [getattr(t, 'name', '') for t in tools]
            assert "write_file" in tool_names
            assert "capture_screen" in tool_names
        finally:
            tr_mod.get_connection_manager = old_cm


# ── Bug-fix verification tests ──────────────────────────────────────


class TestBugFixes:
    """Tests that verify the audit fixes work correctly."""

    def test_resolve_pops_from_pending(self):
        """Fix #1: resolve_tool_result must pop the call_id to prevent leak."""
        import asyncio

        from app.services.tool_registry import _pending_results, resolve_tool_result

        loop = asyncio.new_event_loop()
        fut = loop.create_future()
        _pending_results["leak_test"] = fut

        resolve_tool_result("leak_test", {"ok": True})
        assert "leak_test" not in _pending_results, "_pending_results should be cleaned after resolve"
        loop.close()

    @pytest.mark.asyncio
    async def test_await_cleans_up_on_timeout(self):
        """_await_tool_result must remove the entry even on timeout."""
        from app.services.tool_registry import _await_tool_result, _pending_results

        await _await_tool_result("cleanup_test", timeout=0.05)
        assert "cleanup_test" not in _pending_results

    def test_proxy_tool_supports_array_and_object_types(self):
        """Fix #9: array/object params must map to list/dict."""
        from app.models.client import ClientType
        from app.services.tool_registry import _create_proxy_tool

        tool_def = {
            "name": "complex_tool",
            "description": "A tool with complex params",
            "parameters": {
                "items": {"type": "array"},
                "config": {"type": "object"},
                "name": {"type": "string"},
            },
        }
        tool = _create_proxy_tool(tool_def, "user1", ClientType.CLI)
        fn = getattr(tool, 'func', None) or getattr(tool, '_func', None)
        assert fn is not None
        annotations = fn.__annotations__
        assert annotations["items"] is list
        assert annotations["config"] is dict
        assert annotations["name"] is str

    def test_safe_parse_json_valid(self):
        """Fix #4: _safe_parse_json handles valid JSON."""
        from app.tools.cross_client import _safe_parse_json
        result = _safe_parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_safe_parse_json_invalid(self):
        """Fix #4: _safe_parse_json returns raw string on invalid JSON."""
        from app.tools.cross_client import _safe_parse_json
        result = _safe_parse_json("not valid json {{{")
        assert result == "not valid json {{{"

    def test_safe_category_valid(self):
        """Fix #5: _safe_category handles valid categories."""
        from app.models.mcp import MCPCategory
        from app.services.mcp_manager import _safe_category
        assert _safe_category("search") == MCPCategory.SEARCH

    def test_safe_category_invalid(self):
        """Fix #5: _safe_category returns OTHER for unknown categories."""
        from app.models.mcp import MCPCategory
        from app.services.mcp_manager import _safe_category
        assert _safe_category("totally_unknown_category") == MCPCategory.OTHER

    def test_event_bus_higher_queue_size(self):
        """Fix #6: event bus queue should be 1024."""
        from app.services.event_bus import EventBus
        bus = EventBus()
        q = bus.create_queue()
        assert q.maxsize == 1024

    def test_plugin_template_not_discovered(self):
        """Fix #10: TEMPLATE.py must be excluded from auto-discovery."""
        from app.services.plugin_registry import PluginRegistry
        reg = PluginRegistry()
        # TEMPLATE has id="my-plugin" — it should NOT be discovered
        assert "my-plugin" not in [m for m in reg._catalog]
