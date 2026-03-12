#!/usr/bin/env python3
"""Omni Hub CLI Client — text-only agent in your terminal.

Connects to the backend via WebSocket, authenticates, and provides
a REPL for conversing with the same agent that powers the web dashboard.

Demonstrates "one agent, one backend, any surface" — no GUI needed.

Usage:
    # With a Firebase ID token (get from dashboard dev tools):
    python cli/omni_cli.py --token <firebase-jwt>

    # With a saved token file:
    python cli/omni_cli.py --token-file ~/.omni_token

    # Custom server:
    python cli/omni_cli.py --server ws://localhost:8000 --token <jwt>

Capabilities example (advertise local tools):
    python cli/omni_cli.py --token <jwt> --capabilities read_file,write_file,run_command
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    print("Install websockets: pip install websockets")
    sys.exit(1)


async def main(server: str, token: str, capabilities: list[str], local_tools: list[dict]) -> None:
    uri = f"{server}/ws/chat"
    print(f"\n  Omni Hub CLI — connecting to {uri}")
    print("  Type your message and press Enter. Ctrl+C to quit.\n")

    async with websockets.connect(uri) as ws:
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
                print(f"  Auth failed: {resp.get('error', 'unknown')}")
                return
            user_id = resp.get("user_id", "?")
            tools = resp.get("available_tools", [])
            others = resp.get("other_clients_online", [])
            print(f"  Authenticated as {user_id}")
            if tools:
                print(f"  Available tools: {', '.join(tools[:10])}{'...' if len(tools) > 10 else ''}")
            if others:
                print(f"  Other clients online: {', '.join(others)}")
            print()

        # Phase 2 — REPL loop
        async def reader():
            """Read server messages and print them."""
            try:
                async for raw_msg in ws:
                    try:
                        msg = json.loads(raw_msg)
                    except json.JSONDecodeError:
                        continue
                    msg_type = msg.get("type", "")

                    if msg_type == "response":
                        text = msg.get("data", "")
                        if text:
                            print(f"  Agent: {text}")

                    elif msg_type == "transcription":
                        direction = msg.get("direction", "")
                        text = msg.get("text", "")
                        if direction == "output" and text:
                            print(f"  Agent: {text}")

                    elif msg_type == "tool_call":
                        tool = msg.get("tool_name", "?")
                        args = msg.get("arguments", {})
                        print(f"  [tool] {tool}({json.dumps(args, indent=None)})")

                    elif msg_type == "tool_response":
                        tool = msg.get("tool_name", "?")
                        result = msg.get("result", "")
                        print(f"  [result] {tool} → {result[:200]}")

                    elif msg_type == "tool_invocation":
                        # T3 reverse-RPC: server asking us to run a local tool
                        call_id = msg.get("call_id", "")
                        tool = msg.get("tool", "?")
                        args = msg.get("args", {})
                        print(f"  [T3 invoke] {tool}({json.dumps(args)})")
                        # Auto-respond with a stub (real client would execute)
                        result_msg = {
                            "type": "tool_result",
                            "call_id": call_id,
                            "result": {"status": "ok", "message": f"CLI executed {tool}"},
                        }
                        await ws.send(json.dumps(result_msg))

                    elif msg_type == "status":
                        state = msg.get("state", "")
                        if state == "processing":
                            print("  [thinking...]")

                    elif msg_type == "error":
                        print(f"  Error: {msg.get('description', msg.get('code', '?'))}")

                    elif msg_type in ("ping", "connected", "client_status_update"):
                        pass  # Silent

                    else:
                        # Log unknown messages for debugging
                        pass

            except websockets.ConnectionClosed:
                print("\n  Connection closed by server.")

        reader_task = asyncio.create_task(reader())

        try:
            while True:
                line = await asyncio.get_event_loop().run_in_executor(None, lambda: input("  You: "))
                line = line.strip()
                if not line:
                    continue
                if line.lower() in ("quit", "exit", "/q"):
                    break
                await ws.send(json.dumps({"type": "text", "content": line}))
        except (KeyboardInterrupt, EOFError):
            pass
        finally:
            reader_task.cancel()
            print("\n  Goodbye!")


def parse_args():
    p = argparse.ArgumentParser(description="Omni Hub CLI Client")
    p.add_argument("--server", default="ws://localhost:8000", help="WebSocket server URL")
    p.add_argument("--token", help="Firebase ID token")
    p.add_argument("--token-file", help="File containing the Firebase ID token")
    p.add_argument(
        "--capabilities",
        default="",
        help="Comma-separated capability strings (e.g. read_file,write_file)",
    )
    p.add_argument(
        "--local-tools",
        default="",
        help="JSON file with local tool definitions",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    token = args.token
    if not token and args.token_file:
        with open(args.token_file) as f:
            token = f.read().strip()
    if not token:
        print("Error: --token or --token-file required")
        sys.exit(1)

    capabilities = [c.strip() for c in args.capabilities.split(",") if c.strip()]

    local_tools: list[dict] = []
    if args.local_tools:
        with open(args.local_tools) as f:
            local_tools = json.load(f)

    asyncio.run(main(args.server, token, capabilities, local_tools))
