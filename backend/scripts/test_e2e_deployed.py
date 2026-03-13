"""End-to-end smoke tests for the deployed backend on Cloud Run.

Usage:  python scripts/test_e2e_deployed.py [BASE_URL]
"""
import asyncio
import sys

import httpx
import websockets

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://omni-backend-666233642847.us-central1.run.app"
WS_BASE = BASE.replace("https://", "wss://").replace("http://", "ws://")

passed = 0
failed = 0


def ok(name: str, detail: str = ""):
    global passed
    passed += 1
    print(f"  ✓ {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str = ""):
    global failed
    failed += 1
    print(f"  ✗ {name}" + (f" — {detail}" if detail else ""))


async def main():
    global passed, failed

    print(f"\n=== E2E Tests against {BASE} ===\n")

    async with httpx.AsyncClient(follow_redirects=False, timeout=15) as c:
        # 1. Health endpoint
        r = await c.get(f"{BASE}/health")
        if r.status_code == 200 and r.json().get("status") == "healthy":
            ok("GET /health", f"{r.json()['environment']}, v{r.json()['version']}")
        else:
            fail("GET /health", f"status={r.status_code}")

        # 2. /api/v1/clients — no trailing-slash redirect
        r = await c.get(f"{BASE}/api/v1/clients")
        if r.status_code in (401, 403):
            ok("GET /api/v1/clients — no redirect", f"got {r.status_code} (auth required, no 307)")
        elif r.status_code == 307:
            fail("GET /api/v1/clients — STILL REDIRECTING", f"Location: {r.headers.get('location')}")
        else:
            ok("GET /api/v1/clients — no redirect", f"got {r.status_code}")

        # 3. /api/v1/personas — no redirect
        r = await c.get(f"{BASE}/api/v1/personas")
        if r.status_code in (401, 403):
            ok("GET /api/v1/personas — no redirect", f"got {r.status_code}")
        elif r.status_code == 307:
            fail("GET /api/v1/personas — STILL REDIRECTING", f"Location: {r.headers.get('location')}")
        else:
            ok("GET /api/v1/personas — no redirect", f"got {r.status_code}")

        # 4. /api/v1/sessions — no redirect
        r = await c.get(f"{BASE}/api/v1/sessions")
        if r.status_code in (401, 403):
            ok("GET /api/v1/sessions — no redirect", f"got {r.status_code}")
        elif r.status_code == 307:
            fail("GET /api/v1/sessions — STILL REDIRECTING", f"Location: {r.headers.get('location')}")
        else:
            ok("GET /api/v1/sessions — no redirect", f"got {r.status_code}")

        # 5. /api/v1/gallery — no redirect
        r = await c.get(f"{BASE}/api/v1/gallery")
        if r.status_code in (401, 403):
            ok("GET /api/v1/gallery — no redirect", f"got {r.status_code}")
        elif r.status_code == 307:
            fail("GET /api/v1/gallery — STILL REDIRECTING", f"Location: {r.headers.get('location')}")
        else:
            ok("GET /api/v1/gallery — no redirect", f"got {r.status_code}")

        # 6. Known 404
        r = await c.get(f"{BASE}/api/v1/nonexistent")
        if r.status_code == 404:
            ok("GET /api/v1/nonexistent → 404")
        else:
            fail("GET /api/v1/nonexistent", f"expected 404, got {r.status_code}")

        # 7. MCP catalog (public endpoint that may or may not require auth)
        r = await c.get(f"{BASE}/api/v1/plugins/catalog")
        if r.status_code in (200, 401, 403):
            ok("GET /api/v1/plugins/catalog", f"status={r.status_code}")
        else:
            fail("GET /api/v1/plugins/catalog", f"status={r.status_code}")

    # 8. WebSocket connectivity test
    ws_url = f"{WS_BASE}/ws/live"
    try:
        async with websockets.connect(ws_url, close_timeout=5, open_timeout=10) as ws:
            # Send a non-auth message — server should close or respond with error
            await ws.send('{"type":"ping"}')
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                ok("WebSocket /ws/live — connected and received response", f"msg={str(msg)[:80]}")
            except asyncio.TimeoutError:
                ok("WebSocket /ws/live — connected (no response within 5s, expected without auth)")
            except websockets.exceptions.ConnectionClosed as e:
                ok("WebSocket /ws/live — server closed connection", f"code={e.code} reason={e.reason[:60] if e.reason else ''}")
    except websockets.exceptions.InvalidStatusCode as e:
        if e.status_code in (403, 401):
            ok("WebSocket /ws/live — server rejected unauthenticated", f"status={e.status_code}")
        else:
            fail("WebSocket /ws/live", f"unexpected status {e.status_code}")
    except Exception as e:
        fail("WebSocket /ws/live", f"{type(e).__name__}: {e}")

    # 9. WebSocket /ws/events
    ws_events_url = f"{WS_BASE}/ws/events"
    try:
        async with websockets.connect(ws_events_url, close_timeout=5, open_timeout=10) as ws:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                ok("WebSocket /ws/events — connected", f"msg={str(msg)[:80]}")
            except asyncio.TimeoutError:
                ok("WebSocket /ws/events — connected (waiting for auth)")
            except websockets.exceptions.ConnectionClosed as e:
                ok("WebSocket /ws/events — server closed", f"code={e.code}")
    except websockets.exceptions.InvalidStatusCode as e:
        if e.status_code in (403, 401):
            ok("WebSocket /ws/events — rejected unauthenticated", f"status={e.status_code}")
        else:
            fail("WebSocket /ws/events", f"status={e.status_code}")
    except Exception as e:
        fail("WebSocket /ws/events", f"{type(e).__name__}: {e}")

    # 10. CORS headers check
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.options(
            f"{BASE}/api/v1/health",
            headers={
                "Origin": "https://gemini-live-hackathon-2026.web.app",
                "Access-Control-Request-Method": "GET",
            },
        )
        acaoh = r.headers.get("access-control-allow-origin", "")
        if "gemini-live-hackathon-2026.web.app" in acaoh:
            ok("CORS allows dashboard origin", f"ACAO={acaoh}")
        elif acaoh:
            fail("CORS — wrong origin", f"ACAO={acaoh}")
        else:
            fail("CORS — no ACAO header in preflight response")

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {passed+failed}")
    if failed:
        print("SOME TESTS FAILED!")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
