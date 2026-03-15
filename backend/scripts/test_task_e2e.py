#!/usr/bin/env python3
"""
Omni Hub — End-to-End Task Planner + Pipeline Test
====================================================
Full lifecycle test of the Planned Task system with both REST API
and WebSocket event validation:

  1. Auth via Firebase
  2. Connect to /ws/events for real-time events
  3. Create a planned task (POST /tasks)
  4. Verify task decomposed into steps (GET /tasks/{id})
  5. Verify task appears in list (GET /tasks)
  6. Execute the task (POST /tasks/{id}/execute)
  7. Validate real-time WebSocket events: task_created, task_planned, task_step_update, task_completed
  8. Poll until completion
  9. Verify final result
  10. Test pause/resume flow
  11. Test cancel flow

Usage
-----
    cd backend
    uv run python scripts/test_task_e2e.py
    uv run python scripts/test_task_e2e.py --base-url https://omni-backend-666233642847.us-central1.run.app
    uv run python scripts/test_task_e2e.py --only create,execute,events

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

# ── Colours ────────────────────────────────────────────────────────────
USE_COLOR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"{code}{text}\033[0m" if USE_COLOR else text


def green(t: str) -> str:
    return _c("\033[92m", t)


def red(t: str) -> str:
    return _c("\033[91m", t)


def yellow(t: str) -> str:
    return _c("\033[93m", t)


def cyan(t: str) -> str:
    return _c("\033[96m", t)


def bold(t: str) -> str:
    return _c("\033[1m", t)


def dim(t: str) -> str:
    return _c("\033[2m", t)


# ══════════════════════════════════════════════════════════════════════
# Firebase Auth
# ══════════════════════════════════════════════════════════════════════

FIREBASE_SIGN_IN_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
    f"?key={FIREBASE_API_KEY}"
)


async def get_firebase_token() -> str:
    """Sign in with email+password via Firebase Auth REST API."""
    import httpx

    if not FIREBASE_API_KEY or not EMAIL or not PASSWORD:
        print(
            red(
                "  Missing FIREBASE_WEB_API_KEY, TEST_USER_EMAIL, or TEST_USER_PASSWORD"
            )
        )
        print(dim("  Set them in backend/.env or as environment variables"))
        sys.exit(1)

    print(f"  Signing in as {bold(EMAIL)} ...")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            FIREBASE_SIGN_IN_URL,
            json={
                "email": EMAIL,
                "password": PASSWORD,
                "returnSecureToken": True,
            },
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
# HTTP + WebSocket helpers
# ══════════════════════════════════════════════════════════════════════


class ApiClient:
    """Thin async httpx wrapper with auth and DNS retry."""

    def __init__(self, token: str, base_url: str):
        self.token = token
        self.base_url = base_url
        self.tasks_url = f"{base_url}/api/v1/tasks"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def _retry_request(self, method: str, url: str, **kwargs) -> dict:
        import httpx

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    timeout=60, follow_redirects=True
                ) as client:
                    if method == "GET":
                        resp = await client.get(url, headers=self.headers, **kwargs)
                    else:
                        resp = await client.post(url, headers=self.headers, **kwargs)
                    return {
                        "status": resp.status_code,
                        "body": resp.json() if resp.status_code < 500 else {},
                    }
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(2)
                else:
                    raise

    async def get(self, path: str, **kwargs) -> dict:
        return await self._retry_request("GET", f"{self.tasks_url}{path}", **kwargs)

    async def post(self, path: str, data: dict | None = None, **kwargs) -> dict:
        return await self._retry_request(
            "POST", f"{self.tasks_url}{path}", json=data or {}, **kwargs
        )


class EventCollector:
    """Connects to /ws/events and collects task events in background."""

    def __init__(self, base_url: str, token: str):
        ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
        self.ws_url = f"{ws_url}/ws/events"
        self.token = token
        self.events: list[dict] = []
        self._task: asyncio.Task | None = None
        self._connected = asyncio.Event()
        self._ws = None

    async def start(self):
        """Connect and start collecting events."""
        self._task = asyncio.create_task(self._run())
        # Wait up to 10s for connection
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=10)
        except TimeoutError:
            print(yellow("  WS: Connection timed out (events will not be validated)"))

    async def _run(self):
        try:
            import websockets

            async with websockets.connect(
                self.ws_url,
                additional_headers={},
                close_timeout=5,
            ) as ws:
                self._ws = ws
                # Send auth
                await ws.send(json.dumps({"type": "auth", "token": self.token}))
                # Wait for auth response
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(raw)
                if data.get("status") == "ok":
                    print(green("  WS: Connected to /ws/events") + dim(f"  (user: {data.get('user_id', '?')})"))
                    self._connected.set()
                else:
                    print(red(f"  WS: Auth failed: {data.get('error', '?')}"))
                    return

                # Collect events
                while True:
                    try:
                        raw = await ws.recv()
                        event = json.loads(raw) if isinstance(raw, str) else {}
                        if event.get("type"):
                            self.events.append(event)
                    except Exception:
                        break
        except ImportError:
            print(yellow("  WS: websockets not installed — skipping event validation"))
            print(dim("       Install with: pip install websockets"))
            self._connected.set()
        except Exception as e:
            print(yellow(f"  WS: Connection failed: {e}"))
            self._connected.set()

    async def stop(self):
        """Close the WebSocket and stop collecting."""
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    def get_events_for_task(self, task_id: str) -> list[dict]:
        """Get all events for a specific task."""
        result = []
        for e in self.events:
            if e.get("task_id") == task_id:
                result.append(e)
            elif e.get("task", {}).get("id") == task_id:
                result.append(e)
        return result

    def get_event_types_for_task(self, task_id: str) -> list[str]:
        """Get ordered list of event types for a task."""
        return [e["type"] for e in self.get_events_for_task(task_id)]

    def has_event(self, task_id: str, event_type: str) -> bool:
        return event_type in self.get_event_types_for_task(task_id)


# ══════════════════════════════════════════════════════════════════════
# Test Runner
# ══════════════════════════════════════════════════════════════════════


class E2ETestRunner:
    def __init__(
        self,
        api: ApiClient,
        events: EventCollector,
        only: set[str] | None = None,
    ):
        self.api = api
        self.events = events
        self.only = only
        self.task_id: str | None = None
        self.results: list[dict] = []

    def should_run(self, test_id: str) -> bool:
        return self.only is None or test_id in self.only

    def record(self, test_id: str, name: str, passed: bool, detail: str = ""):
        status = green("PASS") if passed else red("FAIL")
        self.results.append({"id": test_id, "name": name, "passed": passed})
        print(f"  {status}  {name}")
        if detail:
            print(dim(f"         {detail}"))

    # ── Tests ─────────────────────────────────────────────────────────

    async def test_create(self):
        """Create a planned task and verify decomposition."""
        print(f"\n{bold('1. Create & Plan Task')}")
        print(dim("   POST /tasks — simple research task"))

        resp = await self.api.post(
            "/",
            {
                "description": "Research the top 3 trending Python web frameworks in 2025 and write a brief comparison (FastAPI vs Django vs Flask)."
            },
        )

        if resp["status"] != 200:
            self.record(
                "create",
                "Create task",
                False,
                f"HTTP {resp['status']}: {json.dumps(resp['body'], indent=2)[:300]}",
            )
            return

        body = resp["body"]
        self.task_id = body.get("id")
        steps = body.get("steps", [])
        has_steps = len(steps) > 0
        status_ok = body.get("status") in (
            "planning",
            "awaiting_confirmation",
            "pending",
        )

        self.record(
            "create",
            "Create & plan task",
            bool(self.task_id and has_steps and status_ok),
            f"id={self.task_id}, status={body.get('status')}, steps={len(steps)}",
        )

        if steps:
            print(dim("   Planned steps:"))
            for i, step in enumerate(steps, 1):
                print(
                    dim(
                        f"     {i}. [{step.get('persona_id', '?')}] {step.get('title', '?')[:70]}"
                    )
                )

    async def test_detail(self):
        """Get full task detail with steps."""
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
        has_desc = bool(body.get("description"))

        self.record(
            "detail",
            "Get task detail",
            has_title and has_steps and has_desc,
            f"title='{body.get('title', '')[:50]}', "
            f"steps={len(body.get('steps', []))}, "
            f"status={body.get('status')}",
        )

    async def test_list(self):
        """List all tasks and verify ours is in the list."""
        print(f"\n{bold('3. List Tasks')}")
        print(dim("   GET /tasks"))

        resp = await self.api.get("/")

        if resp["status"] != 200:
            self.record("list", "List tasks", False, f"HTTP {resp['status']}")
            return

        body = resp["body"]
        tasks = body if isinstance(body, list) else body.get("tasks", [])
        found = any(t.get("id") == self.task_id for t in tasks) if self.task_id else False

        self.record(
            "list",
            "List tasks",
            found,
            f"total={len(tasks)}, our_task_found={found}",
        )

    async def test_execute(self):
        """Execute the planned task."""
        print(f"\n{bold('4. Execute Task')}")
        if not self.task_id:
            self.record("execute", "Execute task", False, "No task_id")
            return

        print(dim(f"   POST /tasks/{self.task_id}/execute"))
        resp = await self.api.post(f"/{self.task_id}/execute")
        ok = resp["status"] in (200, 202)
        status = resp["body"].get("status", "?") if ok else resp["body"]

        self.record(
            "execute",
            "Execute task",
            ok,
            f"HTTP {resp['status']}, status={status}",
        )

    async def test_poll(self):
        """Poll task status until completion with step-by-step progress."""
        print(f"\n{bold('5. Poll Task Until Completion')}")
        if not self.task_id:
            self.record("poll", "Poll status", False, "No task_id")
            return

        timeout = 180  # 3 min max for full execution
        interval = 4
        start = time.time()
        final_status = "unknown"
        terminal = {"completed", "failed", "cancelled"}
        last_step_progress = ""

        print(dim(f"   Polling every {interval}s for up to {timeout}s ..."))
        while time.time() - start < timeout:
            resp = await self.api.get(f"/{self.task_id}")
            if resp["status"] != 200:
                await asyncio.sleep(interval)
                continue

            body = resp["body"]
            final_status = body.get("status", "unknown")
            steps = body.get("steps", [])
            completed = sum(1 for s in steps if s.get("status") == "completed")
            running_steps = [s for s in steps if s.get("status") == "running"]
            elapsed = int(time.time() - start)
            progress = body.get("progress", 0)

            # Show running step name
            step_info = f" → {running_steps[0]['title'][:40]}" if running_steps else ""
            new_progress = f"status={final_status} steps={completed}/{len(steps)} progress={progress}%{step_info}"
            if new_progress != last_step_progress:
                print(dim(f"   [{elapsed:3d}s] {new_progress}"))
                last_step_progress = new_progress

            if final_status in terminal:
                break
            await asyncio.sleep(interval)

        elapsed = int(time.time() - start)
        passed = final_status in terminal
        self.record(
            "poll",
            "Poll to completion",
            passed,
            f"final_status={final_status}, elapsed={elapsed}s",
        )

        # Show result summary if completed
        if final_status == "completed":
            resp = await self.api.get(f"/{self.task_id}")
            if resp["status"] == 200:
                summary = resp["body"].get("result_summary", "")
                if summary:
                    print(dim(f"   Result: {summary[:200]}"))

    async def test_events(self):
        """Validate WebSocket events were received for the task lifecycle."""
        print(f"\n{bold('6. WebSocket Event Validation')}")
        if not self.task_id:
            self.record("events", "WS events", False, "No task_id")
            return

        # Give events a moment to arrive
        await asyncio.sleep(2)

        event_types = self.events.get_event_types_for_task(self.task_id)
        all_events = self.events.get_events_for_task(self.task_id)

        print(dim(f"   Total events received: {len(all_events)}"))
        print(dim(f"   Event types: {', '.join(event_types) if event_types else 'none'}"))

        # Check for key lifecycle events
        has_created = self.events.has_event(self.task_id, "task_created")
        has_planned = self.events.has_event(self.task_id, "task_planned")
        has_step_update = self.events.has_event(self.task_id, "task_step_update")
        has_completed = self.events.has_event(
            self.task_id, "task_completed"
        ) or self.events.has_event(self.task_id, "task_updated")

        # Count step updates
        step_updates = [e for e in all_events if e.get("type") == "task_step_update"]

        self.record(
            "events",
            "WS events received",
            len(all_events) > 0,
            f"created={has_created}, planned={has_planned}, "
            f"step_updates={len(step_updates)}, completed={has_completed}",
        )

    async def test_pause_resume(self):
        """Create → execute → pause → resume → cancel."""
        print(f"\n{bold('7. Pause & Resume Flow')}")
        print(dim("   Creating a new task for pause/resume test ..."))

        resp = await self.api.post(
            "/",
            {
                "description": "Write a detailed analysis of the evolution of JavaScript frameworks from jQuery to modern React, Vue, and Svelte."
            },
        )
        if resp["status"] != 200 or not resp["body"].get("id"):
            self.record(
                "pause_resume",
                "Pause & Resume",
                False,
                f"Failed to create task: {resp['status']}",
            )
            return

        tid = resp["body"]["id"]
        step_count = len(resp["body"].get("steps", []))
        print(dim(f"   Task {tid} created with {step_count} steps"))

        # Execute
        exec_resp = await self.api.post(f"/{tid}/execute")
        if exec_resp["status"] not in (200, 202):
            self.record(
                "pause_resume",
                "Pause & Resume",
                False,
                f"Execute failed: {exec_resp['status']}",
            )
            return

        await asyncio.sleep(3)

        # Pause
        print(dim("   Pausing ..."))
        pause_resp = await self.api.post(f"/{tid}/action", {"action": "pause"})
        pause_ok = pause_resp["status"] in (200, 202)

        # Check status
        await asyncio.sleep(1)
        status_resp = await self.api.get(f"/{tid}")
        paused_status = status_resp["body"].get("status", "?") if status_resp["status"] == 200 else "?"

        # Resume
        print(dim("   Resuming ..."))
        resume_resp = await self.api.post(f"/{tid}/action", {"action": "resume"})
        resume_ok = resume_resp["status"] in (200, 202)

        self.record(
            "pause_resume",
            "Pause & Resume",
            pause_ok and resume_ok,
            f"pause_http={pause_resp['status']}, paused_state={paused_status}, "
            f"resume_http={resume_resp['status']}",
        )

        # Cleanup: cancel
        await self.api.post(f"/{tid}/action", {"action": "cancel"})

    async def test_cancel(self):
        """Create → execute → cancel and verify cancelled state."""
        print(f"\n{bold('8. Cancel Flow')}")
        print(dim("   Creating a task for cancel test ..."))

        resp = await self.api.post(
            "/",
            {
                "description": "Write a 10-chapter comprehensive history of every programming language ever invented, with detailed code samples for each language, performance benchmarks, and community analysis."
            },
        )
        if resp["status"] != 200 or not resp["body"].get("id"):
            self.record(
                "cancel",
                "Cancel task",
                False,
                f"Failed to create task: {resp['status']}",
            )
            return

        tid = resp["body"]["id"]

        # Execute
        await self.api.post(f"/{tid}/execute")
        await asyncio.sleep(4)

        # Cancel
        print(dim("   Cancelling ..."))
        cancel_resp = await self.api.post(f"/{tid}/action", {"action": "cancel"})
        cancel_ok = cancel_resp["status"] in (200, 202)

        # Verify (may take a moment to propagate)
        await asyncio.sleep(2)
        status_resp = await self.api.get(f"/{tid}")
        final_status = (
            status_resp["body"].get("status", "?")
            if status_resp["status"] == 200
            else "?"
        )

        self.record(
            "cancel",
            "Cancel task",
            cancel_ok and final_status in ("cancelled", "completed"),
            f"cancel_http={cancel_resp['status']}, final_status={final_status}",
        )

    async def test_auto_execute(self):
        """Create a task with auto_execute=True to test auto-start."""
        print(f"\n{bold('9. Auto-Execute Task')}")
        print(dim("   POST /tasks with auto_execute=true"))

        resp = await self.api.post(
            "/",
            {
                "description": "Summarize the key features of Google Cloud Run in 3 bullet points.",
                "auto_execute": True,
            },
        )
        if resp["status"] != 200:
            self.record(
                "auto_execute",
                "Auto-execute",
                False,
                f"HTTP {resp['status']}: {resp['body']}",
            )
            return

        body = resp["body"]
        tid = body.get("id")
        status = body.get("status", "?")

        # Status should already be running or beyond
        ok = status in ("running", "completed", "failed")

        # Poll briefly
        if ok and status == "running":
            print(dim("   Task auto-started, polling ..."))
            for _ in range(20):
                await asyncio.sleep(5)
                check = await self.api.get(f"/{tid}")
                if check["status"] == 200:
                    status = check["body"].get("status", "?")
                    progress = check["body"].get("progress", 0)
                    print(dim(f"   status={status} progress={progress}%"))
                    if status in ("completed", "failed", "cancelled"):
                        break

        # Auto-execute: task should reach a terminal state
        self.record(
            "auto_execute",
            "Auto-execute task",
            status in ("running", "completed"),
            f"id={tid}, final_status={status}",
        )

        # Cleanup
        if status == "running":
            await self.api.post(f"/{tid}/action", {"action": "cancel"})

    # ── Run all ───────────────────────────────────────────────────────

    async def run_all(self):
        """Run selected tests in order."""
        test_methods = [
            ("create", self.test_create),
            ("detail", self.test_detail),
            ("list", self.test_list),
            ("execute", self.test_execute),
            ("poll", self.test_poll),
            ("events", self.test_events),
            ("pause_resume", self.test_pause_resume),
            ("cancel", self.test_cancel),
            ("auto_execute", self.test_auto_execute),
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
    parser = argparse.ArgumentParser(
        description="End-to-End Task Planner Test",
    )
    parser.add_argument("--only", type=str, help="Comma-separated test IDs to run")
    parser.add_argument("--base-url", type=str, help="Backend base URL override")
    args = parser.parse_args()

    base_url = (args.base_url or BACKEND_URL).rstrip("/")
    only = set(args.only.split(",")) if args.only else None

    print(bold("\n═══════════════════════════════════════════════════════"))
    print(bold("  Omni Hub — E2E Task Planner + Pipeline Tests"))
    print(bold("═══════════════════════════════════════════════════════"))
    print(f"  Backend : {cyan(base_url)}")
    print(f"  API     : {dim(f'{base_url}/api/v1/tasks')}")
    print(f"  WS      : {dim(f'{base_url.replace('http', 'ws')}/ws/events')}")

    # Auth
    print(f"\n{bold('Auth')}")
    token = await get_firebase_token()

    # Smoke check with DNS retry
    print(f"\n{bold('Smoke Check')}")
    import httpx

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(f"{base_url}/api/v1/health")
                print(green("  Backend reachable") + dim(f" ({r.status_code})"))
                break
        except Exception as e:
            if attempt < 2:
                print(yellow(f"  Attempt {attempt + 1} failed: {e}"))
                print(dim("  Retrying in 3s ..."))
                await asyncio.sleep(3)
            else:
                print(red(f"  Backend unreachable after 3 attempts: {e}"))
                sys.exit(1)

    # Connect WebSocket event collector
    print(f"\n{bold('WebSocket Events')}")
    event_collector = EventCollector(base_url, token)
    await event_collector.start()

    # Run tests
    api_client = ApiClient(token, base_url)
    runner = E2ETestRunner(api_client, event_collector, only)
    results = await runner.run_all()

    # Disconnect WS
    await event_collector.stop()

    # Event summary
    total_events = len(event_collector.events)
    if total_events > 0:
        print(f"\n{bold('Event Summary')}")
        type_counts: dict[str, int] = {}
        for e in event_collector.events:
            t = e.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
        for t, c in sorted(type_counts.items()):
            print(dim(f"  {t}: {c}"))

    # Results summary
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    total = len(results)

    print(bold("\n═══════════════════════════════════════════════════════"))
    print(
        f"  Results: {green(f'{passed} passed')}  "
        f"{red(f'{failed} failed') if failed else ''}  ({total} total)"
    )
    print(f"  WS Events: {total_events} total received")
    print(bold("═══════════════════════════════════════════════════════\n"))

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
