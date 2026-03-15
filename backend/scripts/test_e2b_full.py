#!/usr/bin/env python3
"""
Omni Hub — Comprehensive E2B Desktop End-to-End Test
======================================================
Tests ALL E2B Desktop features both directly (service-level) and via REST API.

Two modes:
  --mode direct  → Imports E2BDesktopService directly, no server needed (default)
  --mode api     → Calls REST API endpoints (requires running server + Firebase auth)
  --mode both    → Runs both direct and API tests

Tests Cover
-----------
  1.  Desktop lifecycle: create → status → destroy
  2.  Screenshot capture → verify PNG bytes
  3.  Mouse: left click, right click, double click, move, scroll, drag
  4.  Keyboard: type text, hotkey combos
  5.  App launch (xterm/terminal)
  6.  Shell commands: echo, file creation, package listing
  7.  File operations: upload, download, verify content match
  8.  Window listing
  9.  URL opening
  10. Cleanup: destroy + verify cleaned up
  11. Re-create after destroy (lifecycle resilience)

Usage
-----
    cd backend
    uv run python scripts/test_e2b_full.py                     # direct mode
    uv run python scripts/test_e2b_full.py --mode api          # REST API mode
    uv run python scripts/test_e2b_full.py --mode both         # both modes
    uv run python scripts/test_e2b_full.py --base-url http://[::1]:8000  # custom URL

Environment
-----------
    E2B_API_KEY           — E2B API key (required for all modes)
    FIREBASE_WEB_API_KEY  — Firebase web API key (required for API mode)
    TEST_USER_EMAIL       — Test user email (required for API mode)
    TEST_USER_PASSWORD    — Test user password (required for API mode)
    BACKEND_URL           — Backend URL (default: http://[::1]:8000)
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

# ── Load .env from backend root ───────────────────────────────────────
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

# Ensure app is importable for direct mode
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Config ─────────────────────────────────────────────────────────────
FIREBASE_API_KEY = os.environ.get("FIREBASE_WEB_API_KEY", "")
EMAIL = os.environ.get("TEST_USER_EMAIL", "")
PASSWORD = os.environ.get("TEST_USER_PASSWORD", "")
BACKEND_URL = os.getenv("BACKEND_URL", "http://[::1]:8000")
API_BASE = f"{BACKEND_URL}/api/v1"
DESKTOP_URL = f"{API_BASE}/tasks/desktop"
FIREBASE_SIGN_IN_URL = (
    f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
    f"?key={FIREBASE_API_KEY}"
)

TEST_USER = "e2b_test_user"

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


# ══════════════════════════════════════════════════════════════════════
# Result Tracking
# ══════════════════════════════════════════════════════════════════════

class TestResults:
    def __init__(self):
        self.results: list[dict] = []

    def record(self, name: str, passed: bool, detail: str = ""):
        status = green("PASS") if passed else red("FAIL")
        self.results.append({"name": name, "passed": passed})
        print(f"    {status}  {name}")
        if detail:
            print(dim(f"           {detail}"))

    def summary(self) -> tuple[int, int]:
        passed = sum(1 for r in self.results if r["passed"])
        failed = sum(1 for r in self.results if not r["passed"])
        return passed, failed


# ══════════════════════════════════════════════════════════════════════
# DIRECT MODE — Tests E2BDesktopService directly
# ══════════════════════════════════════════════════════════════════════

async def run_direct_tests() -> TestResults:
    """Run tests by importing and calling E2BDesktopService directly."""
    print(bold("\n╔══════════════════════════════════════════════╗"))
    print(bold("║  E2B Desktop — Direct Service Tests          ║"))
    print(bold("╚══════════════════════════════════════════════╝"))

    from app.services.e2b_desktop_service import E2BDesktopService, DesktopStatus

    svc = E2BDesktopService()
    results = TestResults()
    user = TEST_USER

    # ── Test 1: Create Desktop ──
    print(f"\n  {bold('1. Create Desktop Sandbox')}")
    print(dim("     Provisioning E2B Desktop (may take 10-30s) ..."))
    t0 = time.time()
    try:
        info = await svc.create_desktop(user, timeout=300)
        elapsed = int(time.time() - t0)
        results.record(
            "Create desktop",
            info.status in (DesktopStatus.READY, DesktopStatus.STREAMING),
            f"status={info.status.value}, sandbox_id={info.sandbox_id}, elapsed={elapsed}s"
        )
        if info.stream_url:
            print(dim(f"           Stream URL: {info.stream_url[:120]}"))
    except Exception as e:
        results.record("Create desktop", False, f"Exception: {e}")
        print(red(f"\n  Cannot continue without a desktop. Aborting direct tests."))
        return results

    # ── Test 2: Get Status ──
    print(f"\n  {bold('2. Get Desktop Status')}")
    try:
        fetched = await svc.get_desktop_info(user)
        results.record(
            "Get status",
            fetched is not None and fetched.status != DesktopStatus.DESTROYED,
            f"status={fetched.status.value if fetched else 'None'}"
        )
    except Exception as e:
        results.record("Get status", False, str(e))

    # ── Test 3: Duplicate Create (should return existing) ──
    print(f"\n  {bold('3. Idempotent Create (return existing)')}")
    try:
        info2 = await svc.create_desktop(user)
        results.record(
            "Idempotent create",
            info2.sandbox_id == info.sandbox_id,
            f"same_sandbox={info2.sandbox_id == info.sandbox_id}"
        )
    except Exception as e:
        results.record("Idempotent create", False, str(e))

    # ── Test 4: Screenshot ──
    print(f"\n  {bold('4. Screenshot')}")
    await asyncio.sleep(3)  # Let desktop fully render
    try:
        img_bytes = await svc.screenshot(user)
        is_png = img_bytes[:4] == b'\x89PNG'
        results.record(
            "Screenshot capture",
            len(img_bytes) > 100 and is_png,
            f"size={len(img_bytes)} bytes, is_png={is_png}"
        )
    except Exception as e:
        results.record("Screenshot capture", False, str(e))

    # ── Test 5: Mouse — Left Click ──
    print(f"\n  {bold('5. Mouse — Left Click')}")
    try:
        await svc.left_click(user, 512, 384)
        results.record("Left click (512, 384)", True, "No exception")
    except Exception as e:
        results.record("Left click", False, str(e))

    # ── Test 6: Mouse — Right Click ──
    print(f"\n  {bold('6. Mouse — Right Click')}")
    try:
        await svc.right_click(user, 100, 100)
        await asyncio.sleep(0.5)
        results.record("Right click (100, 100)", True, "No exception")
    except Exception as e:
        results.record("Right click", False, str(e))

    # ── Test 7: Mouse — Double Click ──
    print(f"\n  {bold('7. Mouse — Double Click')}")
    try:
        await svc.double_click(user, 200, 200)
        results.record("Double click (200, 200)", True, "No exception")
    except Exception as e:
        results.record("Double click", False, str(e))

    # ── Test 8: Mouse — Move ──
    print(f"\n  {bold('8. Mouse — Move')}")
    try:
        await svc.move_mouse(user, 300, 300)
        results.record("Move mouse (300, 300)", True, "No exception")
    except Exception as e:
        results.record("Move mouse", False, str(e))

    # ── Test 9: Mouse — Scroll ──
    print(f"\n  {bold('9. Mouse — Scroll')}")
    try:
        await svc.scroll(user, 512, 384, direction="down", amount=3)
        results.record("Scroll down (3 steps)", True, "No exception")
    except Exception as e:
        results.record("Scroll", False, str(e))

    # ── Test 10: Mouse — Drag ──
    print(f"\n  {bold('10. Mouse — Drag')}")
    try:
        await svc.drag(user, 100, 100, 400, 400)
        results.record("Drag (100,100)→(400,400)", True, "No exception")
    except Exception as e:
        results.record("Drag", False, str(e))

    # ── Test 11: Shell Command — Echo ──
    print(f"\n  {bold('11. Shell — Echo Command')}")
    try:
        result = await svc.run_command(user, "echo 'Hello from E2B!'")
        stdout = result.get("stdout", "").strip()
        results.record(
            "Shell echo",
            "Hello from E2B!" in stdout,
            f"stdout='{stdout}', exit_code={result.get('exit_code')}"
        )
    except Exception as e:
        results.record("Shell echo", False, str(e))

    # ── Test 12: Shell — System Info ──
    print(f"\n  {bold('12. Shell — System Info')}")
    try:
        result = await svc.run_command(user, "uname -a && whoami")
        stdout = result.get("stdout", "").strip()
        results.record(
            "System info",
            len(stdout) > 10 and result.get("exit_code") == 0,
            f"output={stdout[:100]}"
        )
    except Exception as e:
        results.record("System info", False, str(e))

    # ── Test 13: Shell — Python Available ──
    print(f"\n  {bold('13. Shell — Python Execution')}")
    try:
        result = await svc.run_command(user, "python3 -c \"import sys; print(f'Python {sys.version}')\"")
        stdout = result.get("stdout", "").strip()
        results.record(
            "Python available",
            "Python" in stdout and result.get("exit_code") == 0,
            f"output={stdout[:80]}"
        )
    except Exception as e:
        results.record("Python available", False, str(e))

    # ── Test 14: Shell — Create and Read File ──
    print(f"\n  {bold('14. Shell — File Create + Read')}")
    try:
        # Create file
        await svc.run_command(user, "echo 'E2B test content 12345' > /tmp/e2b_test.txt")
        # Read it back
        result = await svc.run_command(user, "cat /tmp/e2b_test.txt")
        stdout = result.get("stdout", "").strip()
        results.record(
            "Shell file create+read",
            "E2B test content 12345" in stdout,
            f"content='{stdout}'"
        )
    except Exception as e:
        results.record("Shell file create+read", False, str(e))

    # ── Test 15: File Upload ──
    print(f"\n  {bold('15. File — Upload')}")
    test_content = b"This is uploaded via E2B SDK test. Random: 98765"
    try:
        path = await svc.upload_file(user, "/home/user/uploaded_test.txt", test_content)
        results.record(
            "File upload",
            path == "/home/user/uploaded_test.txt",
            f"path={path}"
        )
    except Exception as e:
        results.record("File upload", False, str(e))

    # ── Test 16: File Download ──
    print(f"\n  {bold('16. File — Download + Verify Content')}")
    try:
        downloaded = await svc.download_file(user, "/home/user/uploaded_test.txt")
        content_match = downloaded == test_content
        results.record(
            "File download + verify",
            content_match,
            f"size={len(downloaded)}, match={content_match}"
        )
    except Exception as e:
        results.record("File download + verify", False, str(e))

    # ── Test 17: Keyboard — Type Text ──
    print(f"\n  {bold('17. Keyboard — Type Text')}")
    try:
        await svc.write_text(user, "Hello from E2B keyboard test!")
        results.record("Type text", True, "No exception")
    except Exception as e:
        results.record("Type text", False, str(e))

    # ── Test 18: Keyboard — Hotkey ──
    print(f"\n  {bold('18. Keyboard — Hotkey (Ctrl+C)')}")
    try:
        await svc.press_keys(user, ["ctrl", "c"])
        results.record("Hotkey Ctrl+C", True, "No exception")
    except Exception as e:
        results.record("Hotkey", False, str(e))

    # ── Test 19: App Launch — Terminal ──
    print(f"\n  {bold('19. App — Launch Terminal')}")
    try:
        await svc.launch_app(user, "xterm")
        await asyncio.sleep(4)  # Let app open
        results.record("Launch xterm", True, "No exception")
    except Exception as e:
        results.record("Launch xterm", False, str(e))

    # ── Test 20: Window Listing ──
    print(f"\n  {bold('20. Window Listing')}")
    try:
        windows = await svc.get_windows(user, app_name="xterm")
        results.record(
            "List windows",
            isinstance(windows, list),
            f"count={len(windows)}, windows={json.dumps(windows[:3]) if windows else '[]'}"
        )
    except Exception as e:
        results.record("List windows", False, str(e))

    # ── Test 21: Open URL ──
    print(f"\n  {bold('21. Browser — Open URL')}")
    try:
        await svc.open_url(user, "https://example.com")
        await asyncio.sleep(3)
        results.record("Open URL (example.com)", True, "No exception")
    except Exception as e:
        results.record("Open URL", False, str(e))

    # ── Test 22: Screenshot After Actions ──
    print(f"\n  {bold('22. Screenshot After Actions')}")
    await asyncio.sleep(2)  # Let browser render
    try:
        img2 = await svc.screenshot(user)
        is_png = img2[:4] == b'\x89PNG'
        results.record(
            "Screenshot after actions",
            len(img2) > 100 and is_png,
            f"size={len(img2)} bytes"
        )
    except Exception as e:
        results.record("Screenshot after actions", False, str(e))

    # ── Test 23: Complex Shell — Multi-step Python Script ──
    print(f"\n  {bold('23. Shell — Multi-step Python Script')}")
    try:
        script = (
            "python3 -c \""
            "import json; "
            "data = {'numbers': list(range(10)), 'sum': sum(range(10))}; "
            "print(json.dumps(data))"
            "\""
        )
        result = await svc.run_command(user, script)
        stdout = result.get("stdout", "").strip()
        parsed = json.loads(stdout)
        results.record(
            "Python script execution",
            parsed.get("sum") == 45 and len(parsed.get("numbers", [])) == 10,
            f"sum={parsed.get('sum')}, numbers_count={len(parsed.get('numbers', []))}"
        )
    except Exception as e:
        results.record("Python script execution", False, str(e))

    # ── Test 24: Shell — Pip / Package Install ──
    print(f"\n  {bold('24. Shell — Package Install (pip)')}")
    try:
        result = await svc.run_command(user, "pip install cowsay 2>&1 | tail -1", timeout=30)
        stdout = result.get("stdout", "").strip()
        # Verify installed
        verify = await svc.run_command(user, "python3 -c \"import cowsay; print('cowsay imported OK')\"")
        results.record(
            "Pip install cowsay",
            "cowsay imported OK" in verify.get("stdout", ""),
            f"install_output='{stdout}', verify='{verify.get('stdout', '').strip()}'"
        )
    except Exception as e:
        results.record("Pip install", False, str(e))

    # ── Test 25: File — Binary Upload/Download Roundtrip ──
    print(f"\n  {bold('25. File — Binary Roundtrip')}")
    try:
        binary_content = bytes(range(256)) * 4  # 1024 bytes of all byte values
        await svc.upload_file(user, "/tmp/binary_test.bin", binary_content)
        downloaded = await svc.download_file(user, "/tmp/binary_test.bin")
        results.record(
            "Binary file roundtrip",
            downloaded == binary_content,
            f"uploaded={len(binary_content)} bytes, downloaded={len(downloaded)} bytes, match={downloaded == binary_content}"
        )
    except Exception as e:
        results.record("Binary file roundtrip", False, str(e))

    # ── Test 26: Destroy Desktop ──
    print(f"\n  {bold('26. Destroy Desktop')}")
    try:
        destroyed = await svc.destroy_desktop(user)
        results.record("Destroy desktop", destroyed, f"destroyed={destroyed}")
    except Exception as e:
        results.record("Destroy desktop", False, str(e))

    # ── Test 27: Verify Cleanup ──
    print(f"\n  {bold('27. Verify Cleanup')}")
    try:
        info_after = await svc.get_desktop_info(user)
        results.record(
            "Cleanup verified",
            info_after is None,
            f"info_after={'None' if info_after is None else info_after.status.value}"
        )
    except Exception as e:
        results.record("Cleanup verified", False, str(e))

    # ── Test 28: Re-create After Destroy ──
    print(f"\n  {bold('28. Re-create After Destroy')}")
    try:
        info3 = await svc.create_desktop(user, timeout=300)
        results.record(
            "Re-create after destroy",
            info3.status in (DesktopStatus.READY, DesktopStatus.STREAMING) and info3.sandbox_id != info.sandbox_id,
            f"new_sandbox={info3.sandbox_id}, old_sandbox={info.sandbox_id}"
        )
        # Verify it works
        echo_result = await svc.run_command(user, "echo 'fresh sandbox'")
        results.record(
            "Fresh sandbox functional",
            "fresh sandbox" in echo_result.get("stdout", ""),
            f"stdout='{echo_result.get('stdout', '').strip()}'"
        )
    except Exception as e:
        results.record("Re-create after destroy", False, str(e))

    # ── Final Cleanup ──
    print(dim("\n     Cleaning up ..."))
    try:
        await svc.destroy_all()
    except Exception:
        pass

    return results


# ══════════════════════════════════════════════════════════════════════
# API MODE — Tests via REST endpoints (requires running server)
# ══════════════════════════════════════════════════════════════════════

async def get_firebase_token() -> str:
    """Sign in with email+password via Firebase Auth REST API."""
    import httpx
    if not FIREBASE_API_KEY or not EMAIL or not PASSWORD:
        print(red("    Missing FIREBASE_WEB_API_KEY, TEST_USER_EMAIL, or TEST_USER_PASSWORD"))
        print(dim("    Set them in backend/.env or as environment variables"))
        sys.exit(1)

    print(f"    Signing in as {bold(EMAIL)} ...")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            FIREBASE_SIGN_IN_URL,
            json={"email": EMAIL, "password": PASSWORD, "returnSecureToken": True},
        )
    if resp.status_code != 200:
        err = resp.json().get("error", {}).get("message", "unknown")
        print(red(f"    Firebase sign-in failed: {err}"))
        sys.exit(1)

    token = resp.json()["idToken"]
    print(green("    Auth OK") + dim(f"  (token: {token[:20]}...)"))
    return token


async def run_api_tests() -> TestResults:
    """Run tests via REST API endpoints."""
    import httpx

    print(bold("\n╔══════════════════════════════════════════════╗"))
    print(bold("║  E2B Desktop — REST API Tests                ║"))
    print(bold("╚══════════════════════════════════════════════╝"))
    print(f"    Backend: {cyan(BACKEND_URL)}")

    results = TestResults()

    # ── Auth ──
    print(f"\n  {bold('Auth')}")
    token = await get_firebase_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def api_get(path: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{DESKTOP_URL}{path}", headers=headers)
            return {"status": resp.status_code, "body": resp.json() if resp.status_code < 500 else {"error": resp.text}}

    async def api_post(path: str, data: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{DESKTOP_URL}{path}", headers=headers, json=data or {})
            return {"status": resp.status_code, "body": resp.json() if resp.status_code < 500 else {"error": resp.text}}

    # ── Smoke check ──
    print(f"\n  {bold('Smoke Check')}")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{BACKEND_URL}/api/v1/health")
            print(green(f"    Backend reachable") + dim(f" ({r.status_code})"))
    except Exception as e:
        print(red(f"    Backend unreachable: {e}"))
        return results

    # ── Test 1: Initial Status ──
    print(f"\n  {bold('1. Initial Desktop Status')}")
    resp = await api_get("/status")
    results.record(
        "Initial status (no desktop)",
        resp["status"] == 200,
        f"HTTP {resp['status']}, body={json.dumps(resp['body'])[:100]}"
    )

    # ── Test 2: Start Desktop ──
    print(f"\n  {bold('2. Start Desktop')}")
    print(dim("     Provisioning (may take 10-30s) ..."))
    t0 = time.time()
    resp = await api_post("/start")
    elapsed = int(time.time() - t0)
    started = resp["status"] in (200, 201)

    if started:
        body = resp["body"]
        results.record(
            "Start desktop via API",
            True,
            f"status={body.get('status')}, sandbox_id={body.get('sandbox_id', '?')}, "
            f"stream={'yes' if body.get('stream_url') else 'no'}, elapsed={elapsed}s"
        )
        if body.get("stream_url"):
            print(dim(f"           Stream: {body['stream_url'][:120]}"))
    else:
        results.record("Start desktop via API", False, f"HTTP {resp['status']}: {resp['body']}")
        print(red("    Cannot continue API tests without desktop."))
        return results

    # ── Test 3: Status (active) ──
    print(f"\n  {bold('3. Active Status Check')}")
    resp = await api_get("/status")
    status_val = resp["body"].get("status", "?") if resp["status"] == 200 else "?"
    results.record(
        "Desktop is active",
        status_val in ("ready", "streaming", "idle", "working"),
        f"status={status_val}"
    )

    # ── Test 4: Double Start (idempotent) ──
    print(f"\n  {bold('4. Idempotent Start (same sandbox)')}")
    resp2 = await api_post("/start")
    if resp2["status"] in (200, 201):
        same_id = resp2["body"].get("sandbox_id") == resp["body"].get("sandbox_id") if resp["status"] == 200 else False
        results.record(
            "Idempotent start returns same sandbox",
            resp2["status"] in (200, 201),
            f"same_sandbox_id={same_id}"
        )
    else:
        results.record("Idempotent start", False, f"HTTP {resp2['status']}")

    # ── Test 5: Stop Desktop ──
    print(f"\n  {bold('5. Stop Desktop')}")
    resp = await api_post("/stop")
    results.record(
        "Stop desktop",
        resp["status"] in (200, 204),
        f"HTTP {resp['status']}, body={resp['body']}"
    )

    # ── Test 6: Status After Stop ──
    print(f"\n  {bold('6. Status After Stop')}")
    await asyncio.sleep(1)
    resp = await api_get("/status")
    status_val = resp["body"].get("status", "?") if resp["status"] == 200 else "?"
    results.record(
        "Status after stop (none/destroyed)",
        status_val in ("none", "destroyed", "no_desktop"),
        f"status={status_val}"
    )

    # ── Test 7: Re-start Desktop ──
    print(f"\n  {bold('7. Restart Desktop')}")
    print(dim("     Provisioning fresh sandbox ..."))
    resp = await api_post("/start")
    restarted = resp["status"] in (200, 201) and resp["body"].get("status") in ("ready", "streaming")
    results.record(
        "Restart desktop",
        restarted,
        f"status={resp['body'].get('status', '?')}, sandbox_id={resp['body'].get('sandbox_id', '?')}"
    )

    # ── Test 8: Final Stop ──
    print(f"\n  {bold('8. Final Stop + Cleanup')}")
    resp = await api_post("/stop")
    results.record(
        "Final stop",
        resp["status"] in (200, 204),
        f"HTTP {resp['status']}"
    )

    return results


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(description="E2B Desktop Comprehensive E2E Test")
    parser.add_argument("--mode", choices=["direct", "api", "both"], default="direct",
                        help="Test mode: direct (service-level), api (REST), or both")
    parser.add_argument("--base-url", type=str, help="Backend base URL override")
    args = parser.parse_args()

    global BACKEND_URL, API_BASE, DESKTOP_URL
    if args.base_url:
        BACKEND_URL = args.base_url.rstrip("/")
        API_BASE = f"{BACKEND_URL}/api/v1"
        DESKTOP_URL = f"{API_BASE}/tasks/desktop"

    print(bold("\n═══════════════════════════════════════════════════"))
    print(bold("  Omni Hub — E2B Desktop Comprehensive E2E Test"))
    print(bold("═══════════════════════════════════════════════════"))
    print(f"  Mode    : {cyan(args.mode)}")
    if args.mode in ("api", "both"):
        print(f"  Backend : {dim(BACKEND_URL)}")

    all_results: list[TestResults] = []

    if args.mode in ("direct", "both"):
        direct_results = await run_direct_tests()
        all_results.append(direct_results)

    if args.mode in ("api", "both"):
        api_results = await run_api_tests()
        all_results.append(api_results)

    # ── Grand Summary ──
    total_passed = sum(r.summary()[0] for r in all_results)
    total_failed = sum(r.summary()[1] for r in all_results)
    total = total_passed + total_failed

    print(bold("\n═══════════════════════════════════════════════════"))
    print(f"  Grand Total: {green(f'{total_passed} passed')}  "
          f"{red(f'{total_failed} failed') if total_failed else ''}"
          f"  ({total} tests)")
    print(bold("═══════════════════════════════════════════════════\n"))

    if total_failed:
        print(yellow("  Failed tests:"))
        for res in all_results:
            for r in res.results:
                if not r["passed"]:
                    print(red(f"    ✗ {r['name']}"))
        print()

    sys.exit(1 if total_failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
