"""Custom exception classes."""


class OmniError(Exception):
    """Base exception for Omni backend."""


class AuthenticationError(OmniError):
    """Firebase token verification failed."""


class SessionNotFoundError(OmniError):
    """Requested session does not exist."""


class MCPConnectionError(OmniError):
    """Failed to connect to MCP server."""


class SandboxError(OmniError):
    """E2B sandbox execution failed."""
