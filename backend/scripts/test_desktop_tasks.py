#!/usr/bin/env python3
"""
Omni Hub — Desktop Task Test Runner
====================================
Tests real-world desktop tasks:
  1. File creation (write_file)
  2. Application opening (open_app / execute_command)
  3. Video playback (execute_command to open video)
  4. Opening photos folder (execute_command / list_directory)

Connects as a 'web' client (since the desktop client is already running)
and asks the agent to perform tasks on the desktop using T3 tools.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/test_desktop_tasks.py              # all
    .venv/Scripts/python.exe scripts/test_desktop_tasks.py --only file   # single
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

# ── Load .env from backend root ──
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

FIREBASE_API_KEY = os.environ["FIREBASE_WEB_API_KEY"]
EMAIL = os.environ["TEST_USER_EMAIL"]
PASSWORD = os.environ["TEST_USER_PASSWORD"]

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
_default_ws = BACKEND_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws/live"
WS_URL = os.getenv("WS_LIVE_URL", _default_ws)

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


# ── Firebase Auth ─────────────────────────────────────────────────────

async def get_firebase_token() -> str:
    import httpx
    print(f"  Signing in as {bold(EMAIL)} ...")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}",
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

async def collect_messages(ws, timeout: float = 90.0) -> list[dict]:
    """Receive messages until idle + response, or timeout."""
    messages: list[dict] = []
    has_response = False
    has_tool = False
    idle_count = 0
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    try:
        while loop.time() < deadline:
            remaining = deadline - loop.time()
            silence = 15.0 if has_tool else 10.0
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, silence))
            except TimeoutError:
                if has_response or (has_tool and idle_count >= 2):
                    break
                continue

            if isinstance(raw, bytes):
                messages.append({"type": "_binary_audio", "size": len(raw)})
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            # Skip cross_client broadcast messages for idle detection
            if msg.get("cross_client"):
                continue

            messages.append(msg)
            mtype = msg.get("type", "")

            if mtype == "tool_call":
                has_tool = True
                idle_count = 0  # reset idle counter on new tool activity
            if mtype == "tool_response":
                has_tool = True
            if mtype == "response" and msg.get("data"):
                has_response = True
            if mtype == "transcription" and msg.get("direction") == "output" and msg.get("text"):
                has_response = True
            if mtype == "status" and msg.get("state") == "idle":
                idle_count += 1
                # Only break when we have a response, or seen idle multiple times after tools
                if has_response:
                    break
                if has_tool and idle_count >= 2:
                    break
    except Exception:
        pass
    return messages


async def drain(ws, timeout: float = 1.0) -> None:
    try:
        while True:
            await asyncio.wait_for(ws.recv(), timeout=timeout)
    except Exception:
        pass


def print_messages(messages: list[dict], indent: str = "    ") -> None:
    for msg in messages:
        t = msg.get("type", "?")
        if t == "response":
            text = msg.get("data", "")
            if text:
                lines = textwrap.fill(text, width=88)
                print(f"{indent}{green('[Agent]')} {lines[:200]}")
        elif t == "transcription":
            direction = msg.get("direction", "?")
            text = msg.get("text", "")
            if text and msg.get("finished"):
                arrow = "→" if direction == "input" else "←"
                print(f"{indent}{dim(f'[transcript {arrow}]')} {text[:150]}")
        elif t == "tool_call":
            tool = msg.get("tool_name", "?")
            args_str = json.dumps(msg.get("arguments", {}))[:200]
            print(f"{indent}{blue('[tool]')} {bold(tool)} {dim(args_str)}")
        elif t == "tool_response":
            tool = msg.get("tool_name", "?")
            success = msg.get("success", True)
            result_str = str(msg.get("result", ""))[:200]
            icon = green("✓") if success else red("✗")
            print(f"{indent}{blue('[result]')} {icon} {tool}: {result_str}")
        elif t == "status":
            state = msg.get("state", "?")
            detail = msg.get("detail", "")
            color = green if state == "idle" else yellow
            if detail:
                print(f"{indent}{dim('[status]')} {color(state)} {dim(detail)}")
            else:
                print(f"{indent}{dim('[status]')} {color(state)}")
        elif t in ("auth_response", "connected", "_binary_audio",
                    "session_suggestion", "client_status_update", "mic_floor"):
            pass
        elif t == "error":
            print(f"{indent}{red('[error]')} {msg.get('code', '')}: {msg.get('description', '')}")
        else:
            print(f"{indent}{dim('[' + t + ']')} {json.dumps(msg)[:120]}")


# ── Auth helper ───────────────────────────────────────────────────────

async def ws_auth(ws, token: str) -> dict | None:
    """Auth as web client and return auth_response."""
    auth_msg = {
        "type": "auth",
        "token": token,
        "client_type": "web",
        "capabilities": ["microphone", "speaker"],
    }
    await ws.send(json.dumps(auth_msg))

    auth_resp = None
    for _ in range(10):
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
        except TimeoutError:
            break
        if isinstance(raw, bytes):
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if msg.get("type") == "auth_response":
            auth_resp = msg
        elif msg.get("type") == "connected":
            if auth_resp:
                break
    return auth_resp


# ── Test functions ────────────────────────────────────────────────────

async def test_file_creation(ws, results: dict) -> None:
    """Test 1: Create a file on the desktop using write_file tool."""
    print(bold("\n  [1] File Creation (write_file)"))
    print(dim("  Ask agent to create a text file on the desktop"))

    prompt = (
        "I need you to create a text file. Use the write_file tool to create a file at "
        "~/Desktop/omni_test.txt with the content: "
        "'Hello from Omni Agent! This file was created by the AI assistant.'"
    )
    print(f"  {dim('Prompt:')} {prompt[:100]}...")

    await ws.send(json.dumps({"type": "text", "content": prompt}))
    t0 = time.monotonic()
    messages = await collect_messages(ws, timeout=90.0)
    elapsed = time.monotonic() - t0

    print_messages(messages)

    # Check results
    used_write = any(
        m.get("type") == "tool_call" and m.get("tool_name") == "write_file"
        for m in messages
    )
    write_ok = any(
        m.get("type") == "tool_response" and m.get("tool_name") == "write_file"
        and "ok" in str(m.get("result", "")).lower()
        for m in messages
    )
    has_response = any(
        m.get("type") in ("response", "_binary_audio")
        or (m.get("type") == "transcription" and m.get("direction") == "output")
        for m in messages
    )

    if used_write and write_ok:
        print(green(f"\n  ✓ PASS ({elapsed:.1f}s) — write_file called and succeeded"))
        results["file"] = (True, "file created successfully")
    elif used_write:
        print(yellow(f"\n  ~ WARN ({elapsed:.1f}s) — write_file called but unclear result"))
        results["file"] = (True, "write_file called")
    elif has_response:
        print(yellow(f"\n  ~ WARN ({elapsed:.1f}s) — agent responded but didn't use write_file"))
        results["file"] = (False, "no write_file invocation")
    else:
        print(red(f"\n  ✗ FAIL ({elapsed:.1f}s) — no response"))
        results["file"] = (False, "no response")


async def test_open_app(ws, results: dict) -> None:
    """Test 2: Open an application (Notepad)."""
    print(bold("\n  [2] Application Opening (open_app)"))
    print(dim("  Ask agent to open Notepad on the desktop"))

    prompt = (
        "Open the Notepad application on my desktop. Use the open_app tool with name 'notepad'."
    )
    print(f"  {dim('Prompt:')} {prompt[:100]}...")

    await ws.send(json.dumps({"type": "text", "content": prompt}))
    t0 = time.monotonic()
    messages = await collect_messages(ws, timeout=90.0)
    elapsed = time.monotonic() - t0

    print_messages(messages)

    used_open_app = any(
        m.get("type") == "tool_call" and m.get("tool_name") == "open_app"
        for m in messages
    )
    used_execute = any(
        m.get("type") == "tool_call" and m.get("tool_name") == "execute_command"
        for m in messages
    )
    open_ok = any(
        m.get("type") == "tool_response"
        and m.get("tool_name") in ("open_app", "execute_command")
        and ("ok" in str(m.get("result", "")).lower() or "true" in str(m.get("result", "")).lower())
        for m in messages
    )
    has_response = any(
        m.get("type") in ("response", "_binary_audio")
        or (m.get("type") == "transcription" and m.get("direction") == "output")
        for m in messages
    )

    if (used_open_app or used_execute) and open_ok:
        tool = "open_app" if used_open_app else "execute_command"
        print(green(f"\n  ✓ PASS ({elapsed:.1f}s) — {tool} called, app launched"))
        results["open_app"] = (True, f"{tool} launched notepad")
    elif used_open_app or used_execute:
        print(yellow(f"\n  ~ WARN ({elapsed:.1f}s) — tool called but unclear result"))
        results["open_app"] = (True, "tool called")
    elif has_response:
        print(yellow(f"\n  ~ WARN ({elapsed:.1f}s) — agent responded without using desktop tools"))
        results["open_app"] = (False, "no desktop tool invocation")
    else:
        print(red(f"\n  ✗ FAIL ({elapsed:.1f}s) — no response"))
        results["open_app"] = (False, "no response")


async def test_play_video(ws, results: dict) -> None:
    """Test 3: Play a video file / open video player."""
    print(bold("\n  [3] Video Playback (execute_command)"))
    print(dim("  Ask agent to find and open a video file, or open a video player"))

    # We'll ask it to open a video — it'll use execute_command or open_app
    prompt = (
        "Search my Videos folder (~/Videos) for any video files. "
        "If you find one, open it with the default video player. "
        "If there are no videos, just open the Videos folder so I can see it. "
        "Use list_directory, then execute_command to open the result."
    )
    print(f"  {dim('Prompt:')} {prompt[:100]}...")

    await ws.send(json.dumps({"type": "text", "content": prompt}))
    t0 = time.monotonic()
    messages = await collect_messages(ws, timeout=90.0)
    elapsed = time.monotonic() - t0

    print_messages(messages)

    used_list_dir = any(
        m.get("type") == "tool_call" and m.get("tool_name") == "list_directory"
        for m in messages
    )
    used_execute = any(
        m.get("type") == "tool_call" and m.get("tool_name") == "execute_command"
        for m in messages
    )
    used_open_app = any(
        m.get("type") == "tool_call" and m.get("tool_name") == "open_app"
        for m in messages
    )
    used_any_tool = used_list_dir or used_execute or used_open_app
    has_response = any(
        m.get("type") in ("response", "_binary_audio")
        or (m.get("type") == "transcription" and m.get("direction") == "output")
        for m in messages
    )

    if used_any_tool:
        tools_used = []
        if used_list_dir: tools_used.append("list_directory")
        if used_execute: tools_used.append("execute_command")
        if used_open_app: tools_used.append("open_app")
        print(green(f"\n  ✓ PASS ({elapsed:.1f}s) — tools used: {', '.join(tools_used)}"))
        results["video"] = (True, f"tools: {', '.join(tools_used)}")
    elif has_response:
        print(yellow(f"\n  ~ WARN ({elapsed:.1f}s) — agent responded without desktop tools"))
        results["video"] = (False, "no desktop tool invocation")
    else:
        print(red(f"\n  ✗ FAIL ({elapsed:.1f}s) — no response"))
        results["video"] = (False, "no response")


async def test_open_photos_folder(ws, results: dict) -> None:
    """Test 4: Open the Photos/Pictures folder."""
    print(bold("\n  [4] Open Photos Folder"))
    print(dim("  Ask agent to list and open the Pictures folder"))

    prompt = (
        "List the contents of my Pictures folder (~/Pictures) using list_directory, "
        "then open that folder in the file explorer using execute_command with "
        "'explorer C:\\\\Users\\\\omana\\\\Pictures' on Windows."
    )
    print(f"  {dim('Prompt:')} {prompt[:100]}...")

    await ws.send(json.dumps({"type": "text", "content": prompt}))
    t0 = time.monotonic()
    messages = await collect_messages(ws, timeout=90.0)
    elapsed = time.monotonic() - t0

    print_messages(messages)

    used_list_dir = any(
        m.get("type") == "tool_call" and m.get("tool_name") == "list_directory"
        for m in messages
    )
    used_execute = any(
        m.get("type") == "tool_call" and m.get("tool_name") == "execute_command"
        for m in messages
    )
    used_open_app = any(
        m.get("type") == "tool_call" and m.get("tool_name") == "open_app"
        for m in messages
    )
    used_any_tool = used_list_dir or used_execute or used_open_app
    has_response = any(
        m.get("type") in ("response", "_binary_audio")
        or (m.get("type") == "transcription" and m.get("direction") == "output")
        for m in messages
    )

    if used_any_tool:
        tools_used = []
        if used_list_dir: tools_used.append("list_directory")
        if used_execute: tools_used.append("execute_command")
        if used_open_app: tools_used.append("open_app")
        print(green(f"\n  ✓ PASS ({elapsed:.1f}s) — tools used: {', '.join(tools_used)}"))
        results["photos"] = (True, f"tools: {', '.join(tools_used)}")
    elif has_response:
        print(yellow(f"\n  ~ WARN ({elapsed:.1f}s) — agent responded without desktop tools"))
        results["photos"] = (False, "no desktop tool invocation")
    else:
        print(red(f"\n  ✗ FAIL ({elapsed:.1f}s) — no response"))
        results["photos"] = (False, "no response")


async def test_open_folder(ws, results: dict) -> None:
    """Test 5: Open a specific folder in file explorer."""
    print(bold("\n  [5] Open Folder in Explorer"))
    print(dim("  Ask agent to open the Downloads folder"))

    prompt = (
        "Open my Downloads folder in File Explorer. "
        "Use execute_command with 'explorer ~\\Downloads' or appropriate command."
    )
    print(f"  {dim('Prompt:')} {prompt[:100]}...")

    await ws.send(json.dumps({"type": "text", "content": prompt}))
    t0 = time.monotonic()
    messages = await collect_messages(ws, timeout=90.0)
    elapsed = time.monotonic() - t0

    print_messages(messages)

    used_execute = any(
        m.get("type") == "tool_call" and m.get("tool_name") == "execute_command"
        for m in messages
    )
    used_open_app = any(
        m.get("type") == "tool_call" and m.get("tool_name") == "open_app"
        for m in messages
    )
    execute_ok = any(
        m.get("type") == "tool_response"
        and m.get("tool_name") in ("execute_command", "open_app")
        for m in messages
    )
    has_response = any(
        m.get("type") in ("response", "_binary_audio")
        or (m.get("type") == "transcription" and m.get("direction") == "output")
        for m in messages
    )

    if (used_execute or used_open_app) and execute_ok:
        print(green(f"\n  ✓ PASS ({elapsed:.1f}s) — folder opened"))
        results["folder"] = (True, "execute_command opened Downloads")
    elif used_execute or used_open_app:
        print(yellow(f"\n  ~ WARN ({elapsed:.1f}s) — tool called"))
        results["folder"] = (True, "tool called")
    elif has_response:
        print(yellow(f"\n  ~ WARN ({elapsed:.1f}s) — agent responded without desktop tools"))
        results["folder"] = (False, "no desktop tool invocation")
    else:
        print(red(f"\n  ✗ FAIL ({elapsed:.1f}s) — no response"))
        results["folder"] = (False, "no response")


# ── Test definitions ──────────────────────────────────────────────────

TESTS = [
    {"id": "file",     "name": "File Creation (write_file)",          "fn": "test_file_creation"},
    {"id": "open_app", "name": "Application Opening (open_app)",      "fn": "test_open_app"},
    {"id": "video",    "name": "Video Playback (browse + open)",      "fn": "test_play_video"},
    {"id": "photos",   "name": "Photos Folder (list + open)",         "fn": "test_open_photos_folder"},
    {"id": "folder",   "name": "Open Downloads Folder",               "fn": "test_open_folder"},
]


# ── Main runner ───────────────────────────────────────────────────────

async def run_tests(only: list[str] | None, backend_url: str | None) -> None:
    global BACKEND_URL, WS_URL

    if backend_url:
        BACKEND_URL = backend_url
        WS_URL = backend_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws/live"

    print()
    print(bold("═" * 64))
    print(bold("  Omni Hub — Desktop Task Test Runner"))
    print(bold("═" * 64))
    print(f"  Backend   : {BACKEND_URL}")
    print(f"  WS (live) : {WS_URL}")
    print(f"  Time      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    token = await get_firebase_token()
    print()

    tests_to_run = TESTS if not only else [t for t in TESTS if t["id"] in only]
    if not tests_to_run:
        print(red(f"  No tests matched: {only}"))
        return

    results: dict[str, tuple[bool, str]] = {}
    fn_map = {
        "test_file_creation": test_file_creation,
        "test_open_app": test_open_app,
        "test_play_video": test_play_video,
        "test_open_photos_folder": test_open_photos_folder,
        "test_open_folder": test_open_folder,
    }

    try:
        import websockets
    except ImportError:
        print(red("  websockets not found"))
        sys.exit(1)

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
            auth_resp = await ws_auth(ws, token)
            if not auth_resp or auth_resp.get("status") != "ok":
                print(red("  Auth failed — cannot continue"))
                return

            session = auth_resp.get("session_id", "?")
            tools = auth_resp.get("available_tools", [])
            print(green(f"  Connected: session={session[:20]}..."))
            print(f"  Available tools: {len(tools)} ({', '.join(sorted(tools)[:12])}{'...' if len(tools) > 12 else ''})")

            await drain(ws, timeout=2.0)
            await asyncio.sleep(2)

            for test_def in tests_to_run:
                fn = fn_map[test_def["fn"]]
                await fn(ws, results)
                await drain(ws, timeout=2.0)
                await asyncio.sleep(2)

    except ConnectionRefusedError:
        print(red(f"\n  Connection refused — is the backend running on {BACKEND_URL}?"))
        sys.exit(1)
    except Exception as exc:
        print(red(f"\n  Unexpected error: {type(exc).__name__}: {exc}"))
        import traceback
        traceback.print_exc()

    # ── Summary ──────────────────────────────────────────────────
    print()
    print(bold("═" * 64))
    print(bold("  Desktop Task Test Results"))
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
        description="Omni Hub — Desktop Task Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Available test IDs:
          file       — create a text file on the desktop
          open_app   — open Notepad
          video      — find and play a video / open Videos folder
          photos     — list and open Pictures folder
          folder     — open Downloads folder in Explorer
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
    args = parser.parse_args()

    only = [x.strip() for x in args.only.split(",")] if args.only else None
    asyncio.run(run_tests(only, args.backend))


if __name__ == "__main__":
    main()
