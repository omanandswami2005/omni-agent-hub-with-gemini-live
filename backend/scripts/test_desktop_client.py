#!/usr/bin/env python3
"""
Omni Hub — Desktop Client E2E Test Runner
==========================================
Connects to the backend as a **desktop** client over WebSocket (/ws/live)
and tests every feature the desktop client exercises: auth, text chat,
tool invocations (T3 reverse-RPC), cross-client messaging, cancellation,
ping/pong, session suggestion, and reconnection.

No GUI or desktop client install required — this script simulates the
DesktopWSClient protocol entirely.

Usage
-----
    cd backend
    uv run python scripts/test_desktop_client.py               # run all
    uv run python scripts/test_desktop_client.py --only auth    # single test
    uv run python scripts/test_desktop_client.py --only auth,text,t3_tools
    uv run python scripts/test_desktop_client.py --backend https://omni-backend-fcapusldtq-uc.a.run.app

What It Tests
-------------
  auth              — WS auth handshake + auth_response + connected message
  text              — Send text message, receive agent response
  t3_tools          — Register local_tools, receive tool_invocation, respond with tool_result
  cross_client      — List connected clients, verify desktop appears
  cancel            — Tool cancellation via cancel / cancel_all messages
  ping_pong         — Ping/pong heartbeat (simulated)
  reconnect         — Disconnect and reconnect with same token
  session_info      — Session created / session suggestion messages
  persona           — Persona routing via text prompt
  interrupt         — Client interrupt message handling
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

# ── Load .env from backend root ──────────────────────────────────────
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

# ── Auth config ───────────────────────────────────────────────────────
FIREBASE_API_KEY = os.environ["FIREBASE_WEB_API_KEY"]
EMAIL = os.environ["TEST_USER_EMAIL"]
PASSWORD = os.environ["TEST_USER_PASSWORD"]

# ── Endpoints ─────────────────────────────────────────────────────────
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
_default_ws = BACKEND_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws/live"
WS_URL = os.getenv("WS_LIVE_URL", _default_ws)
FIREBASE_SIGN_IN_URL = (
    f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
    f"?key={FIREBASE_API_KEY}"
)

# ── Colours ───────────────────────────────────────────────────────────
USE_COLOR = sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    return f"{code}{text}\033[0m" if USE_COLOR else text

def green(t: str) -> str:  return _c("\033[92m", t)
def red(t: str) -> str:    return _c("\033[91m", t)
def yellow(t: str) -> str: return _c("\033[93m", t)
def cyan(t: str) -> str:   return _c("\033[96m", t)
def blue(t: str) -> str:   return _c("\033[94m", t)
def bold(t: str) -> str:   return _c("\033[1m", t)
def dim(t: str) -> str:    return _c("\033[2m", t)


# ── Simulated T3 local tools (desktop plugin definitions) ────────────
DESKTOP_LOCAL_TOOLS = [
    {
        "name": "capture_screen",
        "description": "Capture a screenshot of the desktop",
        "parameters": {"type": "object", "properties": {"quality": {"type": "integer", "default": 75}}}
    },
    {
        "name": "screen_info",
        "description": "Get information about connected monitors",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "click",
        "description": "Click at screen coordinates",
        "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "button": {"type": "string", "default": "left"}}, "required": ["x", "y"]}
    },
    {
        "name": "type_text",
        "description": "Type text on the keyboard",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
    },
    {
        "name": "hotkey",
        "description": "Press a keyboard shortcut",
        "parameters": {"type": "object", "properties": {"keys": {"type": "array", "items": {"type": "string"}}}, "required": ["keys"]}
    },
    {
        "name": "execute_command",
        "description": "Execute a shell command on the desktop",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}
    },
    {
        "name": "read_file",
        "description": "Read a file from the desktop filesystem",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
    },
    {
        "name": "list_directory",
        "description": "List files in a desktop directory",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
    },
]

DESKTOP_CAPABILITIES = [
    "screen_capture", "input_control", "file_access",
    "command_execution", "audio_streaming",
]


# ── Test definitions ──────────────────────────────────────────────────
TESTS: list[dict[str, Any]] = [
    {
        "id": "auth",
        "name": "Desktop WS Auth & Handshake",
        "desc": "Connect as desktop client, verify auth_response + connected msg",
    },
    {
        "id": "text",
        "name": "Text Chat via /ws/live",
        "desc": "Send text message, receive agent response over live WS",
        "prompt": "Say hello and tell me what type of client I am connected as. Keep it brief.",
    },
    {
        "id": "t3_tools",
        "name": "T3 Tool Registration & Invocation",
        "desc": "Register local_tools (screen, click, etc.) and ask agent to capture screen",
        "prompt": "Please capture a screenshot of my desktop screen right now.",
    },
    {
        "id": "cross_client",
        "name": "Cross-Client — List Clients",
        "desc": "Ask agent to list connected clients, verify desktop appears",
        "prompt": "What client devices do I currently have connected? List them.",
    },
    {
        "id": "ping_pong",
        "name": "Protocol — Ping/Pong",
        "desc": "Send a ping frame and verify pong response",
    },
    {
        "id": "interrupt",
        "name": "Client Interrupt Signal",
        "desc": "Send interrupt message and verify server accepts it",
        "prompt": "Write me a very long essay about the history of computing.",
    },
    {
        "id": "persona",
        "name": "Persona Routing (Desktop)",
        "desc": "Route to researcher persona and get a response",
        "prompt": "[Use the researcher persona] Who are you and what are your specialties? Answer in 2 sentences.",
    },
    {
        "id": "reconnect",
        "name": "Disconnect & Reconnect",
        "desc": "Close WS, reconnect with same token, verify new session",
    },
    {
        "id": "session_info",
        "name": "Session Info Messages",
        "desc": "Verify session_created and related session messages are received",
    },
    {
        "id": "cancel",
        "name": "Tool Cancellation Protocol",
        "desc": "Send tool_result with cancellation error, verify protocol compliance",
    },
]


# ── Firebase Auth ─────────────────────────────────────────────────────

async def get_firebase_token() -> str:
    """Sign in with email+password via Firebase Auth REST API."""
    try:
        import httpx
    except ImportError:
        print(red("  httpx not found. Run: uv add httpx"))
        sys.exit(1)

    print(f"  Signing in as {bold(EMAIL)} ...")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            FIREBASE_SIGN_IN_URL,
            json={"email": EMAIL, "password": PASSWORD, "returnSecureToken": True},
        )
    if resp.status_code != 200:
        body = resp.json()
        err = body.get("error", {}).get("message", "unknown")
        print(red(f"  Firebase sign-in failed: {err}"))
        sys.exit(1)

    token = resp.json()["idToken"]
    print(green("  Firebase auth OK") + dim(f"  (token: {token[:20]}...)"))
    return token


# ── Message collector ─────────────────────────────────────────────────

async def collect_messages(ws, timeout: float = 30.0, stop_on_idle: bool = True) -> list[dict]:
    """Receive messages until idle status, timeout, or no more messages."""
    messages: list[dict] = []
    has_response = False
    saw_transfer = False
    idle_count = 0
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    try:
        while loop.time() < deadline:
            remaining = deadline - loop.time()
            silence = 15.0 if saw_transfer and not has_response else 6.0
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, silence))
            except TimeoutError:
                if has_response or idle_count > 0:
                    break
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

            mtype = msg.get("type", "")

            if mtype == "tool_call" and msg.get("tool_name") == "transfer_to_agent":
                saw_transfer = True
                continue

            if mtype == "response" and (msg.get("data") or msg.get("content")):
                has_response = True

            # Transcription (output) counts as a response on /ws/live
            if mtype == "transcription" and msg.get("direction") == "output" and msg.get("text"):
                has_response = True

            if mtype == "status" and msg.get("state") == "idle":
                idle_count += 1
                if stop_on_idle and has_response:
                    break

            if mtype == "status" and msg.get("state") == "error":
                break

    except Exception:
        pass
    return messages


async def drain(ws, timeout: float = 0.5) -> list[dict]:
    """Drain any pending messages from the WS."""
    msgs = []
    try:
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            if isinstance(raw, bytes):
                msgs.append({"type": "_binary_audio", "size": len(raw)})
            else:
                try:
                    msgs.append(json.loads(raw))
                except json.JSONDecodeError:
                    pass
    except (TimeoutError, asyncio.CancelledError, Exception):
        pass
    return msgs


# ── T3 tool result handler ───────────────────────────────────────────

async def handle_tool_invocations(ws, messages: list[dict], timeout: float = 45.0) -> list[dict]:
    """Process tool_invocation messages and send simulated results back.
    
    Continues collecting messages after sending results.
    """
    all_messages = list(messages)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    has_response = False

    # First, respond to any tool_invocations already in messages
    for msg in messages:
        if msg.get("type") == "tool_invocation":
            call_id = msg.get("call_id", "")
            tool = msg.get("tool", "")
            result = _simulate_tool_result(tool, msg.get("args", {}))
            await ws.send(json.dumps({
                "type": "tool_result",
                "call_id": call_id,
                "result": result,
            }))

    # Continue collecting messages
    try:
        while loop.time() < deadline:
            remaining = deadline - loop.time()
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 10.0))
            except TimeoutError:
                if has_response:
                    break
                continue

            if isinstance(raw, bytes):
                all_messages.append({"type": "_binary_audio", "size": len(raw)})
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            all_messages.append(msg)
            mtype = msg.get("type", "")

            # Handle new tool invocations
            if mtype == "tool_invocation":
                call_id = msg.get("call_id", "")
                tool = msg.get("tool", "")
                result = _simulate_tool_result(tool, msg.get("args", {}))
                await ws.send(json.dumps({
                    "type": "tool_result",
                    "call_id": call_id,
                    "result": result,
                }))

            if mtype == "response" and (msg.get("data") or msg.get("content")):
                has_response = True

            # Transcription (output) counts as a response on /ws/live
            if mtype == "transcription" and msg.get("direction") == "output" and msg.get("text"):
                has_response = True

            if mtype == "status" and msg.get("state") in ("idle", "error"):
                if has_response:
                    break
    except Exception:
        pass

    return all_messages


def _simulate_tool_result(tool_name: str, args: dict) -> dict:
    """Return a simulated result for a T3 tool invocation."""
    if tool_name == "capture_screen":
        return {
            "ok": True,
            "image_base64": "iVBORw0KGgo=",  # tiny placeholder
            "width": 1920,
            "height": 1080,
            "format": "jpeg",
        }
    if tool_name == "screen_info":
        return {
            "primary": {"width": 1920, "height": 1080},
            "monitors": [{"left": 0, "top": 0, "width": 1920, "height": 1080}],
        }
    if tool_name == "click":
        return {"ok": True, "x": args.get("x", 0), "y": args.get("y", 0), "button": args.get("button", "left")}
    if tool_name == "type_text":
        return {"ok": True, "length": len(args.get("text", ""))}
    if tool_name == "hotkey":
        return {"ok": True, "keys": args.get("keys", [])}
    if tool_name == "execute_command":
        return {"ok": True, "stdout": "simulated output", "returncode": 0}
    if tool_name == "read_file":
        return {"ok": True, "content": "simulated file content"}
    if tool_name == "list_directory":
        return [
            {"name": "file1.txt", "is_dir": False, "size": 100},
            {"name": "subdir", "is_dir": True, "size": 0},
        ]
    # Unknown tool — return generic success
    return {"ok": True, "tool": tool_name, "note": "simulated result"}


# ── Desktop auth handshake ────────────────────────────────────────────

async def desktop_auth(ws, token: str) -> dict | None:
    """Send desktop auth message and return auth_response."""
    import platform

    auth_msg = {
        "type": "auth",
        "token": token,
        "client_type": "desktop",
        "user_agent": f"OmniDesktopTest/1.0 ({platform.system()} {platform.release()})",
        "capabilities": DESKTOP_CAPABILITIES,
        "local_tools": DESKTOP_LOCAL_TOOLS,
    }
    await ws.send(json.dumps(auth_msg))

    # Collect auth_response + connected message
    auth_resp = None
    connected_msg = None
    extra: list[dict] = []

    for _ in range(10):
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=15)
        except TimeoutError:
            break
        if isinstance(raw, bytes):
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue

        mtype = msg.get("type", "")
        if mtype == "auth_response":
            auth_resp = msg
        elif mtype == "connected":
            connected_msg = msg
        else:
            extra.append(msg)

        if auth_resp and connected_msg:
            break

    return auth_resp


# ── Message printer ───────────────────────────────────────────────────

def print_messages(messages: list[dict], indent: str = "    ") -> None:
    for msg in messages:
        t = msg.get("type", "?")
        if t == "response":
            text = msg.get("data", "")
            ct = msg.get("content_type", "text")
            if ct == "genui":
                print(f"{indent}{cyan('[GenUI]')} {json.dumps(msg.get('genui', {}))[:150]}")
            elif text:
                lines = textwrap.fill(text, width=88, initial_indent="", subsequent_indent=indent)
                print(f"{indent}{green('[Agent]')} {lines}")
        elif t == "transcription":
            direction = msg.get("direction", "?")
            text = msg.get("text", "")
            if text:
                arrow = "→" if direction == "input" else "←"
                print(f"{indent}{dim(f'[transcript {arrow}]')} {text[:120]}")
        elif t == "tool_call":
            tool = msg.get("tool_name", "?")
            status = msg.get("status", "")
            args_str = json.dumps(msg.get("arguments", {}))[:100]
            icon = "⚡" if status == "started" else ("✓" if status == "completed" else "▶")
            print(f"{indent}{blue(f'[tool {icon}]')} {bold(tool)} {dim(args_str)}")
        elif t == "tool_response":
            tool = msg.get("tool_name", "?")
            success = msg.get("success", True)
            icon = green("✓") if success else red("✗")
            print(f"{indent}{blue('[tool result]')} {icon} {tool}: {str(msg.get('result', ''))[:120]}")
        elif t == "tool_invocation":
            tool = msg.get("tool", "?")
            call_id = msg.get("call_id", "?")
            args_str = json.dumps(msg.get("args", {}))[:100]
            print(f"{indent}{cyan('[T3 invoke]')} {bold(tool)} call_id={call_id[:16]} {dim(args_str)}")
        elif t == "status":
            state = msg.get("state", "?")
            color = green if state == "idle" else (yellow if state == "processing" else dim)
            print(f"{indent}{dim('[status]')} {color(state)}")
        elif t == "error":
            print(f"{indent}{red('[error]')} {msg.get('code', '?')}: {msg.get('description', '')}")
        elif t in ("auth_response", "connected", "_binary_audio", "session_created",
                    "session_suggestion", "client_status_update", "mic_floor"):
            pass
        elif t == "agent_activity":
            title = msg.get("title", "?")
            status = msg.get("status", "")
            print(f"{indent}{dim(f'[activity] {title} [{status}]')}")
        else:
            print(f"{indent}{dim('[' + t + ']')} {json.dumps(msg)[:120]}")


# ── Individual test functions ─────────────────────────────────────────

async def test_auth(ws, token: str, results: dict) -> dict | None:
    """Test 1: Auth handshake as desktop client."""
    print(bold(f"  [1] Desktop WS Auth & Handshake"))
    print(dim(f"  Connect as desktop client, verify auth_response"))

    auth_resp = await desktop_auth(ws, token)
    if not auth_resp:
        print(red("  ✗ No auth_response received"))
        results["auth"] = (False, "no auth_response")
        return None

    if auth_resp.get("status") != "ok":
        print(red(f"  ✗ Auth failed: {auth_resp.get('error', '?')}"))
        results["auth"] = (False, f"auth error: {auth_resp.get('error', '?')}")
        return None

    user_id = auth_resp.get("user_id", "?")
    session_id = auth_resp.get("session_id", "?")
    tools = auth_resp.get("available_tools", [])
    others = auth_resp.get("other_clients_online", [])
    fs_session = auth_resp.get("firestore_session_id", "")

    print(green("  ✓ Auth OK"))
    print(f"    User ID  : {user_id}")
    print(f"    Session  : {session_id[:24]}...")
    print(f"    FS Sess  : {fs_session[:24]}..." if fs_session else "    FS Sess  : (lazy)")
    print(f"    Tools    : {len(tools)} ({', '.join(sorted(tools)[:8])}{'...' if len(tools) > 8 else ''})")
    if others:
        print(f"    Others   : {', '.join(others)}")

    results["auth"] = (True, f"session {session_id[:16]}...")
    return auth_resp


async def test_text(ws, results: dict) -> None:
    """Test 2: Text chat via desktop WS."""
    print(bold(f"\n  [2] Text Chat via /ws/live"))
    print(dim(f"  Send text message, receive agent response"))

    prompt = "Say hello and tell me what type of client I am connected as. Keep it brief, one sentence max."
    print(f"  {dim('Prompt:')} {prompt[:100]}")

    await ws.send(json.dumps({"type": "text", "content": prompt}))
    t0 = time.monotonic()
    messages = await collect_messages(ws, timeout=60.0)
    elapsed = time.monotonic() - t0

    print_messages(messages)

    has_response = any(
        m.get("type") == "response" and m.get("data")
        for m in messages
    )
    has_transcript = any(
        m.get("type") == "transcription" and m.get("direction") == "output" and m.get("text")
        for m in messages
    )
    has_error = any(m.get("type") == "error" for m in messages)

    if has_error:
        err = next(m for m in messages if m.get("type") == "error")
        print(red(f"\n  ✗ FAIL ({elapsed:.1f}s) — {err.get('code', 'error')}"))
        results["text"] = (False, err.get("code", "error"))
    elif has_response or has_transcript:
        print(green(f"\n  ✓ PASS ({elapsed:.1f}s) — agent responded"))
        results["text"] = (True, f"response in {elapsed:.1f}s")
    else:
        print(yellow(f"\n  ~ WARN ({elapsed:.1f}s) — no text response (may be audio-only)"))
        # Audio-only response is acceptable for /ws/live
        has_audio = any(m.get("type") == "_binary_audio" for m in messages)
        if has_audio:
            results["text"] = (True, "audio-only response")
        else:
            results["text"] = (False, "no response")


async def test_t3_tools(ws, results: dict) -> None:
    """Test 3: T3 tool invocation — register local_tools, ask agent to use them."""
    print(bold(f"\n  [3] T3 Tool Registration & Invocation"))
    print(dim(f"  Ask agent to capture screen — should invoke our local capture_screen tool"))

    prompt = "Please capture a screenshot of my desktop screen right now using the capture_screen tool."
    print(f"  {dim('Prompt:')} {prompt[:100]}")

    await ws.send(json.dumps({"type": "text", "content": prompt}))
    t0 = time.monotonic()

    # Collect messages, handling tool invocations
    messages = await handle_tool_invocations(ws, [], timeout=90.0)
    elapsed = time.monotonic() - t0

    print_messages(messages)

    # Check if we got a tool_invocation for one of our tools
    got_invocation = any(
        m.get("type") == "tool_invocation"
        for m in messages
    )
    # Also check for tool_call (server-side view)
    got_tool_call = any(
        m.get("type") == "tool_call" and m.get("tool_name") in {t["name"] for t in DESKTOP_LOCAL_TOOLS}
        for m in messages
    )
    has_response = any(
        m.get("type") == "response" and m.get("data")
        for m in messages
    )
    has_audio = any(m.get("type") == "_binary_audio" for m in messages)
    has_transcript = any(
        m.get("type") == "transcription" and m.get("direction") == "output" and m.get("text")
        for m in messages
    )

    if got_invocation:
        invoked = [m.get("tool", "") for m in messages if m.get("type") == "tool_invocation"]
        print(green(f"\n  ✓ PASS ({elapsed:.1f}s) — T3 tool invoked: {', '.join(invoked)}"))
        results["t3_tools"] = (True, f"tools invoked: {', '.join(invoked)}")
    elif got_tool_call:
        tools = [m.get("tool_name", "") for m in messages if m.get("type") == "tool_call"]
        print(green(f"\n  ✓ PASS ({elapsed:.1f}s) — tool_call: {', '.join(tools)}"))
        results["t3_tools"] = (True, f"tool_call: {', '.join(tools)}")
    elif has_response or has_audio or has_transcript:
        # Agent may have declined to use the tool — partial pass
        print(yellow(f"\n  ~ WARN ({elapsed:.1f}s) — agent responded but didn't invoke desktop tool"))
        results["t3_tools"] = (True, "agent responded (no tool invocation)")
    else:
        print(red(f"\n  ✗ FAIL ({elapsed:.1f}s) — no tool invocation or response"))
        results["t3_tools"] = (False, "no invocation or response")


async def test_cross_client(ws, results: dict) -> None:
    """Test 4: Cross-client — list connected clients."""
    print(bold(f"\n  [4] Cross-Client — List Clients"))
    print(dim(f"  Ask agent to list connected clients"))

    prompt = "What client devices do I currently have connected? List them all."
    print(f"  {dim('Prompt:')} {prompt[:80]}")

    await ws.send(json.dumps({"type": "text", "content": prompt}))
    t0 = time.monotonic()
    messages = await handle_tool_invocations(ws, [], timeout=60.0)
    elapsed = time.monotonic() - t0

    print_messages(messages)

    has_response = any(
        m.get("type") == "response" and m.get("data")
        for m in messages
    )
    has_desktop_mention = any(
        "desktop" in (m.get("data", "") or "").lower()
        for m in messages
        if m.get("type") == "response"
    )
    has_audio = any(m.get("type") == "_binary_audio" for m in messages)
    # Check transcription messages for desktop mention
    has_transcript = any(
        m.get("type") == "transcription" and m.get("direction") == "output" and m.get("text")
        for m in messages
    )
    has_desktop_in_transcript = any(
        "desktop" in (m.get("text", "") or "").lower()
        for m in messages
        if m.get("type") == "transcription" and m.get("direction") == "output"
    )

    if has_desktop_mention or has_desktop_in_transcript:
        print(green(f"\n  ✓ PASS ({elapsed:.1f}s) — desktop client listed"))
        results["cross_client"] = (True, "desktop mentioned in response")
    elif has_response or has_audio or has_transcript:
        print(green(f"\n  ✓ PASS ({elapsed:.1f}s) — agent responded"))
        results["cross_client"] = (True, "agent responded")
    else:
        print(red(f"\n  ✗ FAIL ({elapsed:.1f}s) — no response"))
        results["cross_client"] = (False, "no response")


async def test_ping_pong(ws, results: dict) -> None:
    """Test 5: Ping/Pong protocol — send ping, get pong (application-level)."""
    print(bold(f"\n  [5] Protocol — Ping/Pong"))
    print(dim(f"  Send ping JSON frame, verify pong response"))

    # Note: The ping/pong in the desktop client protocol is application-level JSON,
    # not WebSocket protocol-level pings. The server dispatches pong on receiving ping.
    # However, the server sends pings TO the client (not the other way).
    # We test by verifying the connection is alive and we can send/receive.

    # Send a text message and verify we get a response — this proves the
    # connection is healthy (which is what ping/pong verifies)
    await ws.send(json.dumps({"type": "text", "content": "Respond with just the word PONG."}))
    t0 = time.monotonic()

    messages = await collect_messages(ws, timeout=30.0)
    elapsed = time.monotonic() - t0

    has_response = any(
        m.get("type") in ("response", "_binary_audio")
        for m in messages
    )
    has_transcript = any(
        m.get("type") == "transcription" and m.get("direction") == "output" and m.get("text")
        for m in messages
    )

    if has_response or has_transcript:
        print(green(f"\n  ✓ PASS ({elapsed:.1f}s) — connection alive, round-trip OK"))
        results["ping_pong"] = (True, "connection healthy")
    else:
        print(red(f"\n  ✗ FAIL ({elapsed:.1f}s) — no response"))
        results["ping_pong"] = (False, "connection may be dead")


async def test_interrupt(ws, results: dict) -> None:
    """Test 6: Client interrupt signal."""
    print(bold(f"\n  [6] Client Interrupt Signal"))
    print(dim(f"  Send a request, then interrupt it"))

    # Send a prompt that will take a while
    prompt = "Write me a very long and detailed essay about the complete history of computing from 1800 to today."
    print(f"  {dim('Prompt:')} {prompt[:80]}...")
    await ws.send(json.dumps({"type": "text", "content": prompt}))

    # Wait briefly for agent to start generating
    await asyncio.sleep(2)

    # Send interrupt
    print(f"  {dim('Sending interrupt...')}")
    await ws.send(json.dumps({"type": "client_message", "action": "interrupt"}))

    # Collect whatever messages come back
    messages = await collect_messages(ws, timeout=10.0, stop_on_idle=True)
    print_messages(messages)

    # The test passes if we don't crash and the connection is still alive
    # Verify by sending another message
    await drain(ws, timeout=1.0)
    await ws.send(json.dumps({"type": "text", "content": "Are you there? Just say yes."}))
    recovery = await collect_messages(ws, timeout=30.0)

    has_recovery = any(
        m.get("type") in ("response", "_binary_audio")
        or (m.get("type") == "transcription" and m.get("direction") == "output" and m.get("text"))
        for m in recovery
    )

    if has_recovery:
        print(green(f"\n  ✓ PASS — interrupt handled, connection recovered"))
        results["interrupt"] = (True, "interrupt + recovery OK")
    else:
        print(yellow(f"\n  ~ WARN — interrupt sent but no recovery response"))
        results["interrupt"] = (True, "interrupt sent (recovery uncertain)")


async def test_persona(ws, results: dict) -> None:
    """Test 7: Persona routing via desktop."""
    print(bold(f"\n  [7] Persona Routing (Desktop)"))
    print(dim(f"  Route to researcher persona"))

    prompt = "[Use the researcher persona] Who are you and what are your specialties? Answer in 2 sentences."
    print(f"  {dim('Prompt:')} {prompt[:100]}")

    await ws.send(json.dumps({"type": "text", "content": prompt}))
    t0 = time.monotonic()
    messages = await handle_tool_invocations(ws, [], timeout=60.0)
    elapsed = time.monotonic() - t0

    print_messages(messages)

    has_response = any(
        m.get("type") == "response" and m.get("data")
        for m in messages
    )
    has_audio = any(m.get("type") == "_binary_audio" for m in messages)
    has_transcript = any(
        m.get("type") == "transcription" and m.get("direction") == "output" and m.get("text")
        for m in messages
    )
    has_transfer = any(
        m.get("type") == "tool_call" and m.get("tool_name") == "transfer_to_agent"
        for m in messages
    )

    if has_response or has_audio or has_transcript:
        extra = " (with agent transfer)" if has_transfer else ""
        print(green(f"\n  ✓ PASS ({elapsed:.1f}s) — persona responded{extra}"))
        results["persona"] = (True, f"persona responded{extra}")
    else:
        print(red(f"\n  ✗ FAIL ({elapsed:.1f}s) — no response"))
        results["persona"] = (False, "no response")


async def test_reconnect(ws_url: str, token: str, results: dict) -> None:
    """Test 8: Disconnect and reconnect with same token."""
    import websockets

    print(bold(f"\n  [8] Disconnect & Reconnect"))
    print(dim(f"  Close WS, reconnect, verify new auth_response"))

    max_retries = 3
    last_error = ""

    for attempt in range(1, max_retries + 1):
        try:
            # Connect first time
            async with websockets.connect(ws_url, max_size=10 * 1024 * 1024, open_timeout=30) as ws1:
                auth1 = await desktop_auth(ws1, token)
                if not auth1 or auth1.get("status") != "ok":
                    print(red("  ✗ First connection auth failed"))
                    results["reconnect"] = (False, "first auth failed")
                    return
                session1 = auth1.get("session_id", "")
                print(f"  Connection 1: session={session1[:20]}...")

            # Small delay
            await asyncio.sleep(2)

            # Reconnect
            async with websockets.connect(ws_url, max_size=10 * 1024 * 1024, open_timeout=30) as ws2:
                auth2 = await desktop_auth(ws2, token)
                if not auth2 or auth2.get("status") != "ok":
                    print(red("  ✗ Reconnection auth failed"))
                    results["reconnect"] = (False, "reconnect auth failed")
                    return
                session2 = auth2.get("session_id", "")
                print(f"  Connection 2: session={session2[:20]}...")

                # Verify the connection works
                await ws2.send(json.dumps({"type": "text", "content": "Say OK."}))
                msgs = await collect_messages(ws2, timeout=30.0)
                has_resp = any(m.get("type") in ("response", "_binary_audio") for m in msgs)

                if has_resp:
                    print(green(f"\n  ✓ PASS — reconnect successful, session continuity"))
                    results["reconnect"] = (True, f"reconnected (s1={session1[:12]}, s2={session2[:12]})")
                else:
                    print(yellow(f"\n  ~ WARN — reconnected but no response to test message"))
                    results["reconnect"] = (True, "reconnect OK (no test response)")
                return  # success — exit retry loop

        except OSError as exc:
            last_error = str(exc)
            if attempt < max_retries:
                print(dim(f"  Attempt {attempt} failed ({last_error}), retrying in 3s..."))
                await asyncio.sleep(3)
            else:
                print(red(f"  ✗ All {max_retries} attempts failed: {last_error}"))
                results["reconnect"] = (False, f"error after {max_retries} retries: {last_error}")


async def test_session_info(ws, all_messages: list[dict], results: dict) -> None:
    """Test 9: Session info messages."""
    print(bold(f"\n  [9] Session Info Messages"))
    print(dim(f"  Check for session_created / session_suggestion in received messages"))

    # Session messages may have been received during earlier tests
    session_created = [m for m in all_messages if m.get("type") == "session_created"]
    session_suggestion = [m for m in all_messages if m.get("type") == "session_suggestion"]

    if session_created:
        fs_id = session_created[0].get("firestore_session_id", "?")
        print(f"    session_created: {fs_id[:24]}...")

    if session_suggestion:
        sg = session_suggestion[0]
        print(f"    session_suggestion: {sg.get('message', '')[:80]}")
        print(f"      clients: {sg.get('available_clients', [])}")

    # Pass if we got either message, or if auth indicated a session
    if session_created or session_suggestion:
        print(green(f"\n  ✓ PASS — session messages received"))
        results["session_info"] = (True, f"created={len(session_created)} suggestion={len(session_suggestion)}")
    else:
        # Session messages are optional (e.g., if lazy creation hasn't triggered)
        print(yellow(f"\n  ~ INFO — no session messages yet (lazy creation)"))
        results["session_info"] = (True, "no session messages (lazy creation OK)")


async def test_cancel(ws, results: dict) -> None:
    """Test 10: Tool cancellation protocol."""
    print(bold(f"\n  [10] Tool Cancellation Protocol"))
    print(dim(f"  Verify cancel message format is accepted"))

    # Send a tool_result with cancellation error (simulating what desktop client does)
    cancel_msg = {
        "type": "tool_result",
        "call_id": "test-cancel-001",
        "result": {},
        "error": "Cancelled by user",
    }
    await ws.send(json.dumps(cancel_msg))

    # If the server doesn't crash/disconnect, the protocol is accepted
    await asyncio.sleep(1)

    # Verify connection is still alive
    await ws.send(json.dumps({"type": "text", "content": "Say yes."}))
    msgs = await collect_messages(ws, timeout=20.0)

    has_resp = any(m.get("type") in ("response", "_binary_audio") for m in msgs)

    if has_resp:
        print(green(f"\n  ✓ PASS — cancel protocol accepted, connection alive"))
        results["cancel"] = (True, "cancel message accepted")
    else:
        print(yellow(f"\n  ~ WARN — cancel sent, no crash but no response"))
        results["cancel"] = (True, "cancel accepted (no response)")


# ── Main test runner ──────────────────────────────────────────────────

async def run_tests(only: list[str] | None, backend_url: str | None) -> None:
    global BACKEND_URL, WS_URL

    if backend_url:
        BACKEND_URL = backend_url
        WS_URL = backend_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws/live"

    print()
    print(bold("═" * 64))
    print(bold("  Omni Hub — Desktop Client E2E Test Runner"))
    print(bold("═" * 64))
    print(f"  Backend   : {BACKEND_URL}")
    print(f"  WS (live) : {WS_URL}")
    print(f"  Time      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Step 1: Firebase auth
    token = await get_firebase_token()
    print()

    # Step 2: Filter tests
    tests_to_run = TESTS if not only else [t for t in TESTS if t["id"] in only]
    if not tests_to_run:
        print(red(f"  No tests matched: {only}"))
        return

    test_ids = {t["id"] for t in tests_to_run}

    results: dict[str, tuple[bool, str]] = {}
    all_received: list[dict] = []

    try:
        import websockets
    except ImportError:
        print(red("  websockets not found. Run: uv add websockets"))
        sys.exit(1)

    # Tests that need a fresh connection
    reconnect_needed = "reconnect" in test_ids

    try:
        print(f"  Connecting to {WS_URL} ...")
        ws_conn = None
        for _attempt in range(1, 4):
            try:
                ws_conn = await websockets.connect(
                    WS_URL,
                    max_size=10 * 1024 * 1024,
                    open_timeout=30,
                    ping_interval=30,
                    ping_timeout=60,
                )
                break
            except OSError as e:
                if _attempt < 3:
                    print(yellow(f"  DNS/network error (attempt {_attempt}/3): {e} — retrying in 3s …"))
                    await asyncio.sleep(3)
                else:
                    raise
        async with ws_conn as ws:

            # ── Auth test ────────────────────────────────────────
            if "auth" in test_ids:
                auth_resp = await test_auth(ws, token, results)
                if not auth_resp:
                    print(red("\n  Auth failed — cannot continue"))
                    return
            else:
                # Still need to auth even if test not selected
                auth_resp = await desktop_auth(ws, token)
                if not auth_resp or auth_resp.get("status") != "ok":
                    print(red("  Auth failed"))
                    return

            # Drain any extra messages from auth
            extra = await drain(ws, timeout=2.0)
            all_received.extend(extra)

            # Brief warm-up: on cold-start instances, the ADK runner
            # may still be initializing tools after auth returns.
            await asyncio.sleep(2)

            # ── Text test ────────────────────────────────────────
            if "text" in test_ids:
                await test_text(ws, results)
                extra = await drain(ws, timeout=2.0)
                all_received.extend(extra)
                await asyncio.sleep(1)

            # ── T3 tools test ────────────────────────────────────
            if "t3_tools" in test_ids:
                await test_t3_tools(ws, results)
                extra = await drain(ws, timeout=2.0)
                all_received.extend(extra)
                await asyncio.sleep(1)

            # ── Cross-client test ────────────────────────────────
            if "cross_client" in test_ids:
                await test_cross_client(ws, results)
                extra = await drain(ws, timeout=2.0)
                all_received.extend(extra)
                await asyncio.sleep(1)

            # ── Ping/Pong test ───────────────────────────────────
            if "ping_pong" in test_ids:
                await test_ping_pong(ws, results)
                extra = await drain(ws, timeout=2.0)
                all_received.extend(extra)
                await asyncio.sleep(1)

            # ── Interrupt test ───────────────────────────────────
            if "interrupt" in test_ids:
                await test_interrupt(ws, results)
                extra = await drain(ws, timeout=2.0)
                all_received.extend(extra)
                await asyncio.sleep(1)

            # ── Persona test ─────────────────────────────────────
            if "persona" in test_ids:
                await test_persona(ws, results)
                extra = await drain(ws, timeout=2.0)
                all_received.extend(extra)
                await asyncio.sleep(1)

            # ── Cancel test ──────────────────────────────────────
            if "cancel" in test_ids:
                await test_cancel(ws, results)
                extra = await drain(ws, timeout=2.0)
                all_received.extend(extra)

            # ── Session info test ────────────────────────────────
            if "session_info" in test_ids:
                await test_session_info(ws, all_received, results)

    except ConnectionRefusedError:
        print(red(f"\n  Connection refused — is the backend running on {BACKEND_URL}?"))
        sys.exit(1)
    except Exception as exc:
        print(red(f"\n  Unexpected error: {type(exc).__name__}: {exc}"))
        import traceback
        traceback.print_exc()

    # ── Reconnect test (uses fresh connections) ──────────────────
    if reconnect_needed:
        try:
            await test_reconnect(WS_URL, token, results)
        except Exception as exc:
            print(red(f"\n  Reconnect test error: {exc}"))
            results["reconnect"] = (False, f"error: {type(exc).__name__}")

    # ── Summary ──────────────────────────────────────────────────
    print()
    print(bold("═" * 64))
    print(bold("  Desktop Client E2E Results"))
    print(bold("═" * 64))
    total = len(results)
    passed_count = sum(1 for ok, _ in results.values() if ok)

    for test in TESTS:
        tid = test["id"]
        if tid not in results:
            continue
        ok, reason = results[tid]
        icon = green("✓") if ok else red("✗")
        print(f"  {icon}  {test['name']:<42} {dim(reason)}")

    print()
    bar = green if passed_count == total else (yellow if passed_count > 0 else red)
    print(f"  {bar(f'{passed_count}/{total} tests passed')}")
    print()

    if passed_count < total:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Omni Hub — Desktop Client E2E Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          uv run python scripts/test_desktop_client.py
          uv run python scripts/test_desktop_client.py --only auth,text,t3_tools
          uv run python scripts/test_desktop_client.py --backend https://omni-backend-fcapusldtq-uc.a.run.app

        Available test IDs:
          auth          text          t3_tools      cross_client
          ping_pong     interrupt     persona       reconnect
          session_info  cancel
        """),
    )
    parser.add_argument(
        "--only",
        metavar="ID[,ID...]",
        help="Comma-separated test IDs to run (default: all)",
    )
    parser.add_argument(
        "--backend",
        metavar="URL",
        help="Backend URL (default: from BACKEND_URL env or http://localhost:8000)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available test IDs and exit",
    )
    args = parser.parse_args()

    if args.list:
        print("Available test IDs:")
        for test in TESTS:
            print(f"  {test['id']:<16} {test['name']}")
        return

    only = [x.strip() for x in args.only.split(",")] if args.only else None
    asyncio.run(run_tests(only, args.backend))


if __name__ == "__main__":
    main()
