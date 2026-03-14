"""Tests for PluginRegistry — MCP, native, lazy loading, catalog."""

from __future__ import annotations

import sys

import pytest

from app.models.plugin import (
    PluginCategory,
    PluginKind,
    PluginManifest,
    PluginState,
    PluginToggle,
    ToolSummary,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the global PluginRegistry singleton between tests."""
    import app.services.plugin_registry as mod

    old = mod._registry
    mod._registry = None
    yield
    mod._registry = old


@pytest.fixture()
def registry():
    from app.services.plugin_registry import PluginRegistry

    return PluginRegistry()


# ── Catalog tests ──────────────────────────────────────────────────


class TestCatalog:
    def test_catalog_has_builtin_plugins(self, registry):
        catalog = registry.get_catalog()
        ids = [p.id for p in catalog]
        assert "e2b-sandbox" in ids
        assert "wikipedia" in ids

    def test_auto_discovers_native_plugins(self, registry):
        catalog = registry.get_catalog()
        ids = [p.id for p in catalog]
        assert "notification-sender" in ids

    def test_catalog_ids_unique(self, registry):
        catalog = registry.get_catalog()
        ids = [p.id for p in catalog]
        assert len(ids) == len(set(ids))

    def test_register_plugin_dynamically(self, registry):
        registry.register_plugin(
            PluginManifest(
                id="test-dynamic",
                name="Test Dynamic",
                kind=PluginKind.NATIVE,
                module="app.plugins.notification_sender",
                factory="get_tools",
            )
        )
        ids = [p.id for p in registry.get_catalog()]
        assert "test-dynamic" in ids

    def test_catalog_default_state_is_available(self, registry):
        catalog = registry.get_catalog("user1")
        for p in catalog:
            assert p.state == PluginState.AVAILABLE


# ── MCP stdio tests (local Python MCP server) ─────────────────────


class TestMCPStdio:
    @pytest.fixture()
    def mcp_manifest(self):
        return PluginManifest(
            id="local-test-mcp",
            name="Local Test MCP",
            description="Test MCP server with echo/time/calculate tools",
            category=PluginCategory.DEV,
            kind=PluginKind.MCP_STDIO,
            command=sys.executable,
            args=["scripts/local_mcp_server.py"],
        )

    @pytest.mark.asyncio
    async def test_connect_discovers_tools(self, registry, mcp_manifest):
        registry.register_plugin(mcp_manifest)
        success = await registry.connect_plugin("u1", "local-test-mcp")
        assert success

        catalog = registry.get_catalog("u1")
        status = next(p for p in catalog if p.id == "local-test-mcp")
        assert status.state == PluginState.CONNECTED
        tool_names = [t.name for t in status.tools_summary]
        assert "echo" in tool_names
        assert "get_server_time" in tool_names
        assert "calculate" in tool_names

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_get_tools_returns_adk_tools(self, registry, mcp_manifest):
        registry.register_plugin(mcp_manifest)
        await registry.connect_plugin("u1", "local-test-mcp")

        tools = await registry.get_tools("u1")
        assert len(tools) == 3
        names = {t.name for t in tools}
        assert names == {"echo", "get_server_time", "calculate"}

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_tool_call_works(self, registry, mcp_manifest):
        registry.register_plugin(mcp_manifest)
        await registry.connect_plugin("u1", "local-test-mcp")

        tools = await registry.get_tools("u1")
        echo = next(t for t in tools if t.name == "echo")
        result = await echo.run_async(args={"message": "pytest works!"}, tool_context=None)
        assert "Echo: pytest works!" in str(result)

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_tool_schemas_have_parameters(self, registry, mcp_manifest):
        registry.register_plugin(mcp_manifest)
        await registry.connect_plugin("u1", "local-test-mcp")

        schemas = await registry.get_tool_schemas("local-test-mcp", "u1")
        assert len(schemas) == 3

        calc_schema = next(s for s in schemas if s.name == "calculate")
        assert "properties" in calc_schema.parameters
        assert "operation" in calc_schema.parameters["properties"]
        assert "a" in calc_schema.parameters["properties"]
        assert "b" in calc_schema.parameters["properties"]

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up(self, registry, mcp_manifest):
        registry.register_plugin(mcp_manifest)
        await registry.connect_plugin("u1", "local-test-mcp")
        await registry.disconnect_plugin("u1", "local-test-mcp")

        catalog = registry.get_catalog("u1")
        status = next(p for p in catalog if p.id == "local-test-mcp")
        assert status.state == PluginState.AVAILABLE

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_toggle_on_off(self, registry, mcp_manifest):
        registry.register_plugin(mcp_manifest)

        # Toggle on
        result = await registry.toggle_plugin(
            "u1", PluginToggle(plugin_id="local-test-mcp", enabled=True)
        )
        assert result is True
        assert "local-test-mcp" in registry.get_enabled_ids("u1")

        # Toggle off
        result = await registry.toggle_plugin(
            "u1", PluginToggle(plugin_id="local-test-mcp", enabled=False)
        )
        assert result is False
        assert "local-test-mcp" not in registry.get_enabled_ids("u1")

        await registry.shutdown()


# ── Native plugin tests ────────────────────────────────────────────


class TestNativePlugin:
    @pytest.mark.asyncio
    async def test_connect_native_plugin(self, registry):
        success = await registry.connect_plugin("u1", "notification-sender")
        assert success

        tools = await registry.get_tools("u1")
        names = {t.name for t in tools}
        assert "send_notification" in names
        assert "list_notification_channels" in names

        await registry.shutdown()


# ── Lazy loading tests ─────────────────────────────────────────────


class TestLazyLoading:
    def test_summaries_before_connect(self, registry):
        """E2B sandbox has pre-declared summaries even before connecting."""
        registry._user_enabled.setdefault("u1", {})["e2b-sandbox"] = True
        summaries = registry.get_tool_summaries("u1")
        tool_names = [s["tool"] for s in summaries]
        assert "execute_code" in tool_names

    @pytest.mark.asyncio
    async def test_summaries_updated_after_mcp_connect(self, registry):
        registry.register_plugin(
            PluginManifest(
                id="local-test-mcp",
                name="Local Test MCP",
                kind=PluginKind.MCP_STDIO,
                command=sys.executable,
                args=["scripts/local_mcp_server.py"],
                tools_summary=[ToolSummary(name="placeholder", description="before connect")],
            )
        )
        await registry.connect_plugin("u1", "local-test-mcp")

        summaries = registry.get_tool_summaries("u1")
        tool_names = [s["tool"] for s in summaries]
        # Should now have real tools, not placeholder
        assert "echo" in tool_names
        assert "placeholder" not in tool_names

        await registry.shutdown()


# ── MCPManager compat layer ────────────────────────────────────────


class TestMCPManagerCompat:
    def test_mcp_manager_delegates_to_registry(self):
        from app.services.mcp_manager import get_mcp_manager

        mgr = get_mcp_manager()
        catalog = mgr.get_catalog()
        assert len(catalog) > 0


# ── Singleton ──────────────────────────────────────────────────────


class TestSingleton:
    def test_singleton_returns_same_instance(self):
        from app.services.plugin_registry import get_plugin_registry

        r1 = get_plugin_registry()
        r2 = get_plugin_registry()
        assert r1 is r2
