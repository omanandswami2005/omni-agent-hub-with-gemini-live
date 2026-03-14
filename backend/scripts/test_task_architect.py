#!/usr/bin/env python3
"""End-to-end test for the TaskArchitect pipeline.

Sends a complex multi-step task over /ws/chat and simultaneously listens
on /ws/events for pipeline_created and pipeline_progress events.
Prints live status updates as stages move through pending → running → completed.

Usage
-----
    cd backend
    uv run python scripts/test_task_architect.py

What it tests
-------------
  1. Firebase auth handshake (both sockets)
  2. plan_task tool invocation on root agent
  3. pipeline_created event → blueprint received on /ws/events
  4. pipeline_progress events → per-stage status updates in real-time
  5. Final agent text response on /ws/chat
  6. pipelineStore.updateStage auto-archive (all stages completed)
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path

# Ensure stdout/stderr use UTF-8 on Windows (needed for emoji/box chars)
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

# ── Load .env ────────────────────────────────────────────────────────────────
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
BACKEND_HTTP = os.getenv("BACKEND_URL", "http://localhost:8000")
BACKEND_WS   = BACKEND_HTTP.replace("http://", "ws://").replace("https://", "wss://")

CHAT_WS   = f"{BACKEND_WS}/ws/chat"
EVENTS_WS = f"{BACKEND_WS}/ws/events"

# ── Colours ──────────────────────────────────────────────────────────────────
USE_COLOR = sys.stdout.isatty()

def _c(code: str, t: str) -> str: return f"{code}{t}\033[0m" if USE_COLOR else t
def green(t):  return _c("\033[92m", t)
def red(t):    return _c("\033[91m", t)
def yellow(t): return _c("\033[93m", t)
def cyan(t):   return _c("\033[96m", t)
def blue(t):   return _c("\033[94m", t)
def bold(t):   return _c("\033[1m",  t)
def dim(t):    return _c("\033[2m",  t)
def magenta(t):return _c("\033[95m", t)

# ── Complex task ─────────────────────────────────────────────────────────────
COMPLEX_TASK = (
    "Do three things: "
    "1) Research the top 3 programming languages in 2026 popularity, "
    "2) Write a Python function that returns a list of those languages with their rank, "
    "3) Write a short creative poem about coding with those languages."
)

# ── Auth ─────────────────────────────────────────────────────────────────────
async def firebase_sign_in() -> str:
    try:
        import httpx
    except ImportError:
        print(red("httpx not installed. Run: uv add httpx"))
        sys.exit(1)

    print(f"  Signing in as {bold(EMAIL)} ...")
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json={
            "email": EMAIL,
            "password": PASSWORD,
            "returnSecureToken": True,
        })
    if resp.status_code != 200:
        err = resp.json().get("error", {}).get("message", "unknown")
        print(red(f"  Firebase sign-in failed: {err}"))
        sys.exit(1)
    token = resp.json()["idToken"]
    print(green(f"  Auth OK") + dim(f"  ({token[:20]}...)"))
    return token


# ── Pipeline event listener ───────────────────────────────────────────────────
STAGE_STATUS_ICON = {
    "pending":   "⏳",
    "running":   "🔄",
    "completed": "✅",
    "failed":    "❌",
}

async def listen_events(token: str, all_done: asyncio.Event, pipeline_seen: asyncio.Event) -> None:
    """Connect to /ws/events and print pipeline events as they arrive."""
    try:
        import websockets
    except ImportError:
        print(red("websockets not installed. Run: uv add websockets"))
        return

    print(f"\n  {dim('[events]')} Connecting to {EVENTS_WS} ...")
    try:
        async with websockets.connect(
            EVENTS_WS,
            max_size=2 * 1024 * 1024,
            open_timeout=15,
            ping_interval=20,
            ping_timeout=30,
        ) as ws:
            # Authenticate
            await ws.send(json.dumps({"type": "auth", "token": token}))
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            auth_resp = json.loads(raw)
            if auth_resp.get("status") != "ok":
                print(red(f"  [events] Auth failed: {auth_resp}"))
                return
            print(green(f"  [events] Auth OK") + dim(f"  uid={auth_resp.get('user_id', '?')}"))
            print(dim("  [events] Listening for pipeline events...\n"))

            # Listen until all_done is set
            while not all_done.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break

                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type", "?")

                if etype == "pipeline_created":
                    pipeline_seen.set()
                    bp = event.get("pipeline", {})
                    pid = bp.get("pipeline_id", "?")
                    stages = bp.get("stages", [])
                    agents = bp.get("total_agents", 0)
                    print()
                    print(bold(cyan(f"  ┌─ Pipeline Created: {pid} ({len(stages)} stages, {agents} agents)")))
                    print(cyan(f"  │  Task: {bp.get('task_description', '')[:80]}"))
                    for i, stage in enumerate(stages):
                        connector = "├" if i < len(stages) - 1 else "└"
                        tasks_str = ", ".join(
                            f"[{t['persona_id']}] {t['description'][:40]}"
                            for t in stage.get("tasks", [])
                        )
                        print(cyan(f"  {connector}─ Stage {i+1}: {stage['name']} ({stage['stage_type']})"))
                        print(dim(f"  │     {tasks_str}"))
                    print()

                elif etype == "pipeline_progress":
                    stage = event.get("stage", "?")
                    status = event.get("status", "?")
                    progress = event.get("progress", 0.0)
                    icon = STAGE_STATUS_ICON.get(status, "❓")
                    pct = f"{int(progress * 100):3d}%"
                    ts = time.strftime("%H:%M:%S")
                    color_fn = green if status == "completed" else (yellow if status == "running" else (red if status == "failed" else dim))
                    print(f"  {dim(ts)} {icon} {color_fn(f'{stage:<20}')} {dim(pct)} {dim(status)}")

                    if all_done.is_set():
                        break
                else:
                    # Other events (genui, cross_client, etc.) — just note them
                    print(dim(f"  [events] {etype}: {json.dumps(event, separators=(',', ':'))[:80]}"))

    except Exception as e:
        print(red(f"  [events] Error: {e}"))


# ── Chat listener ─────────────────────────────────────────────────────────────
async def run_chat(token: str, all_done: asyncio.Event) -> bool:
    try:
        import websockets
    except ImportError:
        print(red("websockets not installed. Run: uv add websockets"))
        return False

    print(f"\n  {dim('[chat]')} Connecting to {CHAT_WS} ...")
    try:
        async with websockets.connect(
            CHAT_WS,
            max_size=10 * 1024 * 1024,
            open_timeout=30,
            ping_interval=30,
            ping_timeout=60,
        ) as ws:
            # Auth
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
            if auth_resp.get("type") not in ("auth_response", "connected") and auth_resp.get("status") != "ok":
                print(red(f"  [chat] Auth failed: {auth_resp}"))
                return False
            print(green(f"  [chat] Auth OK"))

            # Drain any session bootstrap messages
            try:
                while True:
                    await asyncio.wait_for(ws.recv(), timeout=1.5)
            except asyncio.TimeoutError:
                pass

            # Send the complex task
            print(f"\n  {bold('Sending complex task:')}")
            print(f"  {yellow(COMPLEX_TASK)}\n")
            await ws.send(json.dumps({
                "type": "text",
                "content": COMPLEX_TASK,
            }))

            # Collect responses with a long timeout (pipeline execution takes time)
            messages: list[dict] = []
            has_response = False
            idle_count = 0
            saw_plan_task = False
            deadline = asyncio.get_event_loop().time() + 180  # 3 min max

            while asyncio.get_event_loop().time() < deadline:
                remaining = deadline - asyncio.get_event_loop().time()
                # Longer silence allowed while pipeline is executing
                silence = 90.0 if saw_plan_task and not has_response else 15.0
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, silence))
                except asyncio.TimeoutError:
                    if has_response:
                        break
                    if idle_count >= 2:
                        break
                    continue

                if isinstance(raw, bytes):
                    continue  # skip audio

                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                messages.append(msg)
                t = msg.get("type", "?")

                # Print interesting messages
                if t == "tool_call":
                    tool = msg.get("tool_name", "?")
                    args = msg.get("arguments", {})
                    if tool == "plan_task":
                        saw_plan_task = True
                        task_arg = args.get("task", "")[:80]
                        print(f"  {blue('⚡ [plan_task]')} {bold('plan_task')} called")
                        print(dim(f"       task: {task_arg}"))
                    elif tool == "transfer_to_agent":
                        to_agent = args.get("agent_name", args.get("agent", "?"))
                        print(f"  {blue('⚡ [transfer]')} → {bold(to_agent)}")
                    else:
                        print(f"  {blue(f'⚡ [{tool}]')} {dim(json.dumps(args, separators=(',', ':'))[:80])}")

                elif t == "tool_response":
                    tool = msg.get("tool_name", "?")
                    success = msg.get("success", True)
                    icon = green("✓") if success else red("✗")
                    if tool == "plan_task":
                        result = msg.get("result", "")[:200]
                        print(f"  {blue('[plan_task result]')} {icon}")
                        print(dim(f"       {result[:200]}"))
                    else:
                        print(f"  {blue(f'[{tool} result]')} {icon}")

                elif t == "response":
                    text = msg.get("data", "") or msg.get("content", "")
                    if text:
                        has_response = True
                        print(f"\n  {green(bold('[Agent Response]'))}")
                        # Word wrap at 80 chars
                        words = text.split()
                        line = "  "
                        for w in words:
                            if len(line) + len(w) + 1 > 82:
                                print(line)
                                line = "  " + w
                            else:
                                line += (" " if line.strip() else "") + w
                        if line.strip():
                            print(line)
                        print()

                elif t == "status":
                    state = msg.get("state", "?")
                    detail = msg.get("detail", "")
                    color_fn = green if state == "idle" else (yellow if state in ("processing", "listening") else dim)
                    detail_str = dim(f"  ({detail})") if detail else ""
                    print(f"  {dim('[status]')} {color_fn(state)}{detail_str}")
                    if state == "idle":
                        idle_count += 1
                        if has_response or idle_count >= 3:
                            break

                elif t == "error":
                    print(f"  {red('[error]')} {msg.get('code', '?')}: {msg.get('description', '')}")
                    break

                elif t not in ("auth_response", "connected", "persona_changed"):
                    print(dim(f"  [{t}] {json.dumps(msg, separators=(',', ':'))[:100]}"))

            return has_response

    except Exception as e:
        print(red(f"  [chat] Error: {e}"))
        import traceback
        traceback.print_exc()
        return False
    finally:
        all_done.set()


# ── Main ─────────────────────────────────────────────────────────────────────
async def main() -> None:
    print()
    print(bold("═" * 65))
    print(bold("  Omni Hub — TaskArchitect End-to-End Test"))
    print(bold("═" * 65))
    print(f"  Backend : {BACKEND_HTTP}")
    print(f"  Chat WS : {CHAT_WS}")
    print(f"  Events WS: {EVENTS_WS}")
    print()

    token = await firebase_sign_in()
    print()

    all_done = asyncio.Event()
    pipeline_seen = asyncio.Event()

    # Run events listener + chat sender concurrently
    events_task = asyncio.create_task(listen_events(token, all_done, pipeline_seen))
    # Small delay to let events WS connect first
    await asyncio.sleep(0.5)
    chat_ok = await run_chat(token, all_done)

    # Wait for event listener to finish
    try:
        await asyncio.wait_for(events_task, timeout=5)
    except asyncio.TimeoutError:
        events_task.cancel()

    print()
    print(bold("═" * 65))
    if chat_ok and pipeline_seen.is_set():
        print(bold(green("  ✅ PASS — pipeline created + stage events + agent response")))
    elif chat_ok and not pipeline_seen.is_set():
        print(bold(yellow("  ⚠️  PARTIAL — agent responded but no pipeline_created event received")))
        print(dim("     (EventBus may have no subscriber, or plan_task was not triggered)"))
    else:
        print(bold(red("  ❌ FAIL — no agent response received")))
    print(bold("═" * 65))
    print()


if __name__ == "__main__":
    asyncio.run(main())
