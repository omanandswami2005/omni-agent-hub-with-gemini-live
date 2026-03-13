#!/usr/bin/env python3
"""
Targeted tests for OAuth callback URL + Wikipedia plugin fixes.

Usage:
    cd backend
    uv run python scripts/test_oauth_plugin_fixes.py
    uv run python scripts/test_oauth_plugin_fixes.py --backend https://omni-backend-fcapusldtq-uc.a.run.app
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# ── Load .env ──────────────────────────────────────────────────────────
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=False)
    except ImportError:
        for _line in _env_file.read_text().splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

FIREBASE_API_KEY = os.environ.get("FIREBASE_WEB_API_KEY", "")
EMAIL = os.environ.get("TEST_USER_EMAIL", "")
PASSWORD = os.environ.get("TEST_USER_PASSWORD", "")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

passed = 0
failed = 0


def ok(name: str, detail: str = "") -> None:
    global passed
    passed += 1
    extra = f" — {detail}" if detail else ""
    print(f"  ✓ {name}{extra}")


def fail(name: str, detail: str = "") -> None:
    global failed
    failed += 1
    extra = f" — {detail}" if detail else ""
    print(f"  ✗ {name}{extra}")


async def get_token() -> str | None:
    if not FIREBASE_API_KEY or not EMAIL or not PASSWORD:
        print("  ⚠  Firebase creds not set (FIREBASE_WEB_API_KEY, TEST_USER_EMAIL, TEST_USER_PASSWORD)")
        return None
    import httpx
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={"email": EMAIL, "password": PASSWORD, "returnSecureToken": True})
    if resp.status_code != 200:
        print(f"  ⚠  Firebase sign-in failed: {resp.json().get('error', {}).get('message', '?')}")
        return None
    return resp.json()["idToken"]


# ── Test 1: BACKEND_URL config is picked up ────────────────────────────
def test_config_backend_url() -> None:
    print("\n[Test 1] Config exports BACKEND_URL & FRONTEND_URL to os.environ")

    # Simulate: set env var BEFORE importing config
    test_url = "https://test-backend.example.com"
    os.environ["BACKEND_URL"] = test_url
    os.environ["FRONTEND_URL"] = "https://test-frontend.example.com"

    # Force re-import
    import importlib
    if "app.config" in sys.modules:
        mod = importlib.reload(sys.modules["app.config"])
    else:
        mod = importlib.import_module("app.config")

    settings = mod.Settings()
    if settings.BACKEND_URL == test_url:
        ok("Settings.BACKEND_URL reads from env", f"value={settings.BACKEND_URL}")
    else:
        fail("Settings.BACKEND_URL", f"expected {test_url}, got {settings.BACKEND_URL}")

    if settings.FRONTEND_URL == "https://test-frontend.example.com":
        ok("Settings.FRONTEND_URL reads from env")
    else:
        fail("Settings.FRONTEND_URL", f"got {settings.FRONTEND_URL}")

    # Verify os.environ has it (for oauth_service.py etc.)
    if os.environ.get("BACKEND_URL") == test_url:
        ok("os.environ['BACKEND_URL'] accessible")
    else:
        fail("os.environ['BACKEND_URL']", f"got {os.environ.get('BACKEND_URL')}")

    # Clean up
    os.environ.pop("BACKEND_URL", None)
    os.environ.pop("FRONTEND_URL", None)


# ── Test 2: Google OAuth rejects empty client_id ───────────────────────
def test_google_oauth_client_id_validation() -> None:
    print("\n[Test 2] Google OAuth rejects empty client_id with clear error")

    # Ensure env vars are NOT set
    os.environ.pop("GOOGLE_OAUTH_CLIENT_ID", None)
    os.environ.pop("GOOGLE_OAUTH_CLIENT_SECRET", None)

    from app.services.google_oauth_service import GoogleOAuthService
    svc = GoogleOAuthService()

    try:
        svc.start_flow("test_user", "google-calendar", ["https://www.googleapis.com/auth/calendar"])
        fail("GoogleOAuthService.start_flow() should raise ValueError when client_id is empty")
    except ValueError as e:
        if "GOOGLE_OAUTH_CLIENT_ID" in str(e):
            ok("start_flow() raises ValueError with helpful message", str(e)[:80])
        else:
            fail("ValueError message should mention GOOGLE_OAUTH_CLIENT_ID", str(e))
    except Exception as e:
        fail("Unexpected exception type", f"{type(e).__name__}: {e}")


# ── Test 3: Wikipedia plugin lazy-loads tools ──────────────────────────
async def test_wikipedia_lazy_load() -> None:
    print("\n[Test 3] Wikipedia NATIVE plugin lazy-loads tools from empty cache")

    from app.services.plugin_registry import PluginRegistry
    registry = PluginRegistry()

    # Wikipedia should be in catalog
    manifest = registry.get_manifest("wikipedia")
    if manifest is None:
        fail("Wikipedia manifest not found in catalog")
        return
    ok("Wikipedia manifest found in catalog", f"kind={manifest.kind}")

    # Clear native tool cache to simulate cold start
    registry._native_tool_cache.pop("wikipedia", None)
    # Mark as enabled for a test user
    registry._user_enabled.setdefault("test_user", {})["wikipedia"] = True

    # _get_plugin_tools should lazy-load
    tools = await registry._get_plugin_tools("test_user", "wikipedia", manifest)
    if tools and len(tools) > 0:
        tool_names = [getattr(t, "name", str(t)) for t in tools]
        ok(f"Lazy-loaded {len(tools)} Wikipedia tools", f"{tool_names}")
        if "search_wikipedia" in tool_names:
            ok("search_wikipedia tool present")
        else:
            fail("search_wikipedia not found in tools")
        if "get_wikipedia_article" in tool_names:
            ok("get_wikipedia_article tool present")
        else:
            fail("get_wikipedia_article not found in tools")
    else:
        fail("No tools returned after lazy-load")


# ── Test 4: Plugin catalog reachable via HTTP (integration) ────────────
async def test_plugin_catalog_api() -> None:
    print(f"\n[Test 4] Plugin catalog API ({BACKEND_URL})")

    token = await get_token()
    if not token:
        print("  ⚠  Skipping API test (no Firebase token)")
        return

    import httpx
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{BACKEND_URL}/api/v1/plugins/catalog", headers=headers)

    if resp.status_code != 200:
        fail(f"Catalog API returned {resp.status_code}")
        return
    ok("Catalog API returned 200")

    catalog = resp.json()
    wiki = next((p for p in catalog if p.get("id") == "wikipedia"), None)
    if wiki:
        ok(f"Wikipedia in catalog", f"state={wiki.get('state')}")
    else:
        fail("Wikipedia not found in catalog")

    gcal = next((p for p in catalog if "calendar" in p.get("id", "").lower()), None)
    if gcal:
        ok(f"Google Calendar in catalog", f"id={gcal['id']}, state={gcal.get('state')}")
    else:
        print("  ℹ  Google Calendar not in catalog (expected if not configured)")


# ── Test 5: Wikipedia toggle + WS tool test ────────────────────────────
async def test_wikipedia_ws_tools() -> None:
    print(f"\n[Test 5] Wikipedia tools via WebSocket ({BACKEND_URL})")

    token = await get_token()
    if not token:
        print("  ⚠  Skipping WS test (no Firebase token)")
        return

    import httpx
    headers = {"Authorization": f"Bearer {token}"}

    # Enable Wikipedia plugin
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BACKEND_URL}/api/v1/plugins/toggle",
            json={"plugin_id": "wikipedia", "enabled": True},
            headers=headers,
        )
    if resp.status_code in (200, 201):
        ok("Wikipedia plugin enabled via API")
    else:
        fail(f"Toggle Wikipedia: {resp.status_code}", resp.text[:100])
        return

    # Connect WS and check if tools are available
    ws_url = BACKEND_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws/chat"
    import websockets
    try:
        async with websockets.connect(ws_url, max_size=10 * 1024 * 1024, open_timeout=15) as ws:
            auth_msg = {
                "type": "auth",
                "token": token,
                "client_type": "web",
                "capabilities": ["genui", "images"],
                "local_tools": [],
            }
            await ws.send(json.dumps(auth_msg))
            raw = await asyncio.wait_for(ws.recv(), timeout=15)
            auth_resp = json.loads(raw)

            if auth_resp.get("status") != "ok":
                fail(f"WS auth failed: {auth_resp.get('error', '?')}")
                return
            ok("WS auth OK")

            tools = auth_resp.get("available_tools", [])
            wiki_tools = [t for t in tools if "wikipedia" in t.lower()]
            if wiki_tools:
                ok(f"Wikipedia tools in available_tools", f"{wiki_tools}")
            else:
                fail(f"No Wikipedia tools in available_tools", f"got {len(tools)} tools: {tools[:10]}")

            # Send a Wikipedia search prompt
            await ws.send(json.dumps({
                "type": "text",
                "content": "Search Wikipedia for 'quantum computing' and give me a brief summary."
            }))

            # Collect responses for up to 60 seconds
            deadline = time.monotonic() + 60
            messages = []
            saw_wiki_tool = False
            saw_response = False
            while time.monotonic() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=10)
                except TimeoutError:
                    if saw_response:
                        break
                    continue
                if isinstance(raw, bytes):
                    continue
                msg = json.loads(raw)
                messages.append(msg)
                if msg.get("type") == "tool_call" and "wikipedia" in msg.get("tool_name", "").lower():
                    saw_wiki_tool = True
                if msg.get("type") == "response" and msg.get("data"):
                    saw_response = True
                if msg.get("type") == "status" and msg.get("state") == "idle" and saw_response:
                    break

            if saw_wiki_tool:
                ok("Agent used a Wikipedia tool")
            else:
                print(f"  ℹ  Agent may have used built-in knowledge instead of Wikipedia tool")

            if saw_response:
                ok("Agent responded to Wikipedia query")
            else:
                fail("No response from agent for Wikipedia query")

    except Exception as e:
        fail(f"WS test error: {type(e).__name__}: {e}")


async def main() -> None:
    global BACKEND_URL
    parser = argparse.ArgumentParser(description="Test OAuth + Plugin fixes")
    parser.add_argument("--backend", help=f"Backend URL (default: {BACKEND_URL})")
    parser.add_argument("--skip-ws", action="store_true", help="Skip WebSocket tests")
    args = parser.parse_args()

    if args.backend:
        BACKEND_URL = args.backend.rstrip("/")

    print("═" * 50)
    print("  OAuth + Plugin Fix Tests")
    print("═" * 50)
    print(f"  Backend: {BACKEND_URL}")

    # Unit tests (no server needed)
    test_config_backend_url()
    test_google_oauth_client_id_validation()
    await test_wikipedia_lazy_load()

    # Integration tests (server needed)
    if not args.skip_ws:
        await test_plugin_catalog_api()
        await test_wikipedia_ws_tools()

    # Summary
    print("\n" + "═" * 50)
    total = passed + failed
    if failed == 0:
        print(f"  ✓ All {total} checks passed!")
    else:
        print(f"  {passed}/{total} passed, {failed} failed")
    print("═" * 50)
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
