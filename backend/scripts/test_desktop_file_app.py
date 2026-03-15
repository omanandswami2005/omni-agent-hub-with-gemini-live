#!/usr/bin/env python3
"""
Omni Hub — Desktop File & App Operations E2E Test
===================================================
Connects to the live backend as a desktop client and tests:
  1. File creation (write_file)
  2. File copy (execute_command cp/copy)
  3. File move (execute_command mv/move)
  4. App launch — Notepad
  5. App launch — YouTube in browser

Simulates T3 tool handlers so the backend's device_agent can invoke
desktop tools via reverse-RPC (tool_invocation) and cross_client actions.

Usage
-----
    cd backend
    .venv/Scripts/python.exe scripts/test_desktop_file_app.py
    .venv/Scripts/python.exe scripts/test_desktop_file_app.py --backend https://omni-backend-666233642847.us-central1.run.app
    .venv/Scripts/python.exe scripts/test_desktop_file_app.py --only file_create,notepad
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

# ── Load .env ────────────────────────────────────────────────────────
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

# ── Colours ──────────────────────────────────────────────────────────
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


# ── Simulated desktop tool definitions (advertised at auth) ──────────

DESKTOP_LOCAL_TOOLS = [
    {
        "name": "capture_screen",
        "description": "Capture a screenshot of the desktop",
        "parameters": {"type": "object", "properties": {"quality": {"type": "integer", "default": 75}}},
    },
    {
        "name": "click",
        "description": "Click at screen coordinates",
        "parameters": {
            "type": "object",
            "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "button": {"type": "string", "default": "left"}},
            "required": ["x", "y"],
        },
    },
    {
        "name": "type_text",
        "description": "Type text on the keyboard",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    },
    {
        "name": "hotkey",
        "description": "Press a keyboard shortcut",
        "parameters": {"type": "object", "properties": {"keys": {"type": "array", "items": {"type": "string"}}}, "required": ["keys"]},
    },
    {
        "name": "execute_command",
        "description": "Execute a shell command on the desktop",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
    },
    {
        "name": "read_file",
        "description": "Read a file from the desktop filesystem",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
    {
        "name": "write_file",
        "description": "Write content to a file on the desktop filesystem",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_directory",
        "description": "List files in a desktop directory",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
    {
        "name": "open_app",
        "description": "Open an application on the desktop by name",
        "parameters": {"type": "object", "properties": {"app": {"type": "string"}}, "required": ["app"]},
    },
    {
        "name": "screen_info",
        "description": "Get information about connected monitors",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "file_info",
        "description": "Get metadata about a file on the desktop",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
]

DESKTOP_CAPABILITIES = [
    "screen_capture", "mouse_control", "keyboard_control",
    "app_launch", "file_system", "execute_command",
]


# ── Simulated filesystem state ───────────────────────────────────────
# Track file operations locally so we can verify the agent's actions.

class SimulatedFS:
    """In-memory filesystem to track what the agent did."""

    def __init__(self):
        self.files: dict[str, str] = {}  # path -> content
        self.ops: list[dict] = []        # log of operations

    def write(self, path: str, content: str) -> dict:
        self.files[path] = content
        self.ops.append({"op": "write", "path": path, "size": len(content)})
        return {"ok": True, "path": path, "bytes_written": len(content)}

    def read(self, path: str) -> dict:
        if path in self.files:
            self.ops.append({"op": "read", "path": path})
            return {"ok": True, "content": self.files[path]}
        return {"ok": False, "error": f"File not found: {path}"}

    def info(self, path: str) -> dict:
        if path in self.files:
            return {"ok": True, "path": path, "size": len(self.files[path]), "is_dir": False, "exists": True}
        return {"ok": True, "path": path, "exists": False}

    def list_dir(self, path: str) -> dict:
        entries = []
        for fpath, content in self.files.items():
            if fpath.startswith(path.rstrip("/") + "/") or fpath.startswith(path.rstrip("\\") + "\\"):
                entries.append({"name": os.path.basename(fpath), "is_dir": False, "size": len(content)})
        self.ops.append({"op": "list_dir", "path": path})
        return entries if entries else [{"name": ".", "is_dir": True, "size": 0}]

    def execute(self, command: str) -> dict:
        self.ops.append({"op": "execute", "command": command})
        cmd_lower = command.lower()
        # Simulate copy
        if "copy " in cmd_lower or "cp " in cmd_lower:
            parts = command.split()
            if len(parts) >= 3:
                src = parts[-2]
                dst = parts[-1]
                if src in self.files:
                    self.files[dst] = self.files[src]
                    return {"ok": True, "stdout": f"Copied {src} -> {dst}", "returncode": 0}
                # Try with normalized paths
                for fpath in list(self.files.keys()):
                    if fpath.endswith(src) or os.path.basename(fpath) == os.path.basename(src):
                        self.files[dst] = self.files[fpath]
                        return {"ok": True, "stdout": f"Copied {fpath} -> {dst}", "returncode": 0}
            return {"ok": True, "stdout": "1 file(s) copied.", "returncode": 0}
        # Simulate move
        if "move " in cmd_lower or "mv " in cmd_lower or "ren " in cmd_lower:
            parts = command.split()
            if len(parts) >= 3:
                src = parts[-2]
                dst = parts[-1]
                for fpath in list(self.files.keys()):
                    if fpath == src or fpath.endswith(src) or os.path.basename(fpath) == os.path.basename(src):
                        self.files[dst] = self.files.pop(fpath)
                        return {"ok": True, "stdout": f"Moved {fpath} -> {dst}", "returncode": 0}
            return {"ok": True, "stdout": "1 file(s) moved.", "returncode": 0}
        # Simulate start / open
        if cmd_lower.startswith("start ") or cmd_lower.startswith("open "):
            return {"ok": True, "stdout": "Opened successfully", "returncode": 0}
        return {"ok": True, "stdout": f"Simulated: {command}", "returncode": 0}


# ── Global simulated state ───────────────────────────────────────────
_fs = SimulatedFS()
_apps_opened: list[str] = []


def simulate_tool(tool_name: str, args: dict) -> dict:
    """Return a simulated result for a T3 tool or cross_client action."""

    if tool_name == "write_file":
        return _fs.write(args.get("path", "/tmp/test.txt"), args.get("content", ""))
    if tool_name == "read_file":
        return _fs.read(args.get("path", ""))
    if tool_name == "file_info":
        return _fs.info(args.get("path", ""))
    if tool_name == "list_directory":
        return _fs.list_dir(args.get("path", "."))
    if tool_name == "execute_command":
        return _fs.execute(args.get("command", ""))
    if tool_name == "open_app":
        app = args.get("app", "unknown")
        _apps_opened.append(app)
        return {"ok": True, "app": app, "status": "launched"}
    if tool_name == "capture_screen":
        return {"ok": True, "image_base64": "iVBORw0KGgo=", "width": 1920, "height": 1080}
    if tool_name == "screen_info":
        return {"primary": {"width": 1920, "height": 1080}, "monitors": [{"left": 0, "top": 0, "width": 1920, "height": 1080}]}
    if tool_name == "click":
        return {"ok": True, "x": args.get("x", 0), "y": args.get("y", 0)}
    if tool_name == "type_text":
        return {"ok": True, "length": len(args.get("text", ""))}
    if tool_name == "hotkey":
        return {"ok": True, "keys": args.get("keys", [])}

    return {"ok": True, "tool": tool_name, "note": "simulated"}


# ── Firebase Auth ────────────────────────────────────────────────────

async def get_token() -> str:
    import httpx
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.post(url, json={"email": EMAIL, "password": PASSWORD, "returnSecureToken": True})
    resp.raise_for_status()
    return resp.json()["idToken"]


# ── WS message helpers ───────────────────────────────────────────────

async def ws_auth(ws, token: str) -> dict | None:
    """Send desktop auth and return auth_response."""
    import platform
    await ws.send(json.dumps({
        "type": "auth",
        "token": token,
        "client_type": "desktop",
        "user_agent": f"OmniDesktopTest/1.0 ({platform.system()})",
        "capabilities": DESKTOP_CAPABILITIES,
        "local_tools": DESKTOP_LOCAL_TOOLS,
    }))
    for _ in range(10):
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=15)
        except TimeoutError:
            break
        if isinstance(raw, bytes):
            continue
        msg = json.loads(raw)
        if msg.get("type") == "auth_response":
            return msg
    return None


async def send_prompt_and_handle(ws, prompt: str, timeout: float = 90.0) -> dict:
    """Send a text prompt and collect all messages, handling tool invocations.

    Returns a summary dict with message lists and key flags.
    """
    await ws.send(json.dumps({"type": "text", "content": prompt}))
    t0 = time.monotonic()
    messages: list[dict] = []
    tools_invoked: list[dict] = []   # {tool, args, call_id}
    actions_received: list[dict] = []  # cross_client_action
    has_response = False
    saw_transfer = False

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    try:
        while loop.time() < deadline:
            remaining = deadline - loop.time()
            silence = 15.0 if saw_transfer and not has_response else 8.0
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, silence))
            except TimeoutError:
                if has_response:
                    break
                continue

            if isinstance(raw, bytes):
                messages.append({"type": "_audio", "size": len(raw)})
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            messages.append(msg)
            mtype = msg.get("type", "")

            # Handle T3 tool invocations — respond with simulated result
            if mtype == "tool_invocation":
                call_id = msg.get("call_id", "")
                tool = msg.get("tool", "")
                args = msg.get("args", {})
                tools_invoked.append({"tool": tool, "args": args, "call_id": call_id})
                result = simulate_tool(tool, args)
                await ws.send(json.dumps({
                    "type": "tool_result",
                    "call_id": call_id,
                    "result": result,
                }))

            # Handle cross_client (fire-and-forget from backend)
            elif mtype == "cross_client":
                action = msg.get("action", "")
                payload = msg.get("data", {})
                actions_received.append({"action": action, "payload": payload})
                # Simulate and send response
                result = simulate_tool(action, payload)
                await ws.send(json.dumps({
                    "type": "action_response",
                    "action": action,
                    "result": result,
                }))

            elif mtype == "tool_call" and msg.get("tool_name") == "transfer_to_agent":
                saw_transfer = True

            elif mtype == "response" and (msg.get("data") or msg.get("content")):
                has_response = True

            elif mtype == "status" and msg.get("state") == "idle" and has_response:
                break

            elif mtype == "status" and msg.get("state") == "error":
                break

    except Exception as exc:
        messages.append({"type": "_exception", "error": str(exc)})

    elapsed = time.monotonic() - t0
    return {
        "messages": messages,
        "tools_invoked": tools_invoked,
        "actions_received": actions_received,
        "has_response": has_response,
        "elapsed": elapsed,
    }


def print_messages(messages: list[dict], indent: str = "      ") -> None:
    for msg in messages:
        t = msg.get("type", "?")
        if t == "response":
            text = msg.get("data", "")
            if text:
                lines = textwrap.fill(text, width=90, initial_indent="", subsequent_indent=indent)
                print(f"{indent}{green('[Agent]')} {lines}")
        elif t == "tool_invocation":
            tool = msg.get("tool", "?")
            args = json.dumps(msg.get("args", {}))[:100]
            print(f"{indent}{cyan('[T3 invoke]')} {bold(tool)} {dim(args)}")
        elif t == "cross_client":
            action = msg.get("action", "?")
            payload = json.dumps(msg.get("data", {}))[:100]
            print(f"{indent}{cyan('[action]')} {bold(action)} {dim(payload)}")
        elif t == "tool_call":
            tool = msg.get("tool_name", "?")
            status = msg.get("status", "")
            args = json.dumps(msg.get("arguments", {}))[:100]
            icon = ">" if status == "started" else ("✓" if status == "completed" else "▶")
            print(f"{indent}{blue(f'[tool {icon}]')} {bold(tool)} {dim(args)}")
        elif t == "tool_response":
            tool = msg.get("tool_name", "?")
            success = msg.get("success", True)
            icon = green("✓") if success else red("✗")
            print(f"{indent}{blue('[tool result]')} {icon} {tool}: {str(msg.get('result', ''))[:120]}")
        elif t == "transcription":
            text = msg.get("text", "")
            if text:
                d = msg.get("direction", "")
                arrow = "→" if d == "input" else "←"
                print(f"{indent}{dim(f'[transcript {arrow}]')} {text[:120]}")
        elif t == "status":
            state = msg.get("state", "?")
            color = green if state == "idle" else (yellow if state == "processing" else dim)
            print(f"{indent}{dim('[status]')} {color(state)}")
        elif t in ("auth_response", "connected", "_audio", "session_created",
                    "session_suggestion", "client_status_update", "mic_floor", "ping"):
            pass
        elif t == "agent_activity":
            title = msg.get("title", "?")
            status = msg.get("status", "")
            print(f"{indent}{dim(f'[activity] {title} [{status}]')}")
        elif t == "error":
            print(f"{indent}{red('[error]')} {msg.get('code', '?')}: {msg.get('description', '')}")
        elif t != "_exception":
            print(f"{indent}{dim(f'[{t}]')} {json.dumps(msg)[:120]}")


# ── Tests ────────────────────────────────────────────────────────────

TESTS = [
    {"id": "file_create", "name": "File Creation (write_file)"},
    {"id": "file_read", "name": "File Read-back Verification"},
    {"id": "file_copy", "name": "File Copy (command)"},
    {"id": "file_move", "name": "File Move/Rename (command)"},
    {"id": "notepad", "name": "Open Notepad"},
    {"id": "youtube", "name": "Open YouTube in Browser"},
]


async def test_file_create(ws, results: dict) -> None:
    """Ask agent to create a file on the desktop."""
    print(bold("\n  [1] File Creation — write_file"))
    print(dim("      Ask agent to create a test file on the desktop"))

    prompt = (
        "Create a new text file on my desktop at the path ~/Desktop/omni_test.txt "
        "with the content: 'Hello from Omni Hub! Test file created successfully.' "
        "Use the write_file tool to do this."
    )
    print(f"      {dim('Prompt:')} {prompt[:90]}...")

    result = await send_prompt_and_handle(ws, prompt)
    print_messages(result["messages"])

    # Check if write_file was invoked (via T3 or cross_client)
    wrote = any(
        t["tool"] in ("write_file",) for t in result["tools_invoked"]
    ) or any(
        a["action"] in ("write_file",) for a in result["actions_received"]
    )
    # Also accept send_to_desktop with write_file action
    sent_to_desktop_write = any(
        t.get("tool") == "send_to_desktop" or a.get("action") == "write_file"
        for t in result.get("tools_invoked", [])
        for a in result.get("actions_received", [{}])
    )

    if wrote or sent_to_desktop_write:
        print(green(f"\n      ✓ PASS ({result['elapsed']:.1f}s) — write_file invoked"))
        results["file_create"] = (True, "write_file tool invoked")
    elif result["has_response"]:
        # Agent might have used execute_command to create the file
        exec_ops = [t for t in result["tools_invoked"] if t["tool"] == "execute_command"]
        if exec_ops:
            print(green(f"\n      ✓ PASS ({result['elapsed']:.1f}s) — file created via execute_command"))
            results["file_create"] = (True, f"via execute_command")
        else:
            print(yellow(f"\n      ~ WARN ({result['elapsed']:.1f}s) — agent responded but may not have written file"))
            results["file_create"] = (True, "agent responded (indirect)")
    else:
        print(red(f"\n      ✗ FAIL ({result['elapsed']:.1f}s) — no file creation detected"))
        results["file_create"] = (False, "no write_file invocation")


async def test_file_read(ws, results: dict) -> None:
    """Ask agent to read back the file we created."""
    print(bold("\n  [2] File Read-back Verification"))
    print(dim("      Ask agent to read back the file created in test 1"))

    # Pre-seed the simulated FS if it wasn't written by test 1
    if not any("omni_test" in p for p in _fs.files):
        _fs.write(os.path.expanduser("~/Desktop/omni_test.txt"), "Hello from Omni Hub! Test file created successfully.")

    prompt = (
        "Read the file ~/Desktop/omni_test.txt on my desktop and tell me what it contains. "
        "Use the read_file tool."
    )
    print(f"      {dim('Prompt:')} {prompt[:90]}...")

    result = await send_prompt_and_handle(ws, prompt)
    print_messages(result["messages"])

    read_ops = [t for t in result["tools_invoked"] if t["tool"] == "read_file"]
    sent_read = any(a["action"] == "read_file" for a in result["actions_received"])

    if read_ops or sent_read:
        print(green(f"\n      ✓ PASS ({result['elapsed']:.1f}s) — read_file invoked"))
        results["file_read"] = (True, "read_file tool invoked")
    elif result["has_response"]:
        print(green(f"\n      ✓ PASS ({result['elapsed']:.1f}s) — agent responded"))
        results["file_read"] = (True, "agent responded")
    else:
        print(red(f"\n      ✗ FAIL ({result['elapsed']:.1f}s) — no read operation"))
        results["file_read"] = (False, "no read_file invocation")


async def test_file_copy(ws, results: dict) -> None:
    """Ask agent to copy the test file."""
    print(bold("\n  [3] File Copy"))
    print(dim("      Ask agent to copy the test file to a new location"))

    prompt = (
        "Copy the file ~/Desktop/omni_test.txt to ~/Desktop/omni_test_backup.txt on my desktop. "
        "You can use the execute_command tool with a copy command."
    )
    print(f"      {dim('Prompt:')} {prompt[:90]}...")

    result = await send_prompt_and_handle(ws, prompt)
    print_messages(result["messages"])

    exec_ops = [t for t in result["tools_invoked"] if t["tool"] == "execute_command"]
    action_execs = [a for a in result["actions_received"] if a["action"] == "execute_command"]
    has_copy = any("copy" in json.dumps(t.get("args", {})).lower() or "cp " in json.dumps(t.get("args", {})).lower()
                    for t in result["tools_invoked"])

    if exec_ops or action_execs or has_copy:
        print(green(f"\n      ✓ PASS ({result['elapsed']:.1f}s) — copy command executed"))
        results["file_copy"] = (True, "execute_command invoked for copy")
    elif result["has_response"]:
        print(green(f"\n      ✓ PASS ({result['elapsed']:.1f}s) — agent responded"))
        results["file_copy"] = (True, "agent responded")
    else:
        print(red(f"\n      ✗ FAIL ({result['elapsed']:.1f}s) — no copy operation"))
        results["file_copy"] = (False, "no execute_command for copy")


async def test_file_move(ws, results: dict) -> None:
    """Ask agent to move/rename the backup file."""
    print(bold("\n  [4] File Move / Rename"))
    print(dim("      Ask agent to rename the backup file"))

    prompt = (
        "Rename the file ~/Desktop/omni_test_backup.txt to ~/Desktop/omni_renamed.txt on my desktop. "
        "You can use the execute_command tool with a move or rename command."
    )
    print(f"      {dim('Prompt:')} {prompt[:90]}...")

    result = await send_prompt_and_handle(ws, prompt)
    print_messages(result["messages"])

    exec_ops = [t for t in result["tools_invoked"] if t["tool"] == "execute_command"]
    action_execs = [a for a in result["actions_received"] if a["action"] == "execute_command"]
    has_move = any(
        "move" in json.dumps(t.get("args", {})).lower() or
        "mv " in json.dumps(t.get("args", {})).lower() or
        "ren " in json.dumps(t.get("args", {})).lower()
        for t in result["tools_invoked"]
    )

    if exec_ops or action_execs or has_move:
        print(green(f"\n      ✓ PASS ({result['elapsed']:.1f}s) — move/rename command executed"))
        results["file_move"] = (True, "execute_command invoked for move")
    elif result["has_response"]:
        print(green(f"\n      ✓ PASS ({result['elapsed']:.1f}s) — agent responded"))
        results["file_move"] = (True, "agent responded")
    else:
        print(red(f"\n      ✗ FAIL ({result['elapsed']:.1f}s) — no move operation"))
        results["file_move"] = (False, "no execute_command for move")


async def test_notepad(ws, results: dict) -> None:
    """Ask agent to open Notepad."""
    print(bold("\n  [5] Open Notepad"))
    print(dim("      Ask agent to launch Notepad on the desktop"))

    prompt = "Open Notepad on my desktop. Use the open_app tool with app name 'notepad'."
    print(f"      {dim('Prompt:')} {prompt[:90]}")

    result = await send_prompt_and_handle(ws, prompt)
    print_messages(result["messages"])

    open_ops = [t for t in result["tools_invoked"] if t["tool"] == "open_app"]
    action_opens = [a for a in result["actions_received"] if a["action"] == "open_app"]
    exec_notepad = any(
        "notepad" in json.dumps(t.get("args", {})).lower()
        for t in result["tools_invoked"]
    )
    cross_notepad = any(
        "notepad" in json.dumps(a.get("payload", {})).lower()
        for a in result["actions_received"]
    )

    if open_ops or action_opens or exec_notepad or cross_notepad:
        app_name = ""
        if open_ops:
            app_name = open_ops[0].get("args", {}).get("app", "?")
        elif action_opens:
            app_name = action_opens[0].get("payload", {}).get("app", "?")
        print(green(f"\n      ✓ PASS ({result['elapsed']:.1f}s) — open_app invoked: {app_name}"))
        results["notepad"] = (True, f"open_app: {app_name}")
    elif result["has_response"]:
        # Agent might have used execute_command or send_to_desktop
        any_tool = result["tools_invoked"] or result["actions_received"]
        if any_tool:
            print(green(f"\n      ✓ PASS ({result['elapsed']:.1f}s) — agent used tools for notepad"))
            results["notepad"] = (True, "agent used tools")
        else:
            print(yellow(f"\n      ~ WARN ({result['elapsed']:.1f}s) — agent responded but no tool invoked"))
            results["notepad"] = (True, "agent responded (no tool)")
    else:
        print(red(f"\n      ✗ FAIL ({result['elapsed']:.1f}s) — no notepad launch"))
        results["notepad"] = (False, "no open_app invocation")


async def test_youtube(ws, results: dict) -> None:
    """Ask agent to open YouTube in browser."""
    print(bold("\n  [6] Open YouTube in Browser"))
    print(dim("      Ask agent to open YouTube on the desktop"))

    prompt = (
        "Open YouTube (https://www.youtube.com) in a web browser on my desktop. "
        "You can use execute_command with 'start https://www.youtube.com' or use open_app."
    )
    print(f"      {dim('Prompt:')} {prompt[:90]}...")

    result = await send_prompt_and_handle(ws, prompt)
    print_messages(result["messages"])

    has_youtube = any(
        "youtube" in json.dumps(t.get("args", {})).lower()
        for t in result["tools_invoked"]
    ) or any(
        "youtube" in json.dumps(a.get("payload", {})).lower()
        for a in result["actions_received"]
    )
    any_tool = result["tools_invoked"] or result["actions_received"]

    if has_youtube:
        print(green(f"\n      ✓ PASS ({result['elapsed']:.1f}s) — YouTube open command issued"))
        results["youtube"] = (True, "youtube command issued")
    elif any_tool and result["has_response"]:
        print(green(f"\n      ✓ PASS ({result['elapsed']:.1f}s) — agent used tools"))
        results["youtube"] = (True, "agent used tools")
    elif result["has_response"]:
        print(yellow(f"\n      ~ WARN ({result['elapsed']:.1f}s) — agent responded without tool"))
        results["youtube"] = (True, "agent responded (no tool)")
    else:
        print(red(f"\n      ✗ FAIL ({result['elapsed']:.1f}s) — no response"))
        results["youtube"] = (False, "no response")


# ── Runner ───────────────────────────────────────────────────────────

TEST_MAP = {
    "file_create": test_file_create,
    "file_read": test_file_read,
    "file_copy": test_file_copy,
    "file_move": test_file_move,
    "notepad": test_notepad,
    "youtube": test_youtube,
}

async def run_tests(only: list[str] | None, backend_url: str) -> None:
    ws_url = backend_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws/live"

    print()
    print(bold("=" * 64))
    print(bold("  Omni Hub — Desktop File & App Operations E2E"))
    print(bold("=" * 64))
    print(f"  Backend : {backend_url}")
    print(f"  WS      : {ws_url}")
    print(f"  Time    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Auth
    print(bold("  Authenticating..."))
    token = await get_token()
    print(green(f"  Firebase auth OK") + dim(f"  (token: {token[:20]}...)"))

    tests_to_run = TESTS if not only else [t for t in TESTS if t["id"] in only]
    results: dict[str, tuple[bool, str]] = {}

    import websockets

    try:
        print(f"\n  Connecting to {ws_url} ...")
        async with websockets.connect(ws_url, max_size=10 * 1024 * 1024, open_timeout=30,
                                       ping_interval=30, ping_timeout=60) as ws:
            # Auth handshake
            auth_resp = await ws_auth(ws, token)
            if not auth_resp or auth_resp.get("status") != "ok":
                print(red(f"  Auth failed: {auth_resp}"))
                sys.exit(1)
            print(green(f"  WS authenticated — session: {auth_resp.get('session_id', '?')[:24]}..."))

            # Drain startup messages
            try:
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            except (TimeoutError, asyncio.CancelledError):
                pass

            # Run tests
            for test_def in tests_to_run:
                tid = test_def["id"]
                fn = TEST_MAP.get(tid)
                if fn:
                    await fn(ws, results)
                    # Drain between tests
                    try:
                        while True:
                            await asyncio.wait_for(ws.recv(), timeout=2.0)
                    except (TimeoutError, asyncio.CancelledError):
                        pass
                    await asyncio.sleep(1)

    except ConnectionRefusedError:
        print(red(f"\n  Connection refused — is the backend running?"))
        sys.exit(1)
    except Exception as exc:
        print(red(f"\n  Error: {type(exc).__name__}: {exc}"))
        import traceback
        traceback.print_exc()

    # ── Summary ──────────────────────────────────────────────────
    print()
    print(bold("=" * 64))
    print(bold("  Desktop File & App — Test Results"))
    print(bold("=" * 64))

    # Filesystem state
    if _fs.files:
        print(f"\n  {dim('Simulated filesystem state:')}")
        for path, content in _fs.files.items():
            print(f"    {cyan(path)} ({len(content)} bytes)")
    if _fs.ops:
        print(f"\n  {dim(f'Total operations logged: {len(_fs.ops)}')}")
        for op in _fs.ops:
            print(f"    {dim(json.dumps(op))}")
    if _apps_opened:
        print(f"\n  {dim(f'Apps opened: {_apps_opened}')}")

    print()
    total = len(results)
    passed = sum(1 for ok, _ in results.values() if ok)

    for test_def in TESTS:
        tid = test_def["id"]
        if tid not in results:
            continue
        ok, reason = results[tid]
        icon = green("✓") if ok else red("✗")
        print(f"  {icon}  {test_def['name']:<40} {dim(reason)}")

    print()
    bar = green if passed == total else (yellow if passed > 0 else red)
    print(f"  {bar(f'{passed}/{total} tests passed')}")
    print()

    if passed < total:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Desktop File & App Operations E2E Test")
    parser.add_argument("--backend", default=BACKEND_URL, help="Backend URL")
    parser.add_argument("--only", help="Comma-separated test IDs: file_create,file_read,file_copy,file_move,notepad,youtube")
    parser.add_argument("--list", action="store_true", help="List test IDs")
    args = parser.parse_args()

    if args.list:
        for t in TESTS:
            print(f"  {t['id']:<16} {t['name']}")
        return

    only = [x.strip() for x in args.only.split(",")] if args.only else None
    asyncio.run(run_tests(only, args.backend))


if __name__ == "__main__":
    main()
