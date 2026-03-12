"""Auto-discovered plugins package.

Place plugin modules here. Each module should export a ``MANIFEST``
attribute of type :class:`~app.models.plugin.PluginManifest`.  The
PluginRegistry auto-discovers these at startup.

Example plugin module (``my_plugin.py``)::

    from app.models.plugin import PluginManifest, PluginKind, PluginCategory

    MANIFEST = PluginManifest(
        id="my-plugin",
        name="My Plugin",
        description="Does something useful.",
        kind=PluginKind.NATIVE,
        module="app.plugins.my_plugin",
        factory="get_tools",
    )

    def get_tools():
        from google.adk.tools import FunctionTool
        async def my_tool(query: str) -> str:
            return f"Result for {query}"
        return [FunctionTool(my_tool)]
"""
