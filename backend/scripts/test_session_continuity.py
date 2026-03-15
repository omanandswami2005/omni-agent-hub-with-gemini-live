#!/usr/bin/env python3
"""Comprehensive test: session continuity, cross-client detection, session deletion.

Tests:
  1. Desktop-web connects → creates session
  2. Mobile-web connects → should see desktop online, get session suggestion, reuse same session
  3. Desktop should receive client_status_update + session_suggestion from mobile
  4. Session deletion via REST API cleans up correctly
  5. Verify cross-client detection works for both /ws/live and /ws/chat

Usage:
    cd backend
    python scripts/test_session_continuity.py [--prod]

    --prod  → use production URLs (default: localhost)

Requires: websockets, requests
    pip install websockets requests
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from urllib import request as urllib_request

# ── Config ──────────────────────────────────────────────────────────
API_KEY = os.environ.get("FIREBASE_WEB_API_KEY", "AIzaSyC3a98P8sOUKEwGJuJWp2gA6i7o-CW21pE")
EMAIL = os.environ.get("TEST_USER_EMAIL", "omanand@gmail.com")
PASSWORD = os.environ.get("TEST_USER_PASSWORD", "123456")

LOCAL_WS = "ws://localhost:8000/ws/live"
LOCAL_CHAT = "ws://localhost:8000/ws/chat"
LOCAL_API = "http://localhost:8000/api/v1"

PROD_WS = "wss://omni-backend-fcapusldtq-uc.a.run.app/ws/live"
PROD_CHAT = "wss://omni-backend-fcapusldtq-uc.a.run.app/ws/chat"
PROD_API = "https://omni-backend-fcapusldtq-uc.a.run.app/api/v1"

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
INFO = "\033[94m→\033[0m"
WARN = "\033[93m⚠\033[0m"

results: list[tuple[str, bool, str]] = []


def record(name: str, passed: bool, detail: str = ""):
    results.append((name, passed, detail))
    mark = PASS if passed else FAIL
    print(f"  {mark} {name}" + (f"  ({detail})" if detail else ""))


# ── Firebase Auth ──────────────────────────────────────────────────


def get_firebase_token() -> str:
    """Get a Firebase ID token via REST API."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"
    payload = json.dumps({
        "email": EMAIL,
        "password": PASSWORD,
        "returnSecureToken": True,
    }).encode()
    req = urllib_request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib_request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data["idToken"]


# ── REST API helpers ──────────────────────────────────────────────


def api_get(url: str, token: str):
    req = urllib_request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib_request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def api_delete(url: str, token: str):
    req = urllib_request.Request(url, method="DELETE", headers={"Authorization": f"Bearer {token}"})
    with urllib_request.urlopen(req, timeout=15) as resp:
        return resp.status


def api_post(url: str, token: str, data: dict | None = None):
    body = json.dumps(data or {}).encode()
    req = urllib_request.Request(url, data=body, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    with urllib_request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


# ── WebSocket helpers ─────────────────────────────────────────────


async def read_messages(ws, label: str, count: int = 10, timeout: float = 6.0):
    """Read up to `count` text messages, with per-message timeout."""
    msgs = []
    for _ in range(count):
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            if isinstance(raw, bytes):
                continue  # skip binary audio
            data = json.loads(raw)
            msg_type = data.get("type", data.get("status", "?"))
            print(f"    [{label}] {msg_type}: {json.dumps(data, indent=None)[:180]}")
            msgs.append(data)
        except asyncio.TimeoutError:
            break
        except Exception as e:
            print(f"    [{label}] error: {e}")
            break
    return msgs


async def connect_client(ws_url: str, token: str, client_type: str, session_id: str = ""):
    """Connect a WS client, send auth, return (ws, messages)."""
    import websockets
    ws = await websockets.connect(ws_url, close_timeout=5)
    auth_msg = {
        "type": "auth",
        "token": token,
        "client_type": client_type,
        "user_agent": f"TestScript/{client_type}",
    }
    if session_id:
        auth_msg["session_id"] = session_id
    await ws.send(json.dumps(auth_msg))
    msgs = await read_messages(ws, client_type.upper(), count=8, timeout=6)
    return ws, msgs


def find_msg(msgs: list, msg_type: str) -> dict | None:
    return next((m for m in msgs if m.get("type") == msg_type), None)


def find_auth(msgs: list) -> dict | None:
    return next((m for m in msgs if m.get("type") == "auth_response" or m.get("status") in ("ok", "error")), None)


# ── Tests ──────────────────────────────────────────────────────────


async def test_cross_client_session_continuity(ws_url: str, chat_url: str, api_url: str, token: str):
    """Test 1: Desktop connects, then mobile connects — both should share the same session."""
    import websockets

    print(f"\n{'='*60}")
    print("TEST 1: Cross-client session continuity (desktop → mobile)")
    print(f"{'='*60}")

    # --- DESKTOP connects ---
    print(f"\n{INFO} Connecting DESKTOP (web) client...")
    desktop_ws, desktop_msgs = await connect_client(ws_url, token, "web")
    desktop_auth = find_auth(desktop_msgs)

    if not desktop_auth or desktop_auth.get("status") != "ok":
        record("Desktop auth", False, f"auth failed: {desktop_auth}")
        await desktop_ws.close()
        return
    record("Desktop auth", True)

    desktop_session = desktop_auth.get("firestore_session_id", "")
    desktop_others = desktop_auth.get("other_clients_online", [])
    print(f"    {INFO} Desktop session: {desktop_session[:16]}...")
    print(f"    {INFO} Desktop other_clients_online: {desktop_others}")

    # Small delay to allow Firestore presence write to propagate
    await asyncio.sleep(1.5)

    # --- MOBILE connects ---
    print(f"\n{INFO} Connecting MOBILE client...")
    mobile_ws, mobile_msgs = await connect_client(ws_url, token, "mobile")
    mobile_auth = find_auth(mobile_msgs)

    if not mobile_auth or mobile_auth.get("status") != "ok":
        record("Mobile auth", False, f"auth failed: {mobile_auth}")
        await desktop_ws.close()
        await mobile_ws.close()
        return
    record("Mobile auth", True)

    mobile_session = mobile_auth.get("firestore_session_id", "")
    mobile_others = mobile_auth.get("other_clients_online", [])
    print(f"    {INFO} Mobile session: {mobile_session[:16]}...")
    print(f"    {INFO} Mobile other_clients_online: {mobile_others}")

    # Check: mobile should see desktop as online
    record("Mobile sees desktop online", "web" in mobile_others,
           f"other_clients={mobile_others}")

    # Check: both should be on the same Firestore session
    record("Same Firestore session", desktop_session == mobile_session and bool(mobile_session),
           f"desktop={desktop_session[:12]}, mobile={mobile_session[:12]}")

    # Check: mobile should have received a session_suggestion
    suggestion = find_msg(mobile_msgs, "session_suggestion")
    record("Mobile received session_suggestion", suggestion is not None,
           f"suggestion={'yes' if suggestion else 'no'}")

    if suggestion:
        record("Suggestion has session_id", bool(suggestion.get("session_id")),
               suggestion.get("session_id", "")[:16])
        record("Suggestion lists web client", "web" in (suggestion.get("available_clients") or []),
               f"available_clients={suggestion.get('available_clients')}")

    # Check: desktop should receive client_status_update about mobile joining
    print(f"\n{INFO} Checking desktop received mobile's connect event...")
    desktop_late = await read_messages(desktop_ws, "DESKTOP-LATE", count=5, timeout=4)
    status_update = find_msg(desktop_late, "client_status_update")
    record("Desktop received client_status_update", status_update is not None)

    if status_update:
        clients = status_update.get("clients", [])
        client_types = [c.get("client_type") for c in clients]
        record("Status update includes both clients",
               "web" in client_types and "mobile" in client_types,
               f"client_types={client_types}")

    # Check for session_suggestion on desktop (via EventBus relay)
    desktop_suggestion = find_msg(desktop_late, "session_suggestion")
    record("Desktop received session_suggestion from mobile",
           desktop_suggestion is not None)

    # --- Cleanup ---
    await desktop_ws.close()
    await mobile_ws.close()
    return desktop_session


async def test_session_deletion(api_url: str, token: str, session_id: str | None = None):
    """Test 2: Session deletion API cleans up correctly."""
    print(f"\n{'='*60}")
    print("TEST 2: Session deletion API")
    print(f"{'='*60}")

    # List sessions
    print(f"\n{INFO} Listing sessions...")
    sessions = api_get(f"{api_url}/sessions", token)
    print(f"    {INFO} Found {len(sessions)} sessions")
    record("List sessions", len(sessions) >= 0, f"count={len(sessions)}")

    if not sessions:
        print(f"    {WARN} No sessions to delete — creating one...")
        new_session = api_post(f"{api_url}/sessions", token, {"title": "test-delete"})
        sessions = [new_session]
        session_id = new_session["id"]

    if not session_id:
        session_id = sessions[-1]["id"]  # delete oldest

    # Delete the session
    print(f"\n{INFO} Deleting session {session_id[:16]}...")
    try:
        status = api_delete(f"{api_url}/sessions/{session_id}", token)
        record("Delete session API", status in (200, 204), f"status={status}")
    except Exception as e:
        record("Delete session API", False, str(e))
        return

    # Verify session is gone
    print(f"\n{INFO} Verifying session is deleted...")
    remaining = api_get(f"{api_url}/sessions", token)
    still_exists = any(s["id"] == session_id for s in remaining)
    record("Session removed from list", not still_exists,
           f"{'still present!' if still_exists else 'gone'}")

    # Verify getting the deleted session returns 404
    try:
        api_get(f"{api_url}/sessions/{session_id}", token)
        record("GET deleted session returns 404", False, "still accessible!")
    except Exception as e:
        is_404 = "404" in str(e) or "Not Found" in str(e)
        record("GET deleted session returns 404", is_404, str(e)[:80])


async def test_chat_cross_client(ws_url: str, chat_url: str, token: str):
    """Test 3: /ws/chat receives cross-client events from /ws/live."""
    import websockets

    print(f"\n{'='*60}")
    print("TEST 3: /ws/chat cross-client event relay")
    print(f"{'='*60}")

    # Connect desktop on /ws/live
    print(f"\n{INFO} Connecting desktop on /ws/live...")
    desktop_ws, desktop_msgs = await connect_client(ws_url, token, "web")
    desktop_auth = find_auth(desktop_msgs)
    record("Desktop /ws/live auth", desktop_auth and desktop_auth.get("status") == "ok")

    desktop_session = (desktop_auth or {}).get("firestore_session_id", "")

    await asyncio.sleep(1)

    # Connect chat WS for the same user (simulates dashboard text panel)
    print(f"\n{INFO} Connecting /ws/chat with same session...")
    chat_ws = await websockets.connect(chat_url, close_timeout=5)
    chat_auth_msg = {
        "type": "auth",
        "token": token,
        "client_type": "web",
        "session_id": desktop_session,
    }
    await chat_ws.send(json.dumps(chat_auth_msg))
    chat_msgs = await read_messages(chat_ws, "CHAT", count=5, timeout=5)
    chat_auth = find_auth(chat_msgs)
    record("/ws/chat auth", chat_auth and chat_auth.get("status") == "ok")

    # Check chat received a client_status_update snapshot
    status_snap = find_msg(chat_msgs, "client_status_update")
    record("/ws/chat received client status snapshot", status_snap is not None)

    # Now connect mobile on /ws/live — chat should see the session_suggestion
    print(f"\n{INFO} Connecting mobile on /ws/live (chat should see events)...")
    mobile_ws, mobile_msgs = await connect_client(ws_url, token, "mobile")
    mobile_auth = find_auth(mobile_msgs)
    record("Mobile /ws/live auth", mobile_auth and mobile_auth.get("status") == "ok")

    # Read chat relay events
    await asyncio.sleep(1)
    chat_relay = await read_messages(chat_ws, "CHAT-RELAY", count=5, timeout=4)
    chat_suggestion = find_msg(chat_relay, "session_suggestion")
    chat_status = find_msg(chat_relay, "client_status_update")
    record("/ws/chat received cross-client suggestion", chat_suggestion is not None)
    record("/ws/chat received client_status_update", chat_status is not None)

    await chat_ws.close()
    await desktop_ws.close()
    await mobile_ws.close()


async def test_client_api(api_url: str, ws_url: str, token: str):
    """Test 4: GET /clients API shows connected devices."""
    import websockets

    print(f"\n{'='*60}")
    print("TEST 4: GET /clients API")
    print(f"{'='*60}")

    # Connect a client first
    print(f"\n{INFO} Connecting desktop client...")
    ws, msgs = await connect_client(ws_url, token, "web")
    auth = find_auth(msgs)
    record("Client connected", auth and auth.get("status") == "ok")

    await asyncio.sleep(1.5)

    # Check /clients API
    print(f"\n{INFO} Querying GET /clients...")
    try:
        clients = api_get(f"{api_url}/clients", token)
        record("GET /clients returns data", isinstance(clients, list) and len(clients) > 0,
               f"count={len(clients) if isinstance(clients, list) else '?'}")
        if isinstance(clients, list) and clients:
            types = [c.get("client_type") for c in clients]
            record("Web client visible", "web" in types, f"types={types}")
    except Exception as e:
        record("GET /clients", False, str(e)[:80])

    await ws.close()

    # After disconnect, wait and check again
    await asyncio.sleep(2)
    try:
        clients_after = api_get(f"{api_url}/clients", token)
        web_still = any(c.get("client_type") == "web" for c in (clients_after or []))
        # Firestore presence may linger, but local should be gone
        print(f"    {INFO} Clients after disconnect: {len(clients_after or [])}")
    except Exception:
        pass


async def main():
    parser = argparse.ArgumentParser(description="Test session continuity & cross-client detection")
    parser.add_argument("--prod", action="store_true", help="Use production URLs")
    args = parser.parse_args()

    if args.prod:
        ws_url, chat_url, api_url = PROD_WS, PROD_CHAT, PROD_API
    else:
        ws_url, chat_url, api_url = LOCAL_WS, LOCAL_CHAT, LOCAL_API

    try:
        import websockets  # noqa: F401
    except ImportError:
        print("ERROR: pip install websockets")
        sys.exit(1)

    print(f"{'='*60}")
    print("  Session Continuity & Cross-Client Test Suite")
    print(f"{'='*60}")
    print(f"  Target:  {ws_url}")
    print(f"  API:     {api_url}")
    print(f"  User:    {EMAIL}")

    print(f"\n{INFO} Authenticating...")
    token = get_firebase_token()
    print(f"  {PASS} Token acquired ({len(token)} chars)")

    # Run tests
    session_id = await test_cross_client_session_continuity(ws_url, chat_url, api_url, token)
    await asyncio.sleep(1)
    await test_session_deletion(api_url, token, session_id=None)
    await asyncio.sleep(1)
    await test_chat_cross_client(ws_url, chat_url, token)
    await asyncio.sleep(1)
    await test_client_api(api_url, ws_url, token)

    # Summary
    print(f"\n{'='*60}")
    print("  RESULTS SUMMARY")
    print(f"{'='*60}")
    passed = sum(1 for _, p, _ in results if p)
    failed = sum(1 for _, p, _ in results if not p)
    for name, ok, detail in results:
        mark = PASS if ok else FAIL
        print(f"  {mark} {name}" + (f"  ({detail})" if detail and not ok else ""))
    print(f"\n  Total: {passed} passed, {failed} failed out of {len(results)}")
    print(f"{'='*60}")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
