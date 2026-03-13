"""Plugin system for the desktop client.

Each plugin is a module or class that declares:
  - ``name``:         Unique plugin identifier.
  - ``capabilities``: Capability tags (e.g. ``screen_capture``).
  - ``handlers``:     Dict mapping action names → async handler callables.
  - ``tool_defs``:    JSON Schema tool definitions advertised to the server.
  - ``on_load(config)``:  Optional init hook.
  - ``on_unload()``:      Optional cleanup hook.

Plugins are registered via ``PluginRegistry.register(plugin)`` or auto-
discovered from the ``plugins/`` directory.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Plugin protocol
# ---------------------------------------------------------------------------

@dataclass
class DesktopPlugin:
    """Descriptor returned by a plugin module's ``register()`` function."""

    name: str
    capabilities: list[str] = field(default_factory=list)
    handlers: dict[str, Callable[..., Coroutine[Any, Any, dict]]] = field(
        default_factory=dict,
    )
    tool_defs: list[dict] = field(default_factory=list)
    on_load: Callable[..., None] | None = None
    on_unload: Callable[[], None] | None = None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class PluginRegistry:
    """Central registry for desktop client plugins.

    Merges handler maps, capability lists, and tool definitions from all
    registered plugins into a single lookup used by ``DesktopWSClient``.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, DesktopPlugin] = {}
        self._handlers: dict[str, Callable[..., Coroutine[Any, Any, dict]]] = {}
        self._capabilities: list[str] = []
        self._tool_defs: list[dict] = []

    # ── Public API ────────────────────────────────────────────────

    def register(self, plugin: DesktopPlugin) -> None:
        """Register a plugin, merging its handlers/caps/tools."""
        if plugin.name in self._plugins:
            logger.warning("Plugin %s already registered — skipping", plugin.name)
            return
        self._plugins[plugin.name] = plugin
        self._handlers.update(plugin.handlers)
        self._capabilities.extend(plugin.capabilities)
        self._tool_defs.extend(plugin.tool_defs)
        logger.info(
            "Plugin registered: %s (%d handlers, %d caps)",
            plugin.name,
            len(plugin.handlers),
            len(plugin.capabilities),
        )

    def unregister(self, name: str) -> None:
        """Remove a plugin by name."""
        plugin = self._plugins.pop(name, None)
        if plugin is None:
            return
        for action in plugin.handlers:
            self._handlers.pop(action, None)
        for cap in plugin.capabilities:
            if cap in self._capabilities:
                self._capabilities.remove(cap)
        self._tool_defs = [
            td for td in self._tool_defs if td not in plugin.tool_defs
        ]
        if plugin.on_unload:
            try:
                plugin.on_unload()
            except Exception:
                logger.exception("Error unloading plugin %s", name)

    def load_all(self, config: Any = None) -> None:
        """Call ``on_load(config)`` on every registered plugin."""
        for plugin in self._plugins.values():
            if plugin.on_load:
                try:
                    plugin.on_load(config)
                except Exception:
                    logger.exception("Error loading plugin %s", plugin.name)

    def discover(self, package_path: str) -> None:
        """Auto-discover plugins from a package directory.

        Each sub-module must expose a ``register() -> DesktopPlugin`` function.
        """
        pkg_dir = Path(package_path)
        if not pkg_dir.is_dir():
            return
        for finder, mod_name, _is_pkg in pkgutil.iter_modules([str(pkg_dir)]):
            try:
                mod = importlib.import_module(f"src.plugins.{mod_name}")
                if hasattr(mod, "register"):
                    plugin = mod.register()
                    if isinstance(plugin, DesktopPlugin):
                        self.register(plugin)
            except Exception:
                logger.exception("Failed to discover plugin %s", mod_name)

    # ── Accessors ─────────────────────────────────────────────────

    @property
    def handlers(self) -> dict[str, Callable[..., Coroutine[Any, Any, dict]]]:
        return dict(self._handlers)

    @property
    def capabilities(self) -> list[str]:
        return list(self._capabilities)

    @property
    def tool_defs(self) -> list[dict]:
        return list(self._tool_defs)

    @property
    def plugin_names(self) -> list[str]:
        return list(self._plugins.keys())

    def get_handler(self, action: str) -> Callable[..., Coroutine[Any, Any, dict]] | None:
        return self._handlers.get(action)

    def __len__(self) -> int:
        return len(self._plugins)
