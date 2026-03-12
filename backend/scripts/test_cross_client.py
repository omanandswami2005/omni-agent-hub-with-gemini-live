#!/usr/bin/env python3
"""Cross-client test: connect two clients and verify they see each other.

Usage:
    cd backend
    python scripts/test_cross_client.py

Requires: websockets
    pip install websockets
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from urllib import request

# ── Config ──────────────────────────────────────────────────────────
API_KEY = os.environ.get("FIREBASE_WEB_API_KEY", "AIzaSyC3a98P8sOUKEwGJuJWp2gA6i7o-CW21pE")
EMAIL = os.environ.get("TEST_USER_EMAIL", "omanand@gmail.com")
PASSWORD = os.environ.get("TEST_USER_PASSWORD", "123456")
WS_URL = os.environ.get("WS_URL", "ws://localhost:8000/ws/live")
CHAT_URL = os.environ.get("CHAT_URL", "ws://localhost:8000/ws/chat")


def get_firebase_token() -> str:
    """Get a Firebase ID token via REST API (no requests dependency)."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"
    payload = json.dumps({
        "email": EMAIL,
        "password": PASSWORD,
        "returnSecureToken": True,
    }).encode()
    req = request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data["idToken"]


async def read_messages(ws, label: str, count: int = 5, timeout: float = 10.0):
    """Read up to count text messages from ws, with a per-message timeout."""
    msgs = []
    for _ in range(count):
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            if isinstance(raw, bytes):
                print(f"  [{label}] <binary {len(raw)} bytes>")
                continue
            data = json.loads(raw)
            msg_type = data.get("type", "?")
            print(f"  [{label}] {msg_type}: {json.dumps(data, indent=None)[:200]}")
            msgs.append(data)
        except asyncio.TimeoutError:
            print(f"  [{label}] (no more messages after {timeout}s)")
            break
        except Exception as e:
            print(f"  [{label}] error: {e}")
            break
    return msgs


async def main():
    try:
        import websockets
    except ImportError:
        print("ERROR: pip install websockets")
        sys.exit(1)

    print("1. Getting Firebase token...")
    token = get_firebase_token()
    print(f"   Token: {token[:30]}... ({len(token)} chars)")

    # ── Client 1: Desktop with local tools ─────────────────────
    print("\n2. Connecting DESKTOP client with local_tools...")
    desktop_ws = await websockets.connect(WS_URL)

    desktop_auth = json.dumps({
        "type": "auth",
        "token": token,
        "client_type": "desktop",
        "capabilities": ["file_io", "screenshot"],
        "local_tools": [
            {
                "name": "take_screenshot",
                "description": "Capture the desktop screen",
                "parameters": {"region": {"type": "string", "description": "full or region name"}},
            },
            {
                "name": "open_file",
                "description": "Open a file with the default application",
                "parameters": {"path": {"type": "string", "description": "File path to open"}},
            },
        ],
    })
    await desktop_ws.send(desktop_auth)
    print("   Auth sent, reading responses...")
    desktop_msgs = await read_messages(desktop_ws, "DESKTOP", count=5, timeout=8)

    # Check auth succeeded
    auth_resp = next((m for m in desktop_msgs if m.get("type") == "auth_response"), None)
    if auth_resp and auth_resp.get("status") == "ok":
        print(f"   ✓ Desktop authenticated! session={auth_resp.get('session_id', '?')[:12]}...")
    else:
        print(f"   ✗ Desktop auth failed: {auth_resp}")
        await desktop_ws.close()
        return

    # ── Client 2: Web client ───────────────────────────────────
    print("\n3. Connecting WEB client (should see desktop online)...")
    web_ws = await websockets.connect(WS_URL)

    web_auth = json.dumps({
        "type": "auth",
        "token": token,
        "client_type": "web",
    })
    await web_ws.send(web_auth)
    print("   Auth sent, reading responses...")
    web_msgs = await read_messages(web_ws, "WEB", count=5, timeout=8)

    # Check auth response includes desktop in other_clients_online
    auth_resp = next((m for m in web_msgs if m.get("type") == "auth_response"), None)
    if auth_resp and auth_resp.get("status") == "ok":
        others = auth_resp.get("other_clients_online", [])
        tools = auth_resp.get("available_tools", [])
        print(f"   ✓ Web authenticated! other_clients_online={others}")
        print(f"   ✓ Available tools ({len(tools)}): {tools[:10]}{'...' if len(tools) > 10 else ''}")
        if "desktop" in others:
            print("   ✓ CROSS-CLIENT: Web sees desktop is online!")
        else:
            print("   ✗ CROSS-CLIENT: Desktop not visible to web client")
    else:
        print(f"   ✗ Web auth failed: {auth_resp}")

    # Check if desktop received client_status_update about web joining
    print("\n4. Checking if desktop received web's connection event...")
    desktop_late = await read_messages(desktop_ws, "DESKTOP-LATE", count=3, timeout=5)
    status_update = next(
        (m for m in desktop_late if m.get("type") == "client_status_update"),
        None,
    )
    if status_update:
        print(f"   ✓ Desktop received client_status_update: {json.dumps(status_update)[:200]}")
    else:
        print("   (no client_status_update received — may have been sent earlier)")

    # ── Test text chat via /ws/chat ────────────────────────────
    print("\n5. Testing text chat via /ws/chat...")
    chat_ws = await websockets.connect(CHAT_URL)
    chat_auth = json.dumps({"type": "auth", "token": token, "client_type": "web"})
    await chat_ws.send(chat_auth)
    chat_auth_msgs = await read_messages(chat_ws, "CHAT", count=3, timeout=8)

    chat_auth_resp = next((m for m in chat_auth_msgs if m.get("type") == "auth_response"), None)
    if chat_auth_resp and chat_auth_resp.get("status") == "ok":
        print("   ✓ Chat authenticated!")

        # Send a simple message
        print("\n6. Sending text message: 'Hello, what tools do you have?'")
        await chat_ws.send(json.dumps({"type": "text", "content": "Hello, what tools do you have? List them briefly."}))
        print("   Waiting for agent response...")
        chat_responses = await read_messages(chat_ws, "CHAT-RESP", count=20, timeout=30)

        # Look for tool_call/agent_transfer messages (ActionCard testing)
        action_msgs = [m for m in chat_responses if m.get("type") in ("tool_call", "tool_response", "agent_transfer")]
        if action_msgs:
            print(f"\n   ✓ ACTION CARDS: Got {len(action_msgs)} action messages:")
            for am in action_msgs:
                kind = am.get("action_kind", "?")
                name = am.get("tool_name", am.get("to_agent", "?"))
                print(f"     - {am['type']}: {name} (kind={kind})")
        else:
            print("\n   (no tool_call/agent_transfer messages in this response)")
    else:
        print(f"   ✗ Chat auth failed: {chat_auth_resp}")

    # ── Cleanup ────────────────────────────────────────────────
    print("\n7. Cleaning up...")
    await chat_ws.close()
    await web_ws.close()
    await desktop_ws.close()
    print("   Done! All connections closed.")


if __name__ == "__main__":
    asyncio.run(main())
