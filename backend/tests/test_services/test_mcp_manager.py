"""Tests for MCPManager compatibility wrapper & MCP_CATALOG constant."""

from __future__ import annotations

import pytest

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


# ── MCP_CATALOG constant ──────────────────────────────────────────────


class TestCatalog:
    """Tests for the MCP_CATALOG constant (loaded from app/mcps/*.json)."""

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

    def test_catalog_contains_notion(self):
        ids = {m.id for m in MCP_CATALOG}
        assert "notion" in ids

    def test_notion_is_http(self):
        cfg = next(m for m in MCP_CATALOG if m.id == "notion")
        assert cfg.transport == TransportType.STREAMABLE_HTTP
        assert cfg.url != ""

    def test_brave_is_stdio(self):
        cfg = next(m for m in MCP_CATALOG if m.id == "brave-search")
        assert cfg.transport == TransportType.STDIO
        assert cfg.command == "npx"


# ── MCPManager.get_catalog() ──────────────────────────────────────────


class TestGetCatalog:
    """Tests for MCPManager.get_catalog()."""

    def test_returns_catalog_items(self, mgr):
        # Full catalog includes MCP servers + native plugins
        items = mgr.get_catalog()
        assert len(items) >= 9
        assert all(isinstance(i, MCPCatalogItem) for i in items)

    def test_all_disabled_by_default(self, mgr):
        items = mgr.get_catalog("user1")
        assert all(not i.enabled for i in items)


# ── MCPManager.get_mcp_config() ───────────────────────────────────────


class TestGetMcpConfig:
    """Tests for MCPManager.get_mcp_config()."""

    def test_known_mcp(self, mgr):
        cfg = mgr.get_mcp_config("github")
        assert isinstance(cfg, MCPConfig)
        assert cfg.name == "GitHub"

    def test_unknown_mcp(self, mgr):
        assert mgr.get_mcp_config("nonexistent") is None


# ── Singleton ─────────────────────────────────────────────────────────


class TestSingleton:
    """Tests for get_mcp_manager() singleton."""

    def test_returns_same_instance(self):
        mgr1 = get_mcp_manager()
        mgr2 = get_mcp_manager()
        assert mgr1 is mgr2

    def test_is_mcp_manager(self):
        mgr = get_mcp_manager()
        assert isinstance(mgr, MCPManager)

