"""Tests for plugin registry and plugin discovery."""

from __future__ import annotations

from src.plugin_registry import DesktopPlugin, PluginRegistry


class TestPluginRegistry:
    def test_register_plugin(self):
        registry = PluginRegistry()

        async def dummy(**_kw):
            return {"ok": True}

        plugin = DesktopPlugin(
            name="test",
            capabilities=["cap_a"],
            handlers={"action_a": dummy},
            tool_defs=[{"name": "action_a", "description": "test", "parameters": {}}],
        )
        registry.register(plugin)

        assert "test" in registry.plugin_names
        assert "cap_a" in registry.capabilities
        assert "action_a" in registry.handlers
        assert len(registry.tool_defs) == 1
        assert len(registry) == 1

    def test_register_duplicate_skipped(self):
        registry = PluginRegistry()
        plugin = DesktopPlugin(name="dup", capabilities=["x"])
        registry.register(plugin)
        registry.register(plugin)
        assert len(registry) == 1

    def test_unregister_plugin(self):
        registry = PluginRegistry()

        async def action(**_kw):
            return {}

        plugin = DesktopPlugin(
            name="removable",
            capabilities=["cap_b"],
            handlers={"action_b": action},
            tool_defs=[{"name": "action_b", "description": "rm", "parameters": {}}],
        )
        registry.register(plugin)
        assert len(registry) == 1

        registry.unregister("removable")
        assert len(registry) == 0
        assert "cap_b" not in registry.capabilities
        assert "action_b" not in registry.handlers
        assert len(registry.tool_defs) == 0

    def test_unregister_calls_on_unload(self):
        called = []
        plugin = DesktopPlugin(
            name="unloadable",
            on_unload=lambda: called.append(True),
        )
        registry = PluginRegistry()
        registry.register(plugin)
        registry.unregister("unloadable")
        assert called == [True]

    def test_load_all_calls_on_load(self):
        configs = []
        plugin = DesktopPlugin(
            name="loadable",
            on_load=lambda cfg: configs.append(cfg),
        )
        registry = PluginRegistry()
        registry.register(plugin)
        registry.load_all(config={"key": "val"})
        assert configs == [{"key": "val"}]

    def test_get_handler(self):
        registry = PluginRegistry()

        async def h(**_kw):
            return {}

        plugin = DesktopPlugin(name="p", handlers={"act": h})
        registry.register(plugin)
        assert registry.get_handler("act") is h
        assert registry.get_handler("missing") is None

    def test_discover_auto_finds_plugins(self):
        """discover() should find our built-in screen/input/file plugins."""
        import os

        registry = PluginRegistry()
        plugins_dir = os.path.join(os.path.dirname(__file__), "..", "src", "plugins")
        registry.discover(plugins_dir)

        # At least 3 plugins should be discovered
        assert len(registry) >= 3
        assert "screen" in registry.plugin_names
        assert "input" in registry.plugin_names
        assert "file" in registry.plugin_names

        # Check a few handlers exist
        assert "capture_screen" in registry.handlers
        assert "click" in registry.handlers
        assert "read_file" in registry.handlers
