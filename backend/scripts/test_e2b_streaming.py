#!/usr/bin/env python3
"""
E2B Desktop Streaming — E2E Test
=================================
Tests the desktop lifecycle endpoints (/tasks/desktop/*) against the
live backend: start → status → stream URL check → stop.

Usage
-----
    cd backend
    uv run python scripts/test_e2b_streaming.py
    uv run python scripts/test_e2b_streaming.py --backend https://omni-backend-fcapusldtq-uc.a.run.app
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

# ── Load .env ─────────────────────────────────────────────────────────
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

# ── Colours ───────────────────────────────────────────────────────────
USE_COLOR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"{code}{text}\033[0m" if USE_COLOR else text


PASS = lambda t: _c("\033[32m", t)
FAIL = lambda t: _c("\033[31m", t)
INFO = lambda t: _c("\033[36m", t)
BOLD = lambda t: _c("\033[1m", t)
DIM = lambda t: _c("\033[90m", t)

# ── Firebase Auth ─────────────────────────────────────────────────────


def get_firebase_token() -> str:
    """Get a Firebase ID token via email/password sign-in."""
    url = (
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
        f"?key={FIREBASE_API_KEY}"
    )
    resp = httpx.post(url, json={"email": EMAIL, "password": PASSWORD, "returnSecureToken": True})
    resp.raise_for_status()
    return resp.json()["idToken"]


# ── Tests ─────────────────────────────────────────────────────────────


def run_tests(backend: str) -> dict[str, dict]:
    """Run all E2B desktop streaming tests sequentially."""
    api_base = f"{backend}/api/v1"
    results: dict[str, dict] = {}

    # ── Step 0: Auth ──────────────────────────────────────────────
    print(BOLD("\n▸ Authenticating…"))
    try:
        token = get_firebase_token()
        print(f"  {PASS('✓')} Got Firebase token ({len(token)} chars)")
    except Exception as exc:
        print(f"  {FAIL('✗')} Firebase auth failed: {exc}")
        results["auth"] = {"pass": False, "error": str(exc)}
        return results
    results["auth"] = {"pass": True}

    headers = {"Authorization": f"Bearer {token}"}
    client = httpx.Client(headers=headers, base_url=api_base, timeout=60.0)

    # ── Step 1: Clean state — stop any existing desktop ─────────
    print(BOLD("\n▸ Cleanup: stop any existing desktop"))
    try:
        resp = client.post("/tasks/desktop/stop")
        print(f"  HTTP {resp.status_code}: {json.dumps(resp.json(), indent=2)}")
        print(f"  {INFO('ℹ')} Cleaned up pre-existing desktop (if any)")
    except Exception as exc:
        print(f"  {DIM(f'(no-op: {exc})')}")

    # ── Step 2: Status (should now be "none") ─────────────────────
    print(BOLD("\n▸ Test: desktop/status (should be none)"))
    try:
        resp = client.get("/tasks/desktop/status")
        status_data = resp.json()
        print(f"  HTTP {resp.status_code}: {json.dumps(status_data, indent=2)}")
        ok = resp.status_code == 200 and status_data.get("status") in ("none", "destroyed")
        results["status_clean"] = {"pass": ok, "data": status_data}
        print(f"  {PASS('✓') if ok else FAIL('✗')} Status: {status_data.get('status')}")
    except Exception as exc:
        print(f"  {FAIL('✗')} {exc}")
        results["status_clean"] = {"pass": False, "error": str(exc)}

    # ── Step 2: Start desktop ─────────────────────────────────────
    print(BOLD("\n▸ Test: desktop/start"))
    sandbox_id = None
    stream_url = None
    try:
        t0 = time.time()
        resp = client.post("/tasks/desktop/start")
        elapsed = time.time() - t0
        start_data = resp.json()
        print(f"  HTTP {resp.status_code} ({elapsed:.1f}s): {json.dumps(start_data, indent=2)}")

        sandbox_id = start_data.get("sandbox_id")
        stream_url = start_data.get("stream_url")
        status = start_data.get("status")

        ok = resp.status_code == 200 and sandbox_id and stream_url and status in (
            "ready",
            "streaming",
            "creating",
        )
        results["start"] = {"pass": ok, "data": start_data, "elapsed": elapsed}

        if ok:
            print(f"  {PASS('✓')} Desktop started")
            print(f"     Sandbox : {sandbox_id}")
            print(f"     Status  : {status}")
            print(f"     Stream  : {stream_url[:80]}…" if len(stream_url) > 80 else f"     Stream  : {stream_url}")
        else:
            print(f"  {FAIL('✗')} Unexpected start response")
    except Exception as exc:
        print(f"  {FAIL('✗')} Start failed: {exc}")
        results["start"] = {"pass": False, "error": str(exc)}

    # ── Step 3: Status (after start — should be streaming/ready) ──
    print(BOLD("\n▸ Test: desktop/status (after start)"))
    try:
        resp = client.get("/tasks/desktop/status")
        status_data = resp.json()
        print(f"  HTTP {resp.status_code}: {json.dumps(status_data, indent=2)}")

        ok = resp.status_code == 200 and status_data.get("status") in (
            "ready",
            "streaming",
            "working",
            "idle",
        )
        results["status_after"] = {"pass": ok, "data": status_data}
        print(
            f"  {PASS('✓') if ok else FAIL('✗')} Status: {status_data.get('status')}, "
            f"sandbox: {status_data.get('sandbox_id')}"
        )

        # Verify stream_url matches
        if status_data.get("stream_url") == stream_url and stream_url:
            print(f"  {PASS('✓')} stream_url consistent with start response")
        elif stream_url:
            print(f"  {FAIL('✗')} stream_url mismatch")
    except Exception as exc:
        print(f"  {FAIL('✗')} {exc}")
        results["status_after"] = {"pass": False, "error": str(exc)}

    # ── Step 4: Stream URL accessibility ──────────────────────────
    if stream_url:
        print(BOLD("\n▸ Test: stream URL HTTP check"))
        try:
            # E2B stream URLs serve an HTML page (noVNC/WebRTC viewer)
            stream_resp = httpx.get(stream_url, timeout=15.0, follow_redirects=True)
            ok = stream_resp.status_code in (200, 401, 403)  # 200 OK or auth-gated
            results["stream_url"] = {
                "pass": ok,
                "http_status": stream_resp.status_code,
                "content_type": stream_resp.headers.get("content-type", ""),
                "content_length": len(stream_resp.content),
            }
            print(
                f"  HTTP {stream_resp.status_code}, "
                f"Content-Type: {stream_resp.headers.get('content-type', 'n/a')}, "
                f"Size: {len(stream_resp.content)} bytes"
            )
            print(f"  {PASS('✓') if ok else FAIL('✗')} Stream URL {'accessible' if ok else 'unreachable'}")
        except Exception as exc:
            print(f"  {FAIL('✗')} Stream URL check failed: {exc}")
            results["stream_url"] = {"pass": False, "error": str(exc)}
    else:
        print(BOLD("\n▸ Test: stream URL HTTP check"))
        print(f"  {FAIL('✗')} No stream_url to test (start may have failed)")
        results["stream_url"] = {"pass": False, "error": "no stream_url"}

    # ── Step 5: Idempotent start (returns same sandbox) ───────────
    print(BOLD("\n▸ Test: idempotent start (re-call start)"))
    try:
        resp = client.post("/tasks/desktop/start")
        data2 = resp.json()
        same_sandbox = data2.get("sandbox_id") == sandbox_id
        ok = resp.status_code == 200 and same_sandbox
        results["idempotent_start"] = {"pass": ok, "same_sandbox": same_sandbox}
        print(
            f"  {PASS('✓') if ok else FAIL('✗')} "
            f"{'Same sandbox returned (idempotent)' if same_sandbox else 'Different sandbox!'}"
        )
    except Exception as exc:
        print(f"  {FAIL('✗')} {exc}")
        results["idempotent_start"] = {"pass": False, "error": str(exc)}

    # ── Step 6: Stop desktop ──────────────────────────────────────
    print(BOLD("\n▸ Test: desktop/stop"))
    try:
        resp = client.post("/tasks/desktop/stop")
        stop_data = resp.json()
        print(f"  HTTP {resp.status_code}: {json.dumps(stop_data, indent=2)}")
        ok = resp.status_code == 200 and stop_data.get("destroyed") is True
        results["stop"] = {"pass": ok, "data": stop_data}
        print(f"  {PASS('✓') if ok else FAIL('✗')} Desktop {'stopped' if ok else 'stop failed'}")
    except Exception as exc:
        print(f"  {FAIL('✗')} {exc}")
        results["stop"] = {"pass": False, "error": str(exc)}

    # ── Step 7: Status after stop ─────────────────────────────────
    print(BOLD("\n▸ Test: desktop/status (after stop)"))
    try:
        resp = client.get("/tasks/desktop/status")
        status_data = resp.json()
        print(f"  HTTP {resp.status_code}: {json.dumps(status_data, indent=2)}")
        ok = resp.status_code == 200 and status_data.get("status") in ("none", "destroyed")
        results["status_after_stop"] = {"pass": ok, "data": status_data}
        print(f"  {PASS('✓') if ok else FAIL('✗')} Status: {status_data.get('status')}")
    except Exception as exc:
        print(f"  {FAIL('✗')} {exc}")
        results["status_after_stop"] = {"pass": False, "error": str(exc)}

    # ── Step 8: Double-stop (should not error) ────────────────────
    print(BOLD("\n▸ Test: double stop (idempotent)"))
    try:
        resp = client.post("/tasks/desktop/stop")
        ok = resp.status_code == 200
        results["double_stop"] = {"pass": ok, "data": resp.json()}
        print(f"  {PASS('✓') if ok else FAIL('✗')} Double stop returned {resp.status_code}")
    except Exception as exc:
        print(f"  {FAIL('✗')} {exc}")
        results["double_stop"] = {"pass": False, "error": str(exc)}

    client.close()
    return results


# ── Summary ───────────────────────────────────────────────────────────


def print_summary(results: dict[str, dict]) -> int:
    """Print coloured summary table. Return exit code."""
    total = len(results)
    passed = sum(1 for r in results.values() if r.get("pass"))
    failed = total - passed

    print(BOLD(f"\n{'─' * 52}"))
    print(BOLD("  E2B Desktop Streaming — Test Summary"))
    print(f"{'─' * 52}")
    for name, r in results.items():
        tag = PASS("PASS") if r.get("pass") else FAIL("FAIL")
        extra = ""
        if "elapsed" in r:
            extra = DIM(f" ({r['elapsed']:.1f}s)")
        if "error" in r and not r.get("pass"):
            extra = DIM(f" — {r['error'][:60]}")
        print(f"  {tag}  {name}{extra}")
    print(f"{'─' * 52}")
    colour = PASS if failed == 0 else FAIL
    print(colour(f"  {passed}/{total} passed, {failed} failed"))
    print(f"{'─' * 52}\n")
    return 0 if failed == 0 else 1


# ── Main ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="E2B Desktop Streaming E2E Test")
    parser.add_argument("--backend", default=BACKEND_URL, help="Backend base URL")
    args = parser.parse_args()

    print(BOLD(f"Backend: {args.backend}"))
    results = run_tests(args.backend)
    code = print_summary(results)
    sys.exit(code)
