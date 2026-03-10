"""Custom exception classes and FastAPI exception handlers."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# ── Exception Hierarchy ──────────────────────────────────────────────


class OmniError(Exception):
    """Base exception for Omni backend."""

    def __init__(self, message: str = "An unexpected error occurred", status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class AuthenticationError(OmniError):
    """Firebase token verification failed."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message=message, status_code=401)


class AuthorizationError(OmniError):
    """User lacks permission for this resource."""

    def __init__(self, message: str = "Not authorized"):
        super().__init__(message=message, status_code=403)


class NotFoundError(OmniError):
    """Requested resource does not exist."""

    def __init__(self, resource: str = "Resource", identifier: str = ""):
        detail = f"{resource} not found" if not identifier else f"{resource} '{identifier}' not found"
        super().__init__(message=detail, status_code=404)


class ValidationError(OmniError):
    """Invalid input data."""

    def __init__(self, message: str = "Invalid input"):
        super().__init__(message=message, status_code=422)


class RateLimitError(OmniError):
    """Too many requests."""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message=message, status_code=429)


class MCPConnectionError(OmniError):
    """Failed to connect to MCP server."""

    def __init__(self, mcp_id: str = "", message: str = "MCP connection failed"):
        detail = f"{message}: {mcp_id}" if mcp_id else message
        super().__init__(message=detail, status_code=502)


class SandboxError(OmniError):
    """E2B sandbox execution failed."""

    def __init__(self, message: str = "Sandbox execution failed"):
        super().__init__(message=message, status_code=500)


# ── FastAPI Exception Handlers ───────────────────────────────────────


def register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers on the FastAPI app."""

    @app.exception_handler(OmniError)
    async def omni_error_handler(_request: Request, exc: OmniError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": type(exc).__name__, "message": exc.message},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": "InternalServerError", "message": "An unexpected error occurred"},
        )
