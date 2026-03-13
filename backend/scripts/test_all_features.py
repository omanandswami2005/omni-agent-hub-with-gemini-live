#!/usr/bin/env python3
"""
Omni Hub — Feature Test Runner
================================
Connects to the backend as a web-dashboard client over WebSocket (text-only
/ws/chat endpoint) and runs every major feature automatically.

No UI required. No manual token needed — signs in with Firebase email+password.

Usage
-----
    cd backend
    uv run python scripts/test_all_features.py               # run all tests
    uv run python scripts/test_all_features.py --only search  # one test
    uv run python scripts/test_all_features.py --only image,codegen,genui
    uv run python scripts/test_all_features.py --persona dev  # force persona

What It Tests
-------------
  connected   — WS auth handshake + session bootstrap
  search      — Google Search grounding (T1)
  image       — Gemini image generation (T1)
  codegen     — E2B code execution in sandbox (T1)
  mcp_wiki    — Wikipedia MCP server (T2, auto-enabled if needed)
  mcp_fs      — Filesystem MCP server (T2)
  genui       — GenUI dynamic table via send_to_dashboard (T1 cross-client)
  clients     — list_connected_clients cross-client tool (T1)
  notify      — notify_client tool (T1)
  persona     — Persona switch (root agent routing)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import textwrap
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Load .env from backend root (one level up from scripts/) ──────────────
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=False)
    except ImportError:
        # dotenv not available — fall back to manual parse (no dependencies)
        for _line in _env_file.read_text().splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

# ── Auth config — read from environment / .env, never hardcode ────────────
FIREBASE_API_KEY = os.environ["FIREBASE_WEB_API_KEY"]
EMAIL = os.environ["TEST_USER_EMAIL"]
PASSWORD = os.environ["TEST_USER_PASSWORD"]

# ── Endpoints ──────────────────────────────────────────────────────────
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
WS_URL = os.getenv("WS_URL", "ws://localhost:8000/ws/chat")
FIREBASE_SIGN_IN_URL = (
    f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
    f"?key={FIREBASE_API_KEY}"
)

# ── Colours ────────────────────────────────────────────────────────────
USE_COLOR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if not USE_COLOR:
        return text
    return f"{code}{text}\033[0m"


def green(t: str) -> str: return _c("\033[92m", t)
def red(t: str) -> str:   return _c("\033[91m", t)
def yellow(t: str) -> str:return _c("\033[93m", t)
def cyan(t: str) -> str:  return _c("\033[96m", t)
def blue(t: str) -> str:  return _c("\033[94m", t)
def bold(t: str) -> str:  return _c("\033[1m", t)
def dim(t: str) -> str:   return _c("\033[2m", t)


# ── Test definitions ──────────────────────────────────────────────────
TESTS: list[dict[str, Any]] = [
    {
        "id": "connected",
        "name": "WS Auth & Session Bootstrap",
        "desc": "Connects as web client and checks auth_response",
        "prompt": None,  # handled specially
    },
    {
        "id": "search",
        "name": "Google Search Grounding",
        "desc": "T1 tool: google_search via ADK GoogleSearchTool",
        "prompt": (
            "Search Google for 'Gemini 2.5 Flash model benchmark 2026' "
            "and give me a 2-sentence factual summary."
        ),
        "persona": "researcher",
    },
    {
        "id": "image",
        "name": "Image Generation (Gemini)",
        "desc": "T1 tool: generate_image via Gemini interleaved output",
        "prompt": "Generate a simple image of a red apple on a plain white background.",
        "persona": "creative",
        "expect_type": "image_response",
    },
    {
        "id": "codegen",
        "name": "E2B Code Execution",
        "desc": "T1 tool: execute_code runs in E2B sandbox",
        "prompt": (
            "Please transfer to the coder persona and have them write and execute "
            "Python code that prints the first 10 Fibonacci numbers. Show the output."
        ),
        "persona": "coder",
        "expect_tool": "execute_code",
    },
    {
        "id": "mcp_wiki",
        "name": "Wikipedia MCP Server",
        "desc": "T2 plugin: wikipedia via mcp_http server",
        "prompt": (
            "Look up 'quantum entanglement' on Wikipedia and give me "
            "a one-paragraph plain-English explanation."
        ),
        "requires_plugin": "wikipedia",
    },
    {
        "id": "mcp_fs",
        "name": "Filesystem MCP Server",
        "desc": "T2 plugin: filesystem via mcp_stdio server",
        "prompt": (
            "Using the filesystem tool, list the files in the current working directory."
        ),
        "requires_plugin": "filesystem",
    },
    {
        "id": "genui",
        "name": "GenUI — Dynamic Dashboard Card",
        "desc": "T1 cross-client: send_to_dashboard(action='render_genui')",
        "prompt": (
            "Create a comparison table of Python, JavaScript, and Go. "
            "Include columns for: speed, ease of learning, and best use case. "
            "Render it as a GenUI table directly in the dashboard."
        ),
        "expect_type": "response",
    },
    {
        "id": "clients",
        "name": "List Connected Clients",
        "desc": "T1 cross-client: list_connected_clients",
        "prompt": "What client devices do I currently have connected? List them all.",
    },
    {
        "id": "notify",
        "name": "Notification Tool",
        "desc": "T2 native plugin: notification_sender",
        "prompt": (
            "Send me a notification with the title 'Test Passed' and message "
            "'Feature test from CLI completed successfully!'"
        ),
        "requires_plugin": "notification-sender",
    },
    {
        "id": "persona",
        "name": "Persona Switch",
        "desc": "Root agent routes to sub-persona agents",
        "persona_switch": "researcher",
        "prompt": (
            "Who are you and what are your specialties? "
            "Introduce yourself in 2 sentences."
        ),
    },
]


# ── Firebase Auth ──────────────────────────────────────────────────────

async def get_firebase_token() -> str:
    """Sign in with email+password via Firebase Auth REST API."""
    try:
        import httpx
    except ImportError:
        print(red("  httpx not found. Run: uv add httpx"))
        sys.exit(1)

    print(f"  Signing in as {bold(EMAIL)} ...")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            FIREBASE_SIGN_IN_URL,
            json={"email": EMAIL, "password": PASSWORD, "returnSecureToken": True},
        )
    if resp.status_code != 200:
        body = resp.json()
        err = body.get("error", {}).get("message", "unknown")
        print(red(f"  Firebase sign-in failed: {err}"))
        print(dim("  Check EMAIL/PASSWORD constants at the top of this file."))
        sys.exit(1)

    token = resp.json()["idToken"]
    print(green("  Firebase auth OK") + dim(f"  (token: {token[:20]}...)"))
    return token


# ── Plugin toggle ──────────────────────────────────────────────────────

async def ensure_plugin_enabled(token: str, plugin_id: str) -> bool:
    """Enable a plugin via the REST API if not already enabled."""
    try:
        import httpx
    except ImportError:
        return False

    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=60) as client:
        # Check current state
        cat = await client.get(f"{BACKEND_URL}/api/v1/plugins/catalog", headers=headers)
        if cat.status_code != 200:
            print(yellow(f"  Could not reach plugin catalog: {cat.status_code}"))
            return False

        catalog = cat.json()
        plugin = next((p for p in catalog if p.get("id") == plugin_id), None)
        if not plugin:
            print(yellow(f"  Plugin '{plugin_id}' not found in catalog (skipping test)"))
            return False

        if plugin.get("state") in ("enabled", "connected"):
            print(dim(f"  Plugin '{plugin_id}' already enabled (state={plugin.get('state')})"))
            return True

        print(f"  Enabling plugin {bold(plugin_id)} ...")
        toggle = await client.post(
            f"{BACKEND_URL}/api/v1/plugins/toggle",
            json={"plugin_id": plugin_id, "enabled": True},
            headers=headers,
        )
        if toggle.status_code in (200, 201):
            print(green(f"  Plugin '{plugin_id}' enabled"))
            await asyncio.sleep(2)  # let it load
            return True
        else:
            print(yellow(f"  Could not enable plugin '{plugin_id}': {toggle.status_code}"))
            return False


# ── Message collection ─────────────────────────────────────────────────

DONE_STATES = {"idle", "error"}

async def collect_responses(ws, timeout: float = 45.0) -> list[dict]:
    """Receive messages until agent goes idle or timeout.

    Handles the ADK transfer_to_agent pattern: root agent transfers to a
    sub-agent and goes idle, but the sub-agent hasn't responded yet.  We
    skip early idle signals that follow a transfer and keep listening.
    """
    messages: list[dict] = []
    saw_transfer = False
    has_response_text = False
    pending_tools = 0  # tool_calls without matching tool_responses
    idle_count = 0     # how many idle signals we've received
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    try:
        while loop.time() < deadline:
            remaining = deadline - loop.time()
            # After a transfer, the sub-agent may take many seconds to start
            # producing messages (Vertex AI API call latency). Wait generously.
            if pending_tools > 0:
                silence = 20.0
            elif saw_transfer and not has_response_text:
                silence = 45.0  # sub-agent API calls can take 30s+
            else:
                silence = 8.0
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, silence))
            except TimeoutError:
                # Silence exceeded — stop if we have a real text response
                if has_response_text:
                    break
                # Also stop if no transfer & already got idle
                if not saw_transfer and idle_count > 0:
                    break
                # After a transfer with 2+ idle signals and still nothing — give up
                if saw_transfer and idle_count >= 2:
                    break
                continue

            if isinstance(raw, bytes):
                messages.append({"type": "_binary_audio", "size": len(raw)})
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            messages.append(msg)

            # Track transfer_to_agent pattern
            if msg.get("type") == "tool_call" and msg.get("tool_name") == "transfer_to_agent":
                saw_transfer = True
                continue

            # Track tool_response for transfer (indicates transfer completed)
            if msg.get("type") == "tool_response" and msg.get("tool_name") == "transfer_to_agent":
                continue

            # Track pending tool calls (excluding transfer)
            if msg.get("type") == "tool_call":
                pending_tools += 1
            if msg.get("type") == "tool_response":
                pending_tools = max(0, pending_tools - 1)

            # Track whether we got an actual text response from the agent
            if msg.get("type") == "response" and (msg.get("data") or msg.get("content")):
                has_response_text = True

            # Stop on error status immediately
            if msg.get("type") == "status" and msg.get("state") == "error":
                break

            # Stop on idle
            if msg.get("type") == "status" and msg.get("state") == "idle":
                idle_count += 1
                if pending_tools > 0:
                    continue
                # After transfer: need at least 2 idle signals (root + sub-agent)
                # AND either a text response or enough idles
                if saw_transfer:
                    if has_response_text:
                        break
                    if idle_count >= 2:
                        # Sub-agent went idle without text — keep waiting briefly
                        continue
                else:
                    break
    except (Exception, asyncio.CancelledError):
        pass
    return messages


# ── Message printer ────────────────────────────────────────────────────

def print_messages(messages: list[dict]) -> None:
    for msg in messages:
        t = msg.get("type", "?")

        if t == "response":
            text = msg.get("data", "")
            content_type = msg.get("content_type", "text")
            if content_type == "genui":
                genui = msg.get("genui", {})
                print(f"    {cyan('[GenUI]')} {json.dumps(genui, indent=None)[:200]}")
            elif text:
                wrapped = textwrap.fill(text, width=90, initial_indent="    ", subsequent_indent="    ")
                print(f"    {green('[Agent]')} {wrapped}")

        elif t == "transcription":
            direction = msg.get("direction", "?")
            text = msg.get("text", "")
            if text:
                arrow = "→" if direction == "input" else "←"
                print(f"    {dim(f'[transcript {arrow}]')} {text[:120]}")

        elif t == "tool_call":
            tool = msg.get("tool_name", "?")
            args = msg.get("arguments", {})
            status = msg.get("status", "")
            args_str = json.dumps(args, separators=(",", ":"))[:100]
            icon = "⚡" if status == "started" else ("✓" if status == "completed" else "✗")
            print(f"    {blue(f'[tool {icon}]')} {bold(tool)} {dim(args_str)}")

        elif t == "tool_response":
            tool = msg.get("tool_name", "?")
            result = msg.get("result", "")
            success = msg.get("success", True)
            icon = green("✓") if success else red("✗")
            print(f"    {blue('[tool result]')} {icon} {tool}: {str(result)[:150]}")

        elif t == "image_response":
            has_b64 = bool(msg.get("image_base64"))
            has_url = bool(msg.get("image_url"))
            mime = msg.get("mime_type", "?")
            desc = msg.get("description", "")
            parts = msg.get("parts", [])
            loc = "base64 payload" if has_b64 else (msg.get("image_url", "") or "no data")
            print(f"    {cyan('[image]')} {mime} | {loc} | {desc[:80]}")
            if parts:
                print(f"             {dim(f'{len(parts)} interleaved parts')}")

        elif t == "agent_activity":
            title = msg.get("title", "?")
            status = msg.get("status", "")
            print(f"    {dim(f'[activity] {title} [{status}]')}")

        elif t == "status":
            state = msg.get("state", "?")
            color_fn = green if state == "idle" else (yellow if state == "processing" else dim)
            print(f"    {dim('[status]')} {color_fn(state)}")

        elif t == "error":
            code = msg.get("code", "?")
            desc2 = msg.get("description", "")
            print(f"    {red('[error]')} {code}: {desc2}")

        elif t in ("auth_response", "connected", "persona_changed", "_binary_audio"):
            pass  # handled elsewhere or ignored

        else:
            print(f"    {dim('[' + t + ']')} {json.dumps(msg, separators=(',', ':'))[:120]}")


def grade_result(test: dict, messages: list[dict]) -> tuple[bool, str]:
    """Simple pass/fail heuristic for each test."""
    has_response = any(
        m.get("type") == "response" and (m.get("data") or m.get("content"))
        for m in messages
    )
    has_error = any(m.get("type") == "error" for m in messages)

    if has_error:
        first_err = next(m for m in messages if m.get("type") == "error")
        return False, first_err.get("code", "error")

    expect_type = test.get("expect_type")
    if expect_type:
        if any(m.get("type") == expect_type for m in messages):
            return True, "expected message type received"

    expect_tool = test.get("expect_tool")
    if expect_tool:
        if any(m.get("tool_name") == expect_tool for m in messages):
            return True, f"tool '{expect_tool}' was called"
        # Accept transfer_to_agent + response as a pass (sub-agent handled it)
        if has_response and any(m.get("tool_name") == "transfer_to_agent" for m in messages):
            return True, "agent transferred & responded"

    if has_response:
        return True, "agent responded"

    return False, "no response received"


# ── Main test runner ───────────────────────────────────────────────────

async def run_tests(only: list[str] | None, force_persona: str | None) -> None:
    print()
    print(bold("═" * 60))
    print(bold("  Omni Hub — Feature Test Runner"))
    print(bold("═" * 60))
    print(f"  Backend : {BACKEND_URL}")
    print(f"  WS      : {WS_URL}")
    print(f"  Time    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Step 1: Firebase auth
    token = await get_firebase_token()
    print()

    # Step 2: Filter tests
    tests_to_run = TESTS if not only else [t for t in TESTS if t["id"] in only]
    if not tests_to_run:
        print(red(f"  No tests matched: {only}"))
        return

    # Step 3: Open single persistent WS connection
    print(f"  Connecting to {WS_URL} ...")
    try:
        import websockets
    except ImportError:
        print(red("  websockets not found. Run: uv add websockets"))
        sys.exit(1)

    results: dict[str, tuple[bool, str]] = {}

    try:
        async with websockets.connect(WS_URL, max_size=10 * 1024 * 1024, open_timeout=30, ping_interval=30, ping_timeout=60) as ws:
            # ── Auth handshake ──────────────────────────────────────
            auth_msg = {
                "type": "auth",
                "token": token,
                "client_type": "web",
                "capabilities": ["genui", "images", "notifications"],
                "local_tools": [],
            }
            await ws.send(json.dumps(auth_msg))

            raw = await asyncio.wait_for(ws.recv(), timeout=15)
            auth_resp = json.loads(raw)

            if auth_resp.get("status") != "ok":
                print(red(f"  Auth failed: {auth_resp.get('error', '?')}"))
                return

            user_id = auth_resp.get("user_id", "?")
            session_id = auth_resp.get("session_id", "?")
            tools = auth_resp.get("available_tools", [])
            others = auth_resp.get("other_clients_online", [])

            print(green("  WebSocket connected!"))
            print(f"  User ID  : {user_id}")
            print(f"  Session  : {session_id[:20]}...")
            print(f"  Tools    : {len(tools)} available ({', '.join(tools[:6])}{'...' if len(tools)>6 else ''})")
            if others:
                print(f"  Clients  : {', '.join(others)} also online")
            print()

            # Mark connected test as passed
            results["connected"] = (True, f"session {session_id[:16]}...")

            # ── Run each test ───────────────────────────────────────
            for i, test in enumerate(tests_to_run):
                test_id = test["id"]
                if test_id == "connected":
                    continue  # already handled above

                print(bold(f"  [{i+1}/{len(tests_to_run)}] {test['name']}"))
                print(dim(f"  {test['desc']}"))

                # Ensure plugin is enabled
                if "requires_plugin" in test:
                    try:
                        ok = await ensure_plugin_enabled(token, test["requires_plugin"])
                    except Exception as plugin_exc:
                        print(yellow(f"  ⚠  Plugin enable error: {type(plugin_exc).__name__}: {plugin_exc}"))
                        ok = False
                    if not ok:
                        print(yellow("  ⚠  Plugin unavailable — skipping"))
                        results[test_id] = (False, "plugin unavailable")
                        print()
                        continue

                # Persona routing — /ws/chat only accepts "text" type messages,
                # so we prepend a persona instruction to the user prompt and let
                # the root agent's natural-language routing handle the switch.
                persona = force_persona or test.get("persona_switch") or test.get("persona")

                # Send the prompt
                prompt = test.get("prompt")
                if not prompt:
                    results[test_id] = (True, "no-op test")
                    print(green("  ✓ PASS") + "\n")
                    continue

                # Prepend persona routing instruction if needed
                if persona:
                    prompt = f"[Use the {persona} persona] {prompt}"
                    print(dim(f"  Persona: {persona}"))
                print(f"  {dim('Prompt:')} {prompt[:120]}")

                try:
                    await ws.send(json.dumps({"type": "text", "content": prompt}))

                    # Collect responses
                    t_start = time.monotonic()
                    messages = await collect_responses(ws, timeout=120.0)
                    elapsed = time.monotonic() - t_start

                    print_messages(messages)

                    # Grade it
                    passed, reason = grade_result(test, messages)
                    status_str = green(f"✓ PASS ({elapsed:.1f}s)") if passed else red(f"✗ FAIL ({elapsed:.1f}s)")
                    print(f"\n  {status_str} — {reason}")
                    results[test_id] = (passed, reason)
                except (websockets.exceptions.ConnectionClosed, websockets.exceptions.ConnectionClosedError) as ws_err:
                    print(red(f"\n  ✗ WebSocket closed: {ws_err}"))
                    results[test_id] = (False, "websocket closed")
                    # Mark any remaining tests as skipped
                    for remaining_test in tests_to_run[i+1:]:
                        if remaining_test["id"] != "connected":
                            results[remaining_test["id"]] = (False, "skipped — connection lost")
                    break
                except Exception as test_exc:
                    print(red(f"\n  ✗ Error: {type(test_exc).__name__}: {test_exc}"))
                    results[test_id] = (False, f"error: {type(test_exc).__name__}")

                print()

                # Brief pause between tests to avoid rate limits
                await asyncio.sleep(2)

                # Drain any stale messages from previous test before moving on
                try:
                    while True:
                        await asyncio.wait_for(ws.recv(), timeout=0.5)
                except (TimeoutError, asyncio.CancelledError, Exception):
                    pass

    except ConnectionRefusedError:
        print(red(f"\n  Connection refused — is the backend running on {BACKEND_URL}?"))
        print(dim("  Start it with: uv run uvicorn app.main:app --reload --port 8000"))
        sys.exit(1)
    except Exception as exc:
        print(red(f"\n  Unexpected error: {exc}"))
        raise

    # ── Summary ──────────────────────────────────────────────────────────
    print(bold("═" * 60))
    print(bold("  Results Summary"))
    print(bold("═" * 60))
    total = len(results)
    passed_count = sum(1 for ok, _ in results.values() if ok)
    for test_id, (ok, reason) in results.items():
        test_def = next((t for t in TESTS if t["id"] == test_id), {"name": test_id})
        icon = green("✓") if ok else red("✗")
        print(f"  {icon}  {test_def['name']:<40} {dim(reason)}")

    print()
    bar = green if passed_count == total else (yellow if passed_count > 0 else red)
    print(f"  {bar(f'{passed_count}/{total} tests passed')}")
    print()


def main() -> None:
    global BACKEND_URL, WS_URL

    parser = argparse.ArgumentParser(
        description="Omni Hub Feature Test Runner — tests all backend features via WebSocket",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          uv run python scripts/test_all_features.py
          uv run python scripts/test_all_features.py --only search,image
          uv run python scripts/test_all_features.py --only codegen --persona coder
          uv run python scripts/test_all_features.py --only mcp_wiki,mcp_fs
          uv run python scripts/test_all_features.py --only genui,clients,notify
          uv run python scripts/test_all_features.py --list

        Available test IDs:
          connected  search    image    codegen
          mcp_wiki   mcp_fs    genui    clients   notify   persona
        """),
    )
    parser.add_argument(
        "--only",
        metavar="ID[,ID...]",
        help="Comma-separated test IDs to run (default: all)",
    )
    parser.add_argument(
        "--persona",
        metavar="PERSONA_ID",
        help="Force a persona switch before every test (e.g. researcher, coder, creative)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available tests and exit",
    )
    parser.add_argument(
        "--backend",
        default=None,
        help=f"Backend URL override (default: {BACKEND_URL})",
    )
    args = parser.parse_args()

    if args.list:
        print(bold("\nAvailable tests:\n"))
        for t in TESTS:
            print(f"  {bold(t['id']):<20} {t['name']}")
            print(f"  {'':20} {dim(t['desc'])}\n")
        return

    if args.backend:
        BACKEND_URL = args.backend.rstrip("/")
        WS_URL = BACKEND_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws/chat"

    only = [x.strip() for x in args.only.split(",")] if args.only else None

    asyncio.run(run_tests(only=only, force_persona=args.persona))


if __name__ == "__main__":
    main()
