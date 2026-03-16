#!/usr/bin/env python3
"""Omni Hub CLI Client — full-featured agent REPL in your terminal.

Connects to the backend via WebSocket, authenticates, and provides
a REPL for conversing with the same agent that powers the web dashboard.

Features:
  - Text chat via /ws/chat with full message handling
  - T3 reverse-RPC: agent can run tools on YOUR machine (read_file, run_command)
  - Slash commands: /persona, /tools, /clients, /mcp, /cancel, /help
  - Auto-reconnect with exponential backoff
  - Rich terminal output with colors

Usage:
    python cli/omni_cli.py --token <firebase-jwt>
    python cli/omni_cli.py --token-file ~/.omni_token
    python cli/omni_cli.py --server ws://localhost:8000 --token <jwt>
    python cli/omni_cli.py --token <jwt> --no-tools   # disable local T3 tools
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    import websockets
except ImportError:
    print("Install websockets: pip install websockets")
    sys.exit(1)


# ─── Terminal colors (ANSI) ──────────────────────────────────────────

class C:
    """ANSI color codes — degrades gracefully on dumb terminals."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    CYAN = "\033[36m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    MAGENTA = "\033[35m"
    BLUE = "\033[34m"


# ─── T3 Local Tool Definitions ──────────────────────────────────────

CLI_LOCAL_TOOLS = [
    {
        "name": "read_file",
        "description": "Read a file from the user's filesystem",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file on the user's filesystem",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write to"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_directory",
        "description": "List files in a directory on the user's machine",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path (default: current dir)"},
            },
            "required": [],
        },
    },
    {
        "name": "run_command",
        "description": "Execute a shell command on the user's machine and return output",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
            },
            "required": ["command"],
        },
    },
]

CLI_CAPABILITIES = ["read_file", "write_file", "list_directory", "run_command"]


# ─── T3 Tool Execution ──────────────────────────────────────────────

def _execute_local_tool(tool_name: str, args: dict) -> dict:
    """Execute a T3 tool locally and return the result dict."""
    if tool_name == "read_file":
        path = args.get("path", "")
        try:
            p = Path(path).expanduser().resolve()
            content = p.read_text(encoding="utf-8", errors="replace")
            return {"status": "ok", "content": content[:50000]}  # Cap at 50KB
        except FileNotFoundError:
            return {"status": "error", "message": f"File not found: {path}"}
        except PermissionError:
            return {"status": "error", "message": f"Permission denied: {path}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif tool_name == "write_file":
        path = args.get("path", "")
        content = args.get("content", "")
        try:
            p = Path(path).expanduser().resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return {"status": "ok", "bytes_written": len(content)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif tool_name == "list_directory":
        path = args.get("path", ".")
        try:
            p = Path(path).expanduser().resolve()
            entries = []
            for child in sorted(p.iterdir()):
                entries.append({
                    "name": child.name,
                    "type": "dir" if child.is_dir() else "file",
                    "size": child.stat().st_size if child.is_file() else 0,
                })
            return {"status": "ok", "path": str(p), "entries": entries[:200]}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif tool_name == "run_command":
        command = args.get("command", "")
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=Path.cwd(),
            )
            return {
                "status": "ok",
                "stdout": result.stdout[:20000],
                "stderr": result.stderr[:5000],
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "Command timed out (30s limit)"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    return {"status": "error", "message": f"Unknown tool: {tool_name}"}


# ─── Slash Commands ──────────────────────────────────────────────────

HELP_TEXT = f"""{C.BOLD}Slash Commands:{C.RESET}
  {C.CYAN}/help{C.RESET}              Show this help message
  {C.CYAN}/persona <id>{C.RESET}      Switch to a persona (assistant, coder, researcher, analyst, creative)
  {C.CYAN}/tools{C.RESET}             List available backend tools
  {C.CYAN}/clients{C.RESET}           Show other connected clients
  {C.CYAN}/mcp <id> on|off{C.RESET}   Toggle an MCP plugin
  {C.CYAN}/cancel{C.RESET}            Cancel current processing
  {C.CYAN}/quit{C.RESET}              Exit the CLI

{C.BOLD}Keyboard:{C.RESET}
  Ctrl+C               Exit
  Enter                Send message
"""


async def _handle_slash_command(ws, cmd: str, session_state: dict) -> bool:
    """Handle a slash command. Returns True if handled, False otherwise."""
    parts = cmd.strip().split(maxsplit=2)
    command = parts[0].lower()

    if command == "/help":
        print(HELP_TEXT)
        return True

    elif command == "/quit":
        return False  # Signal to exit

    elif command == "/persona":
        if len(parts) < 2:
            print(f"  {C.YELLOW}Usage: /persona <id>{C.RESET}")
            return True
        persona_id = parts[1]
        await ws.send(json.dumps({"type": "persona_switch", "persona_id": persona_id}))
        print(f"  {C.MAGENTA}Switching to persona: {persona_id}{C.RESET}")
        return True

    elif command == "/tools":
        tools = session_state.get("tools", [])
        if tools:
            print(f"  {C.BOLD}Available tools ({len(tools)}):{C.RESET}")
            for t in tools:
                print(f"    {C.CYAN}{t}{C.RESET}")
        else:
            print(f"  {C.DIM}No tools available{C.RESET}")
        return True

    elif command == "/clients":
        clients = session_state.get("other_clients", [])
        if clients:
            print(f"  {C.BOLD}Other clients online:{C.RESET} {', '.join(clients)}")
        else:
            print(f"  {C.DIM}No other clients online{C.RESET}")
        return True

    elif command == "/mcp":
        if len(parts) < 3:
            print(f"  {C.YELLOW}Usage: /mcp <plugin_id> on|off{C.RESET}")
            return True
        mcp_id = parts[1]
        enabled = parts[2].lower() in ("on", "true", "1", "enable")
        await ws.send(json.dumps({
            "type": "mcp_toggle",
            "mcp_id": mcp_id,
            "enabled": enabled,
        }))
        state = "enabled" if enabled else "disabled"
        print(f"  {C.MAGENTA}MCP plugin {mcp_id}: {state}{C.RESET}")
        return True

    elif command == "/cancel":
        await ws.send(json.dumps({
            "type": "control",
            "action": "cancel",
        }))
        print(f"  {C.YELLOW}Cancel requested{C.RESET}")
        return True

    else:
        print(f"  {C.RED}Unknown command: {command}{C.RESET}  (try /help)")
        return True


# ─── Main Client ─────────────────────────────────────────────────────

async def run_client(
    server: str,
    token: str,
    enable_tools: bool = True,
    extra_capabilities: list[str] | None = None,
) -> None:
    """Connect, authenticate, and run the REPL loop."""
    uri = f"{server}/ws/chat"
    session_state: dict = {"tools": [], "other_clients": []}
    active_tool_tasks: dict[str, asyncio.Task] = {}

    print(f"\n  {C.BOLD}Omni Hub CLI{C.RESET} — connecting to {C.CYAN}{uri}{C.RESET}")
    print(f"  Type a message and press Enter. {C.DIM}/help for commands, Ctrl+C to quit.{C.RESET}\n")

    capabilities = list(CLI_CAPABILITIES) if enable_tools else []
    if extra_capabilities:
        capabilities.extend(extra_capabilities)
    local_tools = list(CLI_LOCAL_TOOLS) if enable_tools else []

    async with websockets.connect(uri, max_size=10 * 1024 * 1024) as ws:
        # Phase 1 — Auth handshake
        auth_msg = {
            "type": "auth",
            "token": token,
            "client_type": "cli",
            "capabilities": capabilities,
            "local_tools": local_tools,
        }
        await ws.send(json.dumps(auth_msg))

        # Wait for auth_response
        raw = await ws.recv()
        resp = json.loads(raw)
        if resp.get("type") == "auth_response":
            if resp.get("status") != "ok":
                print(f"  {C.RED}Auth failed: {resp.get('error', 'unknown')}{C.RESET}")
                return
            user_id = resp.get("user_id", "?")
            tools = resp.get("available_tools", [])
            others = resp.get("other_clients_online", [])
            session_state["tools"] = tools
            session_state["other_clients"] = others

            print(f"  {C.GREEN}Authenticated as {user_id}{C.RESET}")
            if tools:
                tool_summary = ', '.join(tools[:8])
                more = f"... +{len(tools) - 8}" if len(tools) > 8 else ""
                print(f"  {C.DIM}Tools: {tool_summary}{more}{C.RESET}")
            if others:
                print(f"  {C.DIM}Other clients online: {', '.join(others)}{C.RESET}")
            if enable_tools:
                print(f"  {C.DIM}T3 tools active: {', '.join(CLI_CAPABILITIES)}{C.RESET}")
            print()

        # Phase 2 — REPL loop
        async def reader():
            """Read server messages and print them."""
            try:
                async for raw_msg in ws:
                    # Skip binary frames (audio — not relevant for text-only CLI)
                    if isinstance(raw_msg, bytes):
                        continue
                    try:
                        msg = json.loads(raw_msg)
                    except json.JSONDecodeError:
                        continue
                    msg_type = msg.get("type", "")

                    if msg_type == "response":
                        ct = msg.get("content_type", "text")
                        text = msg.get("data", "")
                        if ct == "genui":
                            genui = msg.get("genui", {})
                            print(f"  {C.MAGENTA}[GenUI]{C.RESET} {json.dumps(genui, indent=2)[:500]}")
                        elif text:
                            print(f"  {C.GREEN}Agent:{C.RESET} {text}")

                    elif msg_type == "transcription":
                        direction = msg.get("direction", "")
                        text = msg.get("text", "")
                        if direction == "output" and text.strip():
                            print(f"  {C.GREEN}Agent:{C.RESET} {text}")

                    elif msg_type == "tool_call":
                        tool = msg.get("tool_name", "?")
                        status = msg.get("status", "started")
                        args = msg.get("arguments", {})
                        kind = msg.get("action_kind", "")
                        label = msg.get("source_label", "")
                        source = f" ({label})" if label else ""
                        if status == "started":
                            args_str = json.dumps(args, indent=None)
                            if len(args_str) > 120:
                                args_str = args_str[:120] + "..."
                            print(f"  {C.CYAN}[{tool}]{C.RESET}{source} {args_str}")

                    elif msg_type == "tool_response":
                        tool = msg.get("tool_name", "?")
                        result = msg.get("result", "")
                        success = msg.get("success", True)
                        label = msg.get("source_label", "")
                        source = f" ({label})" if label else ""
                        color = C.GREEN if success else C.RED
                        display = result[:200] + "..." if len(result) > 200 else result
                        print(f"  {color}[{tool} done]{C.RESET}{source} {display}")

                    elif msg_type == "image_response":
                        desc = msg.get("description", "No description")
                        mime = msg.get("mime_type", "?")
                        has_data = bool(msg.get("image_base64"))
                        print(f"  {C.MAGENTA}[Image: {desc}]{C.RESET} ({mime}, {'has data' if has_data else 'no data'})")

                    elif msg_type == "tool_invocation":
                        # T3 reverse-RPC: server asking us to run a local tool
                        call_id = msg.get("call_id", "")
                        tool = msg.get("tool", "?")
                        args = msg.get("args", {})
                        print(f"  {C.YELLOW}[T3 → {tool}]{C.RESET} {json.dumps(args)[:150]}")

                        if enable_tools:
                            # Execute in background task (cancellable)
                            async def _run_t3(cid=call_id, t=tool, a=args):
                                result = await asyncio.get_event_loop().run_in_executor(
                                    None, _execute_local_tool, t, a
                                )
                                status = result.get("status", "?")
                                color = C.GREEN if status == "ok" else C.RED
                                print(f"  {color}[T3 ← {t}]{C.RESET} {status}")
                                await ws.send(json.dumps({
                                    "type": "tool_result",
                                    "call_id": cid,
                                    "result": result,
                                }))

                            task = asyncio.create_task(_run_t3())
                            active_tool_tasks[call_id] = task
                            task.add_done_callback(
                                lambda _t, cid=call_id: active_tool_tasks.pop(cid, None)
                            )
                        else:
                            # No tools — respond with error
                            await ws.send(json.dumps({
                                "type": "tool_result",
                                "call_id": call_id,
                                "result": {},
                                "error": "CLI tools disabled (use --no-tools to enable)",
                            }))

                    elif msg_type == "agent_activity":
                        title = msg.get("title", "")
                        status = msg.get("status", "")
                        if title and status == "started":
                            print(f"  {C.DIM}[activity] {title}{C.RESET}")

                    elif msg_type == "agent_transfer":
                        to_agent = msg.get("to_agent", "")
                        print(f"  {C.MAGENTA}[transfer → {to_agent}]{C.RESET}")

                    elif msg_type == "status":
                        state = msg.get("state", "")
                        detail = msg.get("detail", "")
                        if state == "processing":
                            print(f"  {C.DIM}[thinking...]{C.RESET}")
                        elif state == "listening" and "interrupt" in detail.lower():
                            print(f"  {C.YELLOW}[interrupted]{C.RESET}")
                        elif state == "error":
                            print(f"  {C.RED}[error]{C.RESET} {detail}")

                    elif msg_type == "error":
                        code = msg.get("code", "?")
                        desc = msg.get("description", "")
                        print(f"  {C.RED}Error ({code}):{C.RESET} {desc}")

                    elif msg_type == "persona_changed":
                        name = msg.get("persona_name", msg.get("persona_id", "?"))
                        voice = msg.get("voice", "")
                        print(f"  {C.MAGENTA}Persona changed → {name}{C.RESET}" +
                              (f" (voice: {voice})" if voice else ""))

                    elif msg_type == "cross_client":
                        action = msg.get("action", "")
                        target = msg.get("target", "")
                        data = msg.get("data", {})
                        print(f"  {C.BLUE}[cross-client]{C.RESET} {action}" +
                              (f" → {target}" if target else "") +
                              (f": {json.dumps(data)[:100]}" if data else ""))

                    elif msg_type == "session_suggestion":
                        clients = msg.get("available_clients", [])
                        message = msg.get("message", "")
                        print(f"  {C.BLUE}[session]{C.RESET} {message}")

                    elif msg_type == "client_status_update":
                        clients = msg.get("clients", [])
                        session_state["other_clients"] = [
                            c.get("client_type", "?") for c in clients
                        ] if isinstance(clients, list) and clients and isinstance(clients[0], dict) else clients

                    elif msg_type in ("ping", "connected", "auth_response"):
                        pass  # Silent

                    else:
                        pass  # Ignore unknown

            except websockets.ConnectionClosed:
                print(f"\n  {C.RED}Connection closed by server.{C.RESET}")

        reader_task = asyncio.create_task(reader())

        try:
            while True:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input(f"  {C.BOLD}You:{C.RESET} ")
                )
                line = line.strip()
                if not line:
                    continue

                # Slash commands
                if line.startswith("/"):
                    if line.lower() in ("/quit", "/exit", "/q"):
                        break
                    result = await _handle_slash_command(ws, line, session_state)
                    if result is False:  # /quit returns False
                        break
                    continue

                # Regular text message
                await ws.send(json.dumps({"type": "text", "content": line}))

        except (KeyboardInterrupt, EOFError):
            pass
        finally:
            reader_task.cancel()
            # Cancel in-flight T3 tools
            for task in active_tool_tasks.values():
                task.cancel()
            print(f"\n  {C.DIM}Goodbye!{C.RESET}")


# ─── Auto-reconnect wrapper ─────────────────────────────────────────

async def run_with_reconnect(
    server: str, token: str, enable_tools: bool, extra_capabilities: list[str] | None
) -> None:
    """Run the client with auto-reconnect on disconnection."""
    backoff = 3
    while True:
        try:
            await run_client(server, token, enable_tools, extra_capabilities)
            break  # Clean exit (user typed /quit or Ctrl+C)
        except (websockets.ConnectionClosed, OSError, ConnectionRefusedError) as e:
            print(f"\n  {C.RED}Connection lost: {e}{C.RESET}")
            print(f"  Reconnecting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
        except KeyboardInterrupt:
            break


# ─── CLI Entry Point ─────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Omni Hub CLI Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli/omni_cli.py --token <jwt>
  python cli/omni_cli.py --token-file token.txt
  python cli/omni_cli.py --token <jwt> --no-tools
  python cli/omni_cli.py --server ws://myserver:8000 --token <jwt>
        """,
    )
    p.add_argument("--server", default="ws://localhost:8000", help="WebSocket server URL")
    p.add_argument("--token", help="Firebase ID token")
    p.add_argument("--token-file", help="File containing the Firebase ID token")
    p.add_argument(
        "--capabilities",
        default="",
        help="Extra comma-separated capabilities to advertise",
    )
    p.add_argument(
        "--no-tools",
        action="store_true",
        help="Disable T3 local tools (read_file, run_command, etc.)",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # Resolve token
    token = args.token
    if not token and args.token_file:
        with open(args.token_file) as f:
            token = f.read().strip()
    if not token:
        token = os.environ.get("OMNI_TOKEN", "")
    if not token:
        print("Error: Provide --token, --token-file, or set OMNI_TOKEN env var")
        sys.exit(1)

    extra_caps = [c.strip() for c in args.capabilities.split(",") if c.strip()] if args.capabilities else None

    try:
        asyncio.run(run_with_reconnect(
            args.server, token, not args.no_tools, extra_caps,
        ))
    except KeyboardInterrupt:
        print("\n  Stopped.")
