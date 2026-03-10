"""Code execution ADK tools — E2B sandbox primary, Agent Engine fallback.

Provides ``execute_code`` and ``install_package`` as ADK-compatible
``FunctionTool`` functions that the agent can call during conversation.

The tools delegate to :class:`~app.services.e2b_service.E2BService` for
actual execution inside a sandboxed E2B environment.
"""

from __future__ import annotations

from google.adk.tools import FunctionTool

from app.services.agent_engine_service import get_agent_engine_service
from app.services.e2b_service import ExecutionResult, get_e2b_service
from app.utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Raw async functions (ADK wraps these as FunctionTool automatically)
# ---------------------------------------------------------------------------


async def execute_code(
    code: str,
    language: str = "python",
    sandbox_id: str = "default",
) -> dict:
    """Execute code in a sandboxed environment and return the output.

    Args:
        code: Source code to execute.
        language: Programming language (python, javascript, r, etc.).
        sandbox_id: Identifier for the sandbox session.

    Returns:
        A dict with stdout, stderr, error, and any rich results.
    """
    ae = get_agent_engine_service()
    if ae.enabled:
        try:
            result = await ae.execute_code(sandbox_key=sandbox_id, code=code)
            result.setdefault("error", None)
            result.setdefault("results", [])
            return result
        except Exception:
            logger.warning("agent_engine_code_exec_failed_fallback_e2b", exc_info=True)

    svc = get_e2b_service()
    result: ExecutionResult = await svc.execute_code(
        sandbox_id,
        code,
        language=language,
    )
    logger.info(
        "code_executed",
        sandbox_id=sandbox_id,
        language=language,
        has_error=result.error is not None,
    )
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "error": result.error,
        "results": result.results,
        "provider": "e2b",
    }


async def install_package(
    package: str,
    sandbox_id: str = "default",
) -> dict:
    """Install a package in the sandbox environment.

    Args:
        package: Package name (e.g. 'pandas', 'numpy==1.26').
        sandbox_id: Identifier for the sandbox session.

    Returns:
        A dict with stdout, stderr, and any error.
    """
    ae = get_agent_engine_service()
    if ae.enabled:
        try:
            result = await ae.install_package(sandbox_key=sandbox_id, package=package)
            result.setdefault("error", None)
            return result
        except Exception:
            logger.warning("agent_engine_package_install_failed_fallback_e2b", exc_info=True)

    svc = get_e2b_service()
    result: ExecutionResult = await svc.execute_command(
        sandbox_id,
        f"pip install -q {package}",
    )
    logger.info(
        "package_installed",
        sandbox_id=sandbox_id,
        package=package,
        has_error=result.error is not None,
    )
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "error": result.error,
        "provider": "e2b",
    }


# ---------------------------------------------------------------------------
# Pre-built FunctionTool instances
# ---------------------------------------------------------------------------

execute_code_tool = FunctionTool(execute_code)
install_package_tool = FunctionTool(install_package)


def get_code_exec_tools() -> list[FunctionTool]:
    """Return all code-execution related tools as a list."""
    return [execute_code_tool, install_package_tool]


def get_e2b_tools() -> list[FunctionTool]:
    """Return E2B sandbox tools for MCP integration.

    These tools are returned when a user enables the E2B Sandbox in their
    MCP settings. The tools allow the agent to execute code in a secure
    sandboxed environment.
    """
    return get_code_exec_tools()
