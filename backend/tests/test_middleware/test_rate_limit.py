"""Tests for the rate-limiting middleware and ADK callbacks."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.middleware.rate_limit import (
    RateLimiter,
    after_model_callback,
    after_tool_callback,
    before_model_callback,
    before_tool_callback,
    get_api_limiter,
    get_mcp_limiter,
)

# ── RateLimiter core ─────────────────────────────────────────────────


class TestRateLimiterBasic:
    def test_allows_under_limit(self):
        rl = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            assert rl.check("user1") is True

    def test_blocks_over_limit(self):
        rl = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            rl.check("user1")
        assert rl.check("user1") is False

    def test_different_users_independent(self):
        rl = RateLimiter(max_requests=2, window_seconds=60)
        assert rl.check("alice") is True
        assert rl.check("alice") is True
        assert rl.check("alice") is False
        # Bob should still be allowed
        assert rl.check("bob") is True

    def test_different_scopes_independent(self):
        rl = RateLimiter(max_requests=1, window_seconds=60)
        assert rl.check("user1", scope="api") is True
        assert rl.check("user1", scope="api") is False
        assert rl.check("user1", scope="mcp") is True

    def test_remaining_count(self):
        rl = RateLimiter(max_requests=5, window_seconds=60)
        assert rl.remaining("user1") == 5
        rl.check("user1")
        assert rl.remaining("user1") == 4

    def test_reset_clears_all(self):
        rl = RateLimiter(max_requests=1, window_seconds=60)
        rl.check("user1")
        assert rl.check("user1") is False
        rl.reset()
        assert rl.check("user1") is True


class TestSlidingWindow:
    def test_old_entries_pruned(self):
        rl = RateLimiter(max_requests=2, window_seconds=1)
        rl.check("u")
        rl.check("u")
        assert rl.check("u") is False

        # Manually age entries beyond the window
        old_ts = time.monotonic() - 2
        rl._requests[("u", "api")] = [old_ts, old_ts]
        assert rl.check("u") is True


# ── Module singletons ────────────────────────────────────────────────


class TestSingletons:
    def test_api_limiter_singleton(self):
        import app.middleware.rate_limit as mod

        mod._api_limiter = None
        a = get_api_limiter()
        b = get_api_limiter()
        assert a is b
        assert a.max_requests == 100
        mod._api_limiter = None  # cleanup

    def test_mcp_limiter_singleton(self):
        import app.middleware.rate_limit as mod

        mod._mcp_limiter = None
        a = get_mcp_limiter()
        b = get_mcp_limiter()
        assert a is b
        assert a.max_requests == 50
        mod._mcp_limiter = None  # cleanup


# ── RateLimitMiddleware ──────────────────────────────────────────────


class TestRateLimitMiddleware:
    @pytest.fixture(autouse=True)
    def _reset_limiter(self):
        """Ensure a fresh API limiter for each test."""
        import app.middleware.rate_limit as mod

        mod._api_limiter = None
        yield
        mod._api_limiter = None

    @pytest.mark.asyncio
    async def test_skips_websocket_paths(self):
        """WebSocket upgrade requests should pass through unmetered."""
        from app.middleware.rate_limit import RateLimitMiddleware

        mw = RateLimitMiddleware(app=MagicMock())

        request = MagicMock()
        request.url.path = "/ws/live"
        sentinel = object()

        async def call_next(req):
            return sentinel

        result = await mw.dispatch(request, call_next)
        assert result is sentinel

    @pytest.mark.asyncio
    async def test_skips_health(self):
        from app.middleware.rate_limit import RateLimitMiddleware

        mw = RateLimitMiddleware(app=MagicMock())
        request = MagicMock()
        request.url.path = "/health"
        sentinel = object()

        async def call_next(req):
            return sentinel

        result = await mw.dispatch(request, call_next)
        assert result is sentinel

    @pytest.mark.asyncio
    async def test_enforces_rate_limit(self):
        from app.middleware.rate_limit import RateLimitMiddleware
        from app.utils.errors import RateLimitError

        mw = RateLimitMiddleware(app=MagicMock())
        request = MagicMock()
        request.url.path = "/api/v1/stuff"
        request.state.user.uid = "user42"

        # Exhaust rate limit
        limiter = get_api_limiter()
        for _ in range(100):
            limiter.check("user42", "api")

        async def call_next(req):
            return MagicMock()

        with pytest.raises(RateLimitError):
            await mw.dispatch(request, call_next)

    @pytest.mark.asyncio
    async def test_adds_headers(self):
        from app.middleware.rate_limit import RateLimitMiddleware

        mw = RateLimitMiddleware(app=MagicMock())
        request = MagicMock()
        request.url.path = "/api/v1/stuff"
        request.state.user.uid = "user99"

        response = MagicMock()
        response.headers = {}

        async def call_next(req):
            return response

        result = await mw.dispatch(request, call_next)
        assert result.headers["X-RateLimit-Limit"] == "100"
        assert int(result.headers["X-RateLimit-Remaining"]) >= 0

    @pytest.mark.asyncio
    async def test_anonymous_user_fallback(self):
        """If auth middleware hasn't run, user_id defaults to 'anonymous'."""
        from app.middleware.rate_limit import RateLimitMiddleware

        mw = RateLimitMiddleware(app=MagicMock())
        request = MagicMock()
        request.url.path = "/api/v1/stuff"
        # Simulate no auth middleware — hasattr(request.state, "user") is False
        del request.state.user

        response = MagicMock()
        response.headers = {}

        async def call_next(req):
            return response

        result = await mw.dispatch(request, call_next)
        assert result.headers["X-RateLimit-Limit"] == "100"


# ── ADK Callbacks ────────────────────────────────────────────────────


class TestBeforeModelCallback:
    def test_returns_none_for_empty(self):
        assert before_model_callback(model="m", contents=[]) is None

    def test_returns_none_for_normal_input(self):
        assert before_model_callback(model="m", contents=["hello"]) is None

    def test_truncates_long_input(self):
        long_text = "x" * 200_000
        contents = [long_text]
        before_model_callback(model="m", contents=contents)
        assert len(contents[0]) < 200_000
        assert contents[0].endswith("[TRUNCATED]")


class TestAfterModelCallback:
    def test_empty_response_logged(self):
        response = MagicMock()
        response.text = ""
        # Should not raise
        after_model_callback(model="m", response=response)

    def test_normal_response_ok(self):
        response = MagicMock()
        response.text = "Hello!"
        after_model_callback(model="m", response=response)


class TestBeforeToolCallback:
    def test_non_mcp_tool_passes(self):
        result = before_tool_callback(tool_name="search", tool_args={})
        assert result is None

    def test_mcp_tool_under_limit(self):
        import app.middleware.rate_limit as mod

        mod._mcp_limiter = None
        result = before_tool_callback(tool_name="mcp_something", tool_args={"user_id": "u1"})
        assert result is None
        mod._mcp_limiter = None

    def test_mcp_tool_over_limit(self):
        import app.middleware.rate_limit as mod

        mod._mcp_limiter = None
        limiter = get_mcp_limiter()
        for _ in range(50):
            limiter.check("u1", "mcp")

        result = before_tool_callback(tool_name="mcp_test", tool_args={"user_id": "u1"})
        assert result is not None
        assert "error" in result
        mod._mcp_limiter = None


class TestAfterToolCallback:
    def test_no_error(self):
        after_tool_callback(tool_name="t", result={"ok": True})

    def test_logs_error(self):
        after_tool_callback(tool_name="t", result={"error": "something broke"})

    def test_non_dict_result(self):
        after_tool_callback(tool_name="t", result="plain string")
