"""Per-user request rate limiting middleware.

Uses a sliding-window counter (in-memory) to enforce:
  - REST endpoints: 100 requests / minute per user
  - MCP tool calls: 50 calls / minute per user
  - WebSocket frames: unlimited (rate-limited at audio level)

Returns HTTP 429 with ``Retry-After`` header when limit is exceeded.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import TYPE_CHECKING

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.utils.errors import RateLimitError
from app.utils.logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger(__name__)

__all__ = [
    "RateLimitMiddleware",
    "RateLimiter",
]

# ---------------------------------------------------------------------------
# Sliding-window rate limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """Token-bucket-style rate limiter keyed by (user_id, scope).

    Each (user, scope) pair gets *max_requests* within a *window_seconds*
    sliding window.  Old entries are pruned lazily on each ``check`` call.
    """

    def __init__(self, max_requests: int = 100, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # { (user_id, scope): [timestamp, ...] }
        self._requests: dict[tuple[str, str], list[float]] = defaultdict(list)

    def check(self, user_id: str, scope: str = "api") -> bool:
        """Return *True* if the request is allowed, *False* if rate-limited."""
        key = (user_id, scope)
        now = time.monotonic()
        cutoff = now - self.window_seconds

        # Prune old entries
        timestamps = self._requests[key]
        self._requests[key] = [t for t in timestamps if t > cutoff]

        if len(self._requests[key]) >= self.max_requests:
            return False

        self._requests[key].append(now)
        return True

    def remaining(self, user_id: str, scope: str = "api") -> int:
        """Return the number of remaining requests in the current window."""
        key = (user_id, scope)
        now = time.monotonic()
        cutoff = now - self.window_seconds
        current = [t for t in self._requests.get(key, []) if t > cutoff]
        return max(0, self.max_requests - len(current))

    def reset(self) -> None:
        """Clear all rate-limit state (useful in tests)."""
        self._requests.clear()


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

# Per-user REST rate limiter (100 req/min)
_api_limiter: RateLimiter | None = None

# Per-user MCP rate limiter (50 calls/min)
_mcp_limiter: RateLimiter | None = None


def get_api_limiter() -> RateLimiter:
    global _api_limiter
    if _api_limiter is None:
        _api_limiter = RateLimiter(max_requests=100, window_seconds=60)
    return _api_limiter


def get_mcp_limiter() -> RateLimiter:
    global _mcp_limiter
    if _mcp_limiter is None:
        _mcp_limiter = RateLimiter(max_requests=50, window_seconds=60)
    return _mcp_limiter


# ---------------------------------------------------------------------------
# FastAPI middleware
# ---------------------------------------------------------------------------


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Starlette middleware enforcing per-user rate limits on REST APIs.

    WebSocket upgrade requests (``/ws/``) are excluded — audio frames
    are rate-limited at the application level, not HTTP request level.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip WebSocket upgrades and health checks
        path = request.url.path
        if path.startswith("/ws/") or path == "/health":
            return await call_next(request)

        # Extract user_id from auth state (set by auth middleware)
        user_id: str = "anonymous"
        if hasattr(request.state, "user"):
            user_id = request.state.user.uid

        limiter = get_api_limiter()
        if not limiter.check(user_id, scope="api"):
            logger.warning("rate_limited", user_id=user_id, path=path)
            raise RateLimitError("Rate limit exceeded — try again in 60 seconds")

        response = await call_next(request)

        # Add rate-limit headers
        remaining = limiter.remaining(user_id, scope="api")
        response.headers["X-RateLimit-Limit"] = "100"
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


def add_rate_limit_middleware(app: FastAPI) -> None:
    """Register the rate limiting middleware on the FastAPI app."""
    app.add_middleware(RateLimitMiddleware)


# ---------------------------------------------------------------------------
# ADK Callbacks for agent pipeline safety
# ---------------------------------------------------------------------------


def before_model_callback(
    *,
    model: str,
    contents: list,
    **kwargs,
) -> list | None:
    """Input sanitisation + length check before sending to model.

    Returns *None* to proceed unchanged, or a modified *contents* list.
    """
    if not contents:
        return None

    # Truncate extremely long inputs to prevent token exhaustion
    max_chars = 100_000
    for i, item in enumerate(contents):
        if isinstance(item, str) and len(item) > max_chars:
            contents[i] = item[:max_chars] + "\n[TRUNCATED]"
            logger.warning("input_truncated", model=model, original_len=len(item))

    return None  # proceed with original/modified contents


def after_model_callback(
    *,
    model: str,
    response,
    **kwargs,
) -> None:
    """Response validation after model generation.

    Logs warnings for empty or suspiciously short responses.
    """
    text = getattr(response, "text", None) or ""
    if not text.strip():
        logger.warning("empty_model_response", model=model)


def before_tool_callback(
    *,
    tool_name: str,
    tool_args: dict,
    **kwargs,
) -> dict | None:
    """Pre-tool validation — MCP rate limiting, input checks."""
    if tool_name.startswith("mcp_"):
        # Apply MCP-specific rate limit
        user_id = tool_args.get("user_id", "unknown")
        limiter = get_mcp_limiter()
        if not limiter.check(user_id, scope="mcp"):
            logger.warning("mcp_rate_limited", user_id=user_id, tool=tool_name)
            return {"error": "MCP rate limit exceeded. Try again later."}
    return None


def after_tool_callback(
    *,
    tool_name: str,
    result,
    **kwargs,
) -> None:
    """Post-tool logging / MCP failure recovery."""
    if isinstance(result, dict) and result.get("error"):
        logger.warning("tool_error", tool=tool_name, error=result["error"][:200])
