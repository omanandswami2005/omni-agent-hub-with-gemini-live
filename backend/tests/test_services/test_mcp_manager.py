"""Tests for MCP Manager & Dynamic Tool Loading (Task 11)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.mcp import MCPCatalogItem, MCPConfig, MCPToggle, TransportType
from app.services.mcp_manager import (
    MCP_CATALOG,
    MCPManager,
    get_mcp_manager,
)

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the global MCPManager singleton between tests."""
    import app.services.mcp_manager as mod

    old = mod._manager
    mod._manager = None
    yield
    mod._manager = old


@pytest.fixture()
def mgr():
    return MCPManager()


# ── Catalog tests ────────────────────────────────────────────────────


class TestCatalog:
    """Tests for the built-in MCP catalog."""

    def test_catalog_has_nine_entries(self):
        assert len(MCP_CATALOG) == 9

    def test_catalog_ids_unique(self):
        ids = [m.id for m in MCP_CATALOG]
        assert len(ids) == len(set(ids))

    def test_catalog_contains_brave_search(self):
        ids = {m.id for m in MCP_CATALOG}
        assert "brave-search" in ids

    def test_catalog_contains_github(self):
        ids = {m.id for m in MCP_CATALOG}
        assert "github" in ids

    def test_catalog_contains_wikipedia(self):
        ids = {m.id for m in MCP_CATALOG}
        assert "wikipedia" in ids

    def test_wikipedia_is_http(self):
        cfg = next(m for m in MCP_CATALOG if m.id == "wikipedia")
        assert cfg.transport == TransportType.STREAMABLE_HTTP
        assert cfg.url != ""

    def test_brave_is_stdio(self):
        cfg = next(m for m in MCP_CATALOG if m.id == "brave-search")
        assert cfg.transport == TransportType.STDIO
        assert cfg.command == "npx"


class TestGetCatalog:
    """Tests for MCPManager.get_catalog()."""

    def test_returns_catalog_items(self, mgr):
        items = mgr.get_catalog()
        assert len(items) == 9
        assert all(isinstance(i, MCPCatalogItem) for i in items)

    def test_all_disabled_by_default(self, mgr):
        items = mgr.get_catalog("user1")
        assert all(not i.enabled for i in items)

    def test_enabled_state_reflected(self, mgr):
        mgr._user_enabled["user1"] = {"github": True}
        items = mgr.get_catalog("user1")
        gh = next(i for i in items if i.id == "github")
        assert gh.enabled is True


class TestGetMcpConfig:
    """Tests for MCPManager.get_mcp_config()."""

    def test_known_mcp(self, mgr):
        cfg = mgr.get_mcp_config("github")
        assert isinstance(cfg, MCPConfig)
        assert cfg.name == "GitHub"

    def test_unknown_mcp(self, mgr):
        assert mgr.get_mcp_config("nonexistent") is None


# ── Connect / Disconnect ─────────────────────────────────────────────


class TestConnectDisconnect:
    """Tests for connect_mcp / disconnect_mcp."""

    @pytest.mark.asyncio
    async def test_connect_creates_toolset(self, mgr):
        with patch(
            "app.services.mcp_manager.McpToolset"
        ) as MockToolset:
            mock_instance = MagicMock()
            MockToolset.return_value = mock_instance

            toolset = await mgr.connect_mcp("user1", "github")

        assert toolset is mock_instance
        assert ("user1", "github") in mgr._toolsets

    @pytest.mark.asyncio
    async def test_connect_returns_existing(self, mgr):
        mock_toolset = MagicMock()
        mgr._toolsets[("user1", "github")] = (mock_toolset, 0.0)

        result = await mgr.connect_mcp("user1", "github")
        assert result is mock_toolset

    @pytest.mark.asyncio
    async def test_connect_unknown_returns_none(self, mgr):
        result = await mgr.connect_mcp("user1", "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_connect_marks_enabled(self, mgr):
        with patch("app.services.mcp_manager.McpToolset"):
            await mgr.connect_mcp("user1", "github")
        assert mgr._user_enabled["user1"]["github"] is True

    @pytest.mark.asyncio
    async def test_disconnect_removes_toolset(self, mgr):
        mock_toolset = AsyncMock()
        mgr._toolsets[("user1", "github")] = (mock_toolset, 0.0)
        mgr._user_enabled["user1"] = {"github": True}

        result = await mgr.disconnect_mcp("user1", "github")
        assert result is True
        assert ("user1", "github") not in mgr._toolsets
        mock_toolset.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent(self, mgr):
        result = await mgr.disconnect_mcp("user1", "nope")
        assert result is False


# ── Toggle ───────────────────────────────────────────────────────────


class TestToggle:
    """Tests for MCPManager.toggle_mcp()."""

    @pytest.mark.asyncio
    async def test_toggle_on(self, mgr):
        with patch("app.services.mcp_manager.McpToolset"):
            result = await mgr.toggle_mcp(
                "user1", MCPToggle(mcp_id="github", enabled=True)
            )
        assert result is True
        assert "github" in mgr.get_enabled_ids("user1")

    @pytest.mark.asyncio
    async def test_toggle_off(self, mgr):
        mock_toolset = AsyncMock()
        mgr._toolsets[("user1", "github")] = (mock_toolset, 0.0)
        mgr._user_enabled["user1"] = {"github": True}

        result = await mgr.toggle_mcp(
            "user1", MCPToggle(mcp_id="github", enabled=False)
        )
        assert result is False
        assert "github" not in mgr.get_enabled_ids("user1")


# ── Get tools ────────────────────────────────────────────────────────


class TestGetTools:
    """Tests for MCPManager.get_tools()."""

    @pytest.mark.asyncio
    async def test_returns_tools_from_enabled(self, mgr):
        mock_toolset = AsyncMock()
        mock_tool = MagicMock(name="mock_tool")
        mock_toolset.get_tools = AsyncMock(return_value=[mock_tool])
        mgr._toolsets[("user1", "github")] = (mock_toolset, 0.0)
        mgr._user_enabled["user1"] = {"github": True}

        tools = await mgr.get_tools("user1")
        assert len(tools) == 1
        assert tools[0] is mock_tool

    @pytest.mark.asyncio
    async def test_returns_empty_when_none_enabled(self, mgr):
        tools = await mgr.get_tools("user1")
        assert tools == []

    @pytest.mark.asyncio
    async def test_handles_tool_fetch_error(self, mgr):
        mock_toolset = AsyncMock()
        mock_toolset.get_tools = AsyncMock(side_effect=RuntimeError("fail"))
        mgr._toolsets[("user1", "github")] = (mock_toolset, 0.0)
        mgr._user_enabled["user1"] = {"github": True}

        tools = await mgr.get_tools("user1")
        assert tools == []


# ── Connection params builder ────────────────────────────────────────


class TestBuildConnectionParams:
    """Tests for _build_connection_params."""

    def test_stdio_params(self, mgr):
        from google.adk.tools.mcp_tool.mcp_toolset import StdioConnectionParams

        config = MCPConfig(
            id="test",
            name="Test",
            transport=TransportType.STDIO,
            command="npx",
            args=["-y", "test-pkg"],
        )
        params = mgr._build_connection_params(config)
        assert isinstance(params, StdioConnectionParams)

    def test_http_params(self, mgr):
        from google.adk.tools.mcp_tool.mcp_toolset import (
            StreamableHTTPConnectionParams,
        )

        config = MCPConfig(
            id="test",
            name="Test",
            transport=TransportType.STREAMABLE_HTTP,
            url="https://example.com/mcp",
        )
        params = mgr._build_connection_params(config)
        assert isinstance(params, StreamableHTTPConnectionParams)
        assert params.url == "https://example.com/mcp"


# ── Singleton ────────────────────────────────────────────────────────


class TestSingleton:
    """Tests for get_mcp_manager() singleton."""

    def test_returns_same_instance(self):
        mgr1 = get_mcp_manager()
        mgr2 = get_mcp_manager()
        assert mgr1 is mgr2

    def test_is_mcp_manager(self):
        mgr = get_mcp_manager()
        assert isinstance(mgr, MCPManager)


# ── Cleanup ──────────────────────────────────────────────────────────


class TestCleanup:
    """Tests for disconnect_all and shutdown."""

    @pytest.mark.asyncio
    async def test_disconnect_all(self, mgr):
        mock_toolset = AsyncMock()
        mgr._toolsets[("user1", "github")] = mock_toolset
        mgr._toolsets[("user1", "slack")] = AsyncMock()
        mgr._user_enabled["user1"] = {"github": True, "slack": True}

        await mgr.disconnect_all("user1")
        assert mgr.get_enabled_ids("user1") == []

    @pytest.mark.asyncio
    async def test_shutdown_clears_all(self, mgr):
        mgr._toolsets[("u1", "github")] = AsyncMock()
        mgr._toolsets[("u2", "slack")] = AsyncMock()
        mgr._user_enabled["u1"] = {"github": True}
        mgr._user_enabled["u2"] = {"slack": True}

        await mgr.shutdown()
        assert len(mgr._toolsets) == 0
        assert len(mgr._user_enabled) == 0


# ── API endpoint tests ──────────────────────────────────────────────


class TestMCPAPI:
    """Tests for the MCP REST API endpoints."""

    @pytest.fixture()
    def client(self):
        from app.main import app

        with TestClient(app) as c:
            yield c

    def test_get_catalog(self, client):
        resp = client.get("/api/v1/mcp/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 9
        assert all("id" in item for item in data)

    def test_get_enabled_empty(self, client):
        resp = client.get("/api/v1/mcp/enabled")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_mcp_detail(self, client):
        resp = client.get("/api/v1/mcp/github")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "github"
        assert data["name"] == "GitHub"

    def test_get_mcp_detail_404(self, client):
        resp = client.get("/api/v1/mcp/nonexistent")
        assert resp.status_code == 404

    def test_toggle_on(self, client):
        with patch("app.services.mcp_manager.McpToolset"):
            resp = client.post(
                "/api/v1/mcp/toggle",
                json={"mcp_id": "github", "enabled": True},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["mcp_id"] == "github"
        assert data["enabled"] is True

    def test_toggle_unknown_404(self, client):
        resp = client.post(
            "/api/v1/mcp/toggle",
            json={"mcp_id": "nonexistent", "enabled": True},
        )
        assert resp.status_code == 404
