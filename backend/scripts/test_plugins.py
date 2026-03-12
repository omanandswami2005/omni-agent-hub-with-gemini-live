"""Test script for Plugin Registry + MCP + E2B integration.

Tests:
1. Plugin Registry initialization and catalog
2. Wikipedia MCP (HTTP) — connect, discover tools, get schemas
3. E2B sandbox — execute code, install packages, multi-tool scenarios
4. Native plugin — notification sender
5. Lazy tool loading flow

Run from backend directory:
    uv run python -m scripts.test_plugins
"""

from __future__ import annotations

import asyncio
import sys
import os

# Ensure app is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.logging import setup_logging, get_logger

setup_logging("INFO")
logger = get_logger(__name__)

# Test user
TEST_USER = "test_user_plugin_check"


async def test_plugin_catalog():
    """Test 1: Plugin Registry catalog works."""
    print("\n" + "=" * 60)
    print("TEST 1: Plugin Registry — Catalog")
    print("=" * 60)

    from app.services.plugin_registry import get_plugin_registry

    registry = get_plugin_registry()
    catalog = registry.get_catalog(TEST_USER)

    print(f"  Plugins in catalog: {len(catalog)}")
    for p in catalog:
        print(f"    [{p.kind}] {p.id}: {p.name} — {p.state}")
        if p.tools_summary:
            for t in p.tools_summary:
                print(f"        tool: {t.name} — {t.description}")

    assert len(catalog) > 0, "Catalog should not be empty"
    # Check that notification-sender was auto-discovered
    ids = [p.id for p in catalog]
    assert "notification-sender" in ids, "Notification sender plugin should be auto-discovered"
    assert "e2b-sandbox" in ids, "E2B sandbox should be in catalog"
    assert "wikipedia" in ids, "Wikipedia should be in catalog"

    print("  ✅ Catalog test PASSED")
    return True


async def test_wikipedia_mcp():
    """Test 2: Wikipedia MCP (HTTP) — connect and discover tools."""
    print("\n" + "=" * 60)
    print("TEST 2: Wikipedia MCP — Connect & Discover")
    print("=" * 60)

    from app.services.plugin_registry import get_plugin_registry

    registry = get_plugin_registry()

    # Enable Wikipedia
    from app.models.plugin import PluginToggle
    result = await registry.toggle_plugin(TEST_USER, PluginToggle(plugin_id="wikipedia", enabled=True))
    print(f"  Wikipedia enabled: {result}")

    if not result:
        # Check for errors
        catalog = registry.get_catalog(TEST_USER)
        for p in catalog:
            if p.id == "wikipedia":
                print(f"  State: {p.state}, Error: {p.error}")
        print("  ⚠️  Wikipedia MCP connect failed (server may be down)")
        return False

    # Get tools
    tools = await registry.get_tools(TEST_USER)
    wiki_tools = [t for t in tools if "wiki" in getattr(t, "name", "").lower()
                  or "search" in getattr(t, "name", "").lower()
                  or "article" in getattr(t, "name", "").lower()]

    print(f"  Total tools from all enabled plugins: {len(tools)}")
    print(f"  Wikipedia-related tools: {len(wiki_tools)}")
    for t in tools:
        name = getattr(t, "name", str(t))
        desc = getattr(t, "description", "")[:80]
        print(f"    {name}: {desc}")

    # Get tool schemas (on-demand)
    schemas = await registry.get_tool_schemas("wikipedia", TEST_USER)
    print(f"  Tool schemas loaded: {len(schemas)}")
    for s in schemas:
        print(f"    {s.name}: params={list(s.parameters.keys()) if s.parameters else 'none'}")

    # Disconnect
    await registry.disconnect_plugin(TEST_USER, "wikipedia")
    print("  ✅ Wikipedia MCP test PASSED")
    return True


async def test_e2b_sandbox():
    """Test 3: E2B Sandbox — execute code and install packages."""
    print("\n" + "=" * 60)
    print("TEST 3: E2B Sandbox — Code Execution")
    print("=" * 60)

    from app.services.plugin_registry import get_plugin_registry
    from app.services.e2b_service import get_e2b_service
    from app.config import get_settings

    settings = get_settings()
    if not settings.E2B_API_KEY:
        print("  ⚠️  E2B_API_KEY not set, skipping E2B tests")
        return False

    registry = get_plugin_registry()

    # Enable E2B
    from app.models.plugin import PluginToggle
    await registry.toggle_plugin(TEST_USER, PluginToggle(plugin_id="e2b-sandbox", enabled=True))

    svc = get_e2b_service()
    sandbox_id = f"{TEST_USER}:test"

    # Test 3a: Basic Python execution
    print("\n  --- 3a: Basic Python execution ---")
    result = await svc.execute_code(sandbox_id, "print('Hello from E2B!')\n2 + 2")
    print(f"    stdout: {result.stdout}")
    print(f"    results: {result.results}")
    print(f"    error: {result.error}")
    assert result.error is None, f"Code execution failed: {result.error}"

    # Test 3b: Install package and use it
    print("\n  --- 3b: Install package + use ---")
    install_result = await svc.execute_command(sandbox_id, "pip install -q requests")
    print(f"    Install exit code error: {install_result.error}")

    code = """
import requests
resp = requests.get('https://httpbin.org/json')
print(f"Status: {resp.status_code}")
print(f"Keys: {list(resp.json().keys())}")
"""
    result = await svc.execute_code(sandbox_id, code)
    print(f"    stdout: {result.stdout}")
    assert result.error is None, f"Code with requests failed: {result.error}"

    # Test 3c: Multi-step data analysis
    print("\n  --- 3c: Multi-step data analysis ---")
    code = """
import json
data = [
    {"name": "Alice", "score": 85},
    {"name": "Bob", "score": 92},
    {"name": "Charlie", "score": 78},
    {"name": "Diana", "score": 95},
]
avg = sum(d["score"] for d in data) / len(data)
top = max(data, key=lambda d: d["score"])
print(json.dumps({"average": avg, "top_scorer": top["name"]}, indent=2))
"""
    result = await svc.execute_code(sandbox_id, code)
    print(f"    stdout: {result.stdout}")
    assert result.error is None

    # Test 3d: File operations in sandbox
    print("\n  --- 3d: File operations ---")
    await svc.upload_file(sandbox_id, "/tmp/test.txt", b"Hello from Omni Hub!")
    content = await svc.download_file(sandbox_id, "/tmp/test.txt")
    print(f"    Downloaded content: {content[:50]}")

    # Test 3e: Shell command
    print("\n  --- 3e: Shell command ---")
    result = await svc.execute_command(sandbox_id, "echo 'E2B works!' && uname -a")
    print(f"    stdout: {result.stdout}")

    # Cleanup
    await svc.destroy_sandbox(sandbox_id)
    await registry.disconnect_plugin(TEST_USER, "e2b-sandbox")

    print("  ✅ E2B Sandbox test PASSED")
    return True


async def test_native_plugin():
    """Test 4: Native plugin — notification sender."""
    print("\n" + "=" * 60)
    print("TEST 4: Native Plugin — Notification Sender")
    print("=" * 60)

    from app.services.plugin_registry import get_plugin_registry

    registry = get_plugin_registry()

    # Enable notification sender
    from app.models.plugin import PluginToggle
    result = await registry.toggle_plugin(
        TEST_USER,
        PluginToggle(plugin_id="notification-sender", enabled=True),
    )
    print(f"  Notification sender enabled: {result}")
    assert result, "Native plugin should enable successfully"

    # Get tools
    tools = await registry.get_tools(TEST_USER)
    notif_tools = [t for t in tools if "notification" in getattr(t, "name", "").lower()]
    print(f"  Notification tools: {len(notif_tools)}")
    for t in notif_tools:
        print(f"    {t.name}")

    assert len(notif_tools) >= 2, "Should have at least send_notification and list_notification_channels"

    # Test calling the tools directly
    from app.plugins.notification_sender import send_notification, list_notification_channels

    channels = await list_notification_channels()
    print(f"  Available channels: {[c['id'] for c in channels['channels']]}")

    result = await send_notification(message="Test from plugin system", channel="log", title="Plugin Test")
    print(f"  Send result: {result}")
    assert result["success"], "Notification send should succeed"

    # Get tool schemas
    schemas = await registry.get_tool_schemas("notification-sender", TEST_USER)
    print(f"  Tool schemas: {len(schemas)}")
    for s in schemas:
        print(f"    {s.name}: {s.description[:60]}")

    await registry.disconnect_plugin(TEST_USER, "notification-sender")
    print("  ✅ Native plugin test PASSED")
    return True


async def test_lazy_loading():
    """Test 5: Lazy tool loading — summaries first, schemas on demand."""
    print("\n" + "=" * 60)
    print("TEST 5: Lazy Tool Loading")
    print("=" * 60)

    from app.services.plugin_registry import get_plugin_registry

    registry = get_plugin_registry()

    # Enable notification sender (has pre-declared summaries)
    from app.models.plugin import PluginToggle
    await registry.toggle_plugin(
        TEST_USER,
        PluginToggle(plugin_id="notification-sender", enabled=True),
    )

    # Step 1: Get summaries only (fast — no MCP connection)
    summaries = registry.get_tool_summaries(TEST_USER)
    print(f"  Tool summaries (lightweight): {len(summaries)}")
    for s in summaries:
        print(f"    [{s['plugin']}] {s['tool']}: {s['description'][:60]}")

    # Step 2: On-demand — get full schemas only when needed
    schemas = await registry.get_tool_schemas("notification-sender", TEST_USER)
    print(f"  Full schemas (on-demand): {len(schemas)}")

    await registry.disconnect_all(TEST_USER)
    print("  ✅ Lazy loading test PASSED")
    return True


async def test_tool_integration_with_runner():
    """Test 6: Tools integrate with ADK Runner through MCPManager compat layer."""
    print("\n" + "=" * 60)
    print("TEST 6: MCPManager Compatibility Layer")
    print("=" * 60)

    from app.services.mcp_manager import get_mcp_manager

    mgr = get_mcp_manager()

    # Test catalog (backward compat)
    catalog = mgr.get_catalog(TEST_USER)
    print(f"  MCPManager catalog items: {len(catalog)}")

    # Test enabled IDs
    enabled = mgr.get_enabled_ids(TEST_USER)
    print(f"  Enabled: {enabled}")

    # Test config lookup
    config = mgr.get_mcp_config("wikipedia")
    print(f"  Wikipedia config found: {config is not None}")
    if config:
        print(f"    Name: {config.name}, Transport: {config.transport}")

    print("  ✅ MCPManager compat test PASSED")
    return True


async def main():
    """Run all tests."""
    print("\n" + "#" * 60)
    print("# Plugin Registry + MCP + E2B Integration Tests")
    print("#" * 60)

    results = {}

    # Always run
    results["catalog"] = await test_plugin_catalog()
    results["native"] = await test_native_plugin()
    results["lazy_loading"] = await test_lazy_loading()
    results["compat"] = await test_tool_integration_with_runner()

    # Network-dependent
    try:
        results["wikipedia"] = await test_wikipedia_mcp()
    except Exception as e:
        print(f"\n  ❌ Wikipedia test ERROR: {e}")
        results["wikipedia"] = False

    try:
        results["e2b"] = await test_e2b_sandbox()
    except Exception as e:
        print(f"\n  ❌ E2B test ERROR: {e}")
        results["e2b"] = False

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results.items():
        icon = "✅" if passed else "❌"
        print(f"  {icon} {name}")

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n  {passed}/{total} tests passed")

    # Cleanup
    from app.services.plugin_registry import get_plugin_registry
    registry = get_plugin_registry()
    await registry.disconnect_all(TEST_USER)


if __name__ == "__main__":
    asyncio.run(main())
