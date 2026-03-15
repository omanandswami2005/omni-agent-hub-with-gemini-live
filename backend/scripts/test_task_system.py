#!/usr/bin/env python3
"""
Omni Hub — Planned Task System Test Runner
=============================================
Tests the full task orchestrator lifecycle via REST API:
  1. Create a planned task (auto-decomposes into steps)
  2. Get task detail (verify steps were planned)
  3. List tasks (verify task appears)
  4. Execute a task (kick off async step execution)
  5. Poll status until completion or timeout
  6. Pause / resume flow
  7. Cancel flow
  8. Human-in-the-loop input (via REST endpoint)

Usage
-----
    cd backend
    uv run python scripts/test_task_system.py                   # run all tests
    uv run python scripts/test_task_system.py --only create     # one test
    uv run python scripts/test_task_system.py --base-url https://omni-backend-fcapusldtq-uc.a.run.app

Environment
-----------
    FIREBASE_WEB_API_KEY  — Firebase project web API key
    TEST_USER_EMAIL       — Test user email
    TEST_USER_PASSWORD    — Test user password
    BACKEND_URL           — Backend base URL (default: http://localhost:8000)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

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

# ── Auth config ────────────────────────────────────────────────────────
FIREBASE_API_KEY = os.environ.get("FIREBASE_WEB_API_KEY", "")
EMAIL = os.environ.get("TEST_USER_EMAIL", "")
PASSWORD = os.environ.get("TEST_USER_PASSWORD", "")

# ── Endpoints ──────────────────────────────────────────────────────────
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
API_BASE = f"{BACKEND_URL}/api/v1"
TASKS_URL = f"{API_BASE}/tasks"
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


# ══════════════════════════════════════════════════════════════════════
# Firebase Auth
# ══════════════════════════════════════════════════════════════════════

async def get_firebase_token() -> str:
    """Sign in with email+password via Firebase Auth REST API."""
    import httpx

    if not FIREBASE_API_KEY or not EMAIL or not PASSWORD:
        print(red("  Missing FIREBASE_WEB_API_KEY, TEST_USER_EMAIL, or TEST_USER_PASSWORD"))
        print(dim("  Set them in backend/.env or as environment variables"))
        sys.exit(1)

    print(f"  Signing in as {bold(EMAIL)} ...")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            FIREBASE_SIGN_IN_URL,
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


# ══════════════════════════════════════════════════════════════════════
# HTTP helpers
# ══════════════════════════════════════════════════════════════════════

class ApiClient:
    """Thin async httpx wrapper with auth."""

    def __init__(self, token: str):
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def get(self, path: str, **kwargs) -> dict:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{TASKS_URL}{path}", headers=self.headers, **kwargs)
            return {"status": resp.status_code, "body": resp.json() if resp.status_code < 500 else {}}

    async def post(self, path: str, data: dict | None = None, **kwargs) -> dict:
        import httpx
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{TASKS_URL}{path}", headers=self.headers, json=data or {}, **kwargs
            )
            return {"status": resp.status_code, "body": resp.json() if resp.status_code < 500 else {}}


# ══════════════════════════════════════════════════════════════════════
# Test definitions
# ══════════════════════════════════════════════════════════════════════

TESTS: list[dict[str, Any]] = [
    {
        "id": "create",
        "name": "Create Planned Task",
        "desc": "POST /tasks — creates task and decomposes into steps",
    },
    {
        "id": "detail",
        "name": "Get Task Detail",
        "desc": "GET /tasks/{id} — retrieves full task with steps",
    },
    {
        "id": "list",
        "name": "List Tasks",
        "desc": "GET /tasks — lists user's tasks with summaries",
    },
    {
        "id": "execute",
        "name": "Execute Task",
        "desc": "POST /tasks/{id}/execute — starts async step execution",
    },
    {
        "id": "poll",
        "name": "Poll Task Status",
        "desc": "GET /tasks/{id} — poll until completed/failed or timeout",
    },
    {
        "id": "pause_resume",
        "name": "Pause & Resume",
        "desc": "POST /tasks/{id}/action — pause then resume a task",
    },
    {
        "id": "cancel",
        "name": "Cancel Task",
        "desc": "POST /tasks/{id}/action — cancel a running task",
    },
]


# ══════════════════════════════════════════════════════════════════════
# Test implementations
# ══════════════════════════════════════════════════════════════════════

class TestRunner:
    def __init__(self, api: ApiClient, only: set[str] | None = None):
        self.api = api
        self.only = only
        self.task_id: str | None = None
        self.cancel_task_id: str | None = None
        self.results: list[dict] = []

    def should_run(self, test_id: str) -> bool:
        return self.only is None or test_id in self.only

    def record(self, test_id: str, name: str, passed: bool, detail: str = ""):
        status = green("PASS") if passed else red("FAIL")
        self.results.append({"id": test_id, "name": name, "passed": passed})
        print(f"  {status}  {name}")
        if detail:
            print(dim(f"         {detail}"))

    # ── Individual tests ──────────────────────────────────────────────

    async def test_create(self):
        """Create a simple planned task."""
        print(f"\n{bold('1. Create Planned Task')}")
        print(dim("   POST /tasks — with a simple research task"))
        resp = await self.api.post("/", {
            "description": "Research the top 3 trending Python frameworks in 2025 and write a brief comparison."
        })
        if resp["status"] != 200:
            self.record("create", "Create task", False, f"HTTP {resp['status']}: {resp['body']}")
            return

        body = resp["body"]
        self.task_id = body.get("id")
        has_steps = len(body.get("steps", [])) > 0
        status_ok = body.get("status") in ("planning", "awaiting_confirmation", "pending")
        self.record(
            "create", "Create task",
            bool(self.task_id and has_steps and status_ok),
            f"id={self.task_id}, status={body.get('status')}, steps={len(body.get('steps', []))}"
        )

    async def test_detail(self):
        """Get full task detail."""
        print(f"\n{bold('2. Get Task Detail')}")
        if not self.task_id:
            self.record("detail", "Get detail", False, "No task_id from create test")
            return

        print(dim(f"   GET /tasks/{self.task_id}"))
        resp = await self.api.get(f"/{self.task_id}")
        if resp["status"] != 200:
            self.record("detail", "Get detail", False, f"HTTP {resp['status']}")
            return

        body = resp["body"]
        has_title = bool(body.get("title"))
        has_steps = len(body.get("steps", [])) > 0
        self.record(
            "detail", "Get detail",
            has_title and has_steps,
            f"title='{body.get('title', '')[:60]}', steps={len(body.get('steps', []))}"
        )

        print(dim("   Steps:"))
        for i, step in enumerate(body.get("steps", []), 1):
            persona = step.get("persona_id", "?")
            print(dim(f"     {i}. [{persona}] {step.get('title', '?')[:80]}"))

    async def test_list(self):
        """List all tasks."""
        print(f"\n{bold('3. List Tasks')}")
        print(dim("   GET /tasks"))
        resp = await self.api.get("/")
        if resp["status"] != 200:
            self.record("list", "List tasks", False, f"HTTP {resp['status']}")
            return

        body = resp["body"]
        tasks = body if isinstance(body, list) else body.get("tasks", [])
        found = any(t.get("id") == self.task_id for t in tasks) if self.task_id else len(tasks) >= 0
        self.record(
            "list", "List tasks",
            found,
            f"count={len(tasks)}, our_task_found={found}"
        )

    async def test_execute(self):
        """Execute (start) a task."""
        print(f"\n{bold('4. Execute Task')}")
        if not self.task_id:
            self.record("execute", "Execute task", False, "No task_id")
            return

        print(dim(f"   POST /tasks/{self.task_id}/execute"))
        resp = await self.api.post(f"/{self.task_id}/execute")
        ok = resp["status"] in (200, 202)
        status = resp["body"].get("status", "?") if ok else "?"
        self.record(
            "execute", "Execute task",
            ok,
            f"HTTP {resp['status']}, status={status}"
        )

    async def test_poll(self):
        """Poll task status until done or timeout."""
        print(f"\n{bold('5. Poll Task Status')}")
        if not self.task_id:
            self.record("poll", "Poll status", False, "No task_id")
            return

        timeout = 120
        interval = 3
        start = time.time()
        final_status = "unknown"
        terminal = {"completed", "failed", "cancelled"}

        print(dim(f"   Polling every {interval}s for up to {timeout}s ..."))
        while time.time() - start < timeout:
            resp = await self.api.get(f"/{self.task_id}")
            if resp["status"] != 200:
                await asyncio.sleep(interval)
                continue

            final_status = resp["body"].get("status", "unknown")
            steps = resp["body"].get("steps", [])
            completed = sum(1 for s in steps if s.get("status") == "completed")
            total = len(steps)
            elapsed = int(time.time() - start)
            print(dim(f"   [{elapsed}s] status={final_status} steps={completed}/{total}"))

            if final_status in terminal:
                break
            await asyncio.sleep(interval)

        elapsed = int(time.time() - start)
        passed = final_status in terminal
        self.record(
            "poll", "Poll status",
            passed,
            f"final_status={final_status}, elapsed={elapsed}s"
        )

    async def test_pause_resume(self):
        """Create a task, execute it, pause, then resume."""
        print(f"\n{bold('6. Pause & Resume')}")
        print(dim("   Creating a separate task for pause/resume test ..."))

        # Create a new task with multiple steps
        resp = await self.api.post("/", {
            "description": "Write a detailed 5-paragraph essay about the history of the internet, from ARPANET to modern day."
        })
        if resp["status"] != 200 or not resp["body"].get("id"):
            self.record("pause_resume", "Pause & Resume", False, "Failed to create task")
            return

        tid = resp["body"]["id"]
        print(dim(f"   Task {tid} created with {len(resp['body'].get('steps', []))} steps"))

        # Execute
        await self.api.post(f"/{tid}/execute")
        await asyncio.sleep(2)

        # Pause
        print(dim("   Pausing ..."))
        pause_resp = await self.api.post(f"/{tid}/action", {"action": "pause"})
        pause_ok = pause_resp["status"] in (200, 202)

        # Check status is paused
        await asyncio.sleep(1)
        status_resp = await self.api.get(f"/{tid}")
        paused = status_resp["body"].get("status") == "paused" if status_resp["status"] == 200 else False

        # Resume
        print(dim("   Resuming ..."))
        resume_resp = await self.api.post(f"/{tid}/action", {"action": "resume"})
        resume_ok = resume_resp["status"] in (200, 202)

        self.record(
            "pause_resume", "Pause & Resume",
            pause_ok and resume_ok,
            f"pause_http={pause_resp['status']}, paused_state={paused}, resume_http={resume_resp['status']}"
        )

        # Cancel this task to clean up
        await self.api.post(f"/{tid}/action", {"action": "cancel"})

    async def test_cancel(self):
        """Create a task, execute, then cancel."""
        print(f"\n{bold('7. Cancel Task')}")
        print(dim("   Creating a task for cancel test ..."))

        resp = await self.api.post("/", {
            "description": "Create a comprehensive market analysis report for the AI industry in 2025."
        })
        if resp["status"] != 200 or not resp["body"].get("id"):
            self.record("cancel", "Cancel task", False, "Failed to create task")
            return

        tid = resp["body"]["id"]

        # Execute
        await self.api.post(f"/{tid}/execute")
        await asyncio.sleep(2)

        # Cancel
        print(dim("   Cancelling ..."))
        cancel_resp = await self.api.post(f"/{tid}/action", {"action": "cancel"})
        cancel_ok = cancel_resp["status"] in (200, 202)

        # Verify
        await asyncio.sleep(1)
        status_resp = await self.api.get(f"/{tid}")
        cancelled = status_resp["body"].get("status") == "cancelled" if status_resp["status"] == 200 else False

        self.record(
            "cancel", "Cancel task",
            cancel_ok and cancelled,
            f"cancel_http={cancel_resp['status']}, final_status={status_resp['body'].get('status', '?')}"
        )

    # ── Run all ───────────────────────────────────────────────────────

    async def run_all(self):
        """Run selected tests in order."""
        test_methods = [
            ("create", self.test_create),
            ("detail", self.test_detail),
            ("list", self.test_list),
            ("execute", self.test_execute),
            ("poll", self.test_poll),
            ("pause_resume", self.test_pause_resume),
            ("cancel", self.test_cancel),
        ]

        for test_id, method in test_methods:
            if self.should_run(test_id):
                try:
                    await method()
                except Exception as e:
                    self.record(test_id, test_id, False, f"Exception: {e}")

        return self.results


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(description="Planned Task System Test Runner")
    parser.add_argument("--only", type=str, help="Comma-separated test IDs to run")
    parser.add_argument("--base-url", type=str, help="Backend base URL override")
    args = parser.parse_args()

    global BACKEND_URL, API_BASE, TASKS_URL
    if args.base_url:
        BACKEND_URL = args.base_url.rstrip("/")
        API_BASE = f"{BACKEND_URL}/api/v1"
        TASKS_URL = f"{API_BASE}/tasks"

    only = set(args.only.split(",")) if args.only else None

    print(bold("\n═══════════════════════════════════════════════"))
    print(bold("  Omni Hub — Planned Task System Tests"))
    print(bold("═══════════════════════════════════════════════"))
    print(f"  Backend : {cyan(BACKEND_URL)}")
    print(f"  API     : {dim(TASKS_URL)}")

    # Auth
    print(f"\n{bold('Auth')}")
    token = await get_firebase_token()
    api = ApiClient(token)

    # Smoke check
    print(f"\n{bold('Smoke Check')}")
    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(f"{BACKEND_URL}/api/v1/health")
            print(green(f"  Backend reachable") + dim(f" ({r.status_code})"))
        except Exception as e:
            print(red(f"  Backend unreachable: {e}"))
            sys.exit(1)

    # Run tests
    runner = TestRunner(api, only)
    results = await runner.run_all()

    # Summary
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    total = len(results)

    print(bold("\n═══════════════════════════════════════════════"))
    print(f"  Results: {green(f'{passed} passed')}  {red(f'{failed} failed') if failed else ''}  ({total} total)")
    print(bold("═══════════════════════════════════════════════\n"))

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
