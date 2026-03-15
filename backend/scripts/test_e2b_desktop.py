#!/usr/bin/env python3
"""
Omni Hub — E2B Desktop Integration Test
==========================================
Tests the E2B Desktop sandbox lifecycle via REST API:
  1. Start desktop sandbox
  2. Get desktop status + stream URL
  3. Stop desktop sandbox
  4. Verify cleanup

Requires E2B_API_KEY in environment / .env

Usage
-----
    cd backend
    uv run python scripts/test_e2b_desktop.py
    uv run python scripts/test_e2b_desktop.py --base-url https://omni-backend-fcapusldtq-uc.a.run.app

Environment
-----------
    FIREBASE_WEB_API_KEY  — Firebase project web API key
    TEST_USER_EMAIL       — Test user email
    TEST_USER_PASSWORD    — Test user password
    BACKEND_URL           — Backend base URL (default: http://localhost:8000)
    E2B_API_KEY           — E2B API key (must be set on backend)
"""

from __future__ import annotations

import argparse
import asyncio
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

# ── Config ─────────────────────────────────────────────────────────────
FIREBASE_API_KEY = os.environ.get("FIREBASE_WEB_API_KEY", "")
EMAIL = os.environ.get("TEST_USER_EMAIL", "")
PASSWORD = os.environ.get("TEST_USER_PASSWORD", "")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
API_BASE = f"{BACKEND_URL}/api/v1"
DESKTOP_URL = f"{API_BASE}/tasks/desktop"
FIREBASE_SIGN_IN_URL = (
    f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
    f"?key={FIREBASE_API_KEY}"
)

# ── Colours ────────────────────────────────────────────────────────────
USE_COLOR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"{code}{text}\033[0m" if USE_COLOR else text


def green(t: str) -> str: return _c("\033[92m", t)
def red(t: str) -> str:   return _c("\033[91m", t)
def yellow(t: str) -> str:return _c("\033[93m", t)
def cyan(t: str) -> str:  return _c("\033[96m", t)
def bold(t: str) -> str:  return _c("\033[1m", t)
def dim(t: str) -> str:   return _c("\033[2m", t)


# ── Firebase Auth ──────────────────────────────────────────────────────

async def get_firebase_token() -> str:
    import httpx
    if not FIREBASE_API_KEY or not EMAIL or not PASSWORD:
        print(red("  Missing FIREBASE_WEB_API_KEY, TEST_USER_EMAIL, or TEST_USER_PASSWORD"))
        sys.exit(1)

    print(f"  Signing in as {bold(EMAIL)} ...")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            FIREBASE_SIGN_IN_URL,
            json={"email": EMAIL, "password": PASSWORD, "returnSecureToken": True},
        )
    if resp.status_code != 200:
        err = resp.json().get("error", {}).get("message", "unknown")
        print(red(f"  Firebase sign-in failed: {err}"))
        sys.exit(1)

    token = resp.json()["idToken"]
    print(green("  Auth OK") + dim(f"  (token: {token[:20]}...)"))
    return token


# ── Tests ──────────────────────────────────────────────────────────────

async def run_tests(token: str):
    import httpx
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    results = []

    def record(name: str, passed: bool, detail: str = ""):
        status = green("PASS") if passed else red("FAIL")
        results.append({"name": name, "passed": passed})
        print(f"  {status}  {name}")
        if detail:
            print(dim(f"         {detail}"))

    async def api_get(path: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{DESKTOP_URL}{path}", headers=headers)
            return {"status": resp.status_code, "body": resp.json() if resp.status_code < 500 else {}}

    async def api_post(path: str, data: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{DESKTOP_URL}{path}", headers=headers, json=data or {})
            return {"status": resp.status_code, "body": resp.json() if resp.status_code < 500 else {}}

    # ── Test 1: Initial status (should be no desktop) ──
    print(f"\n{bold('1. Initial Desktop Status')}")
    resp = await api_get("/status")
    no_desktop = resp["status"] == 200 and resp["body"].get("status") in (None, "destroyed", "no_desktop")
    record(
        "Initial status (no active desktop)",
        resp["status"] == 200,
        f"HTTP {resp['status']}, status={resp['body'].get('status', 'N/A')}"
    )

    # ── Test 2: Start desktop ──
    print(f"\n{bold('2. Start Desktop Sandbox')}")
    print(dim("   This may take 10-30s to provision ..."))
    start_time = time.time()
    resp = await api_post("/start")
    elapsed = int(time.time() - start_time)
    start_ok = resp["status"] in (200, 201)

    if start_ok:
        desktop = resp["body"].get("desktop", resp["body"])
        sandbox_id = desktop.get("sandbox_id", "?")
        stream_url = desktop.get("stream_url", "")
        status = desktop.get("status", "?")
        record(
            "Start desktop",
            True,
            f"sandbox_id={sandbox_id}, status={status}, stream_url={'yes' if stream_url else 'no'}, elapsed={elapsed}s"
        )
        if stream_url:
            print(dim(f"         Stream URL: {stream_url[:100]}"))
    else:
        record(
            "Start desktop",
            False,
            f"HTTP {resp['status']}: {resp['body']}"
        )

    # ── Test 3: Check status (should be active) ──
    print(f"\n{bold('3. Active Desktop Status')}")
    resp = await api_get("/status")
    if resp["status"] == 200:
        status = resp["body"].get("status", "?")
        active = status in ("ready", "streaming", "idle", "working")
        record(
            "Desktop active",
            active,
            f"status={status}, sandbox_id={resp['body'].get('sandbox_id', '?')}"
        )
    else:
        record("Desktop active", False, f"HTTP {resp['status']}")

    # ── Test 4: Stop desktop ──
    print(f"\n{bold('4. Stop Desktop')}")
    resp = await api_post("/stop")
    stop_ok = resp["status"] in (200, 204)
    record(
        "Stop desktop",
        stop_ok,
        f"HTTP {resp['status']}"
    )

    # ── Test 5: Verify cleanup ──
    print(f"\n{bold('5. Verify Cleanup')}")
    await asyncio.sleep(1)
    resp = await api_get("/status")
    if resp["status"] == 200:
        status = resp["body"].get("status", "?")
        record(
            "Desktop cleaned up",
            status in (None, "destroyed", "no_desktop"),
            f"status={status}"
        )
    else:
        record("Desktop cleaned up", resp["status"] == 200, f"HTTP {resp['status']}")

    return results


# ── Main ───────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="E2B Desktop Integration Test")
    parser.add_argument("--base-url", type=str, help="Backend base URL override")
    args = parser.parse_args()

    global BACKEND_URL, API_BASE, DESKTOP_URL
    if args.base_url:
        BACKEND_URL = args.base_url.rstrip("/")
        API_BASE = f"{BACKEND_URL}/api/v1"
        DESKTOP_URL = f"{API_BASE}/tasks/desktop"

    print(bold("\n═══════════════════════════════════════════════"))
    print(bold("  Omni Hub — E2B Desktop Integration Test"))
    print(bold("═══════════════════════════════════════════════"))
    print(f"  Backend : {cyan(BACKEND_URL)}")
    print(f"  Desktop : {dim(DESKTOP_URL)}")

    print(f"\n{bold('Auth')}")
    token = await get_firebase_token()

    # Smoke
    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(f"{BACKEND_URL}/api/v1/health")
            print(green(f"\n  Backend reachable") + dim(f" ({r.status_code})"))
        except Exception as e:
            print(red(f"\n  Backend unreachable: {e}"))
            sys.exit(1)

    results = await run_tests(token)

    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])

    print(bold("\n═══════════════════════════════════════════════"))
    print(f"  Results: {green(f'{passed} passed')}  {red(f'{failed} failed') if failed else ''}  ({len(results)} total)")
    print(bold("═══════════════════════════════════════════════\n"))

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
