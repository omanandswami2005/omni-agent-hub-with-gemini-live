"""E2B sandbox service — manages sandbox lifecycle for code execution.

Provides async sandbox creation, code execution, file operations, and
cleanup using E2B's ``AsyncSandbox`` (CodeInterpreter template).

Each user session gets its own sandbox instance.  Sandboxes are pooled
in-memory and cleaned up on session end or timeout.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from e2b_code_interpreter import AsyncSandbox

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ExecutionResult:
    """Normalized result from code execution."""

    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    results: list[dict] = field(default_factory=list)
    execution_count: int = 0


class E2BService:
    """Manages E2B sandbox lifecycle and code execution.

    Sandboxes are keyed by a caller-provided identifier (typically
    ``user_id:session_id``).  The service is stateless across restarts —
    orphaned sandboxes are cleaned up by E2B's own timeout.
    """

    def __init__(self) -> None:
        self._sandboxes: dict[str, AsyncSandbox] = {}

    # ------------------------------------------------------------------
    # Sandbox lifecycle
    # ------------------------------------------------------------------

    async def create_sandbox(
        self,
        sandbox_id: str,
        *,
        timeout: int = 300,
    ) -> AsyncSandbox:
        """Create (or return existing) sandbox for *sandbox_id*."""
        if sandbox_id in self._sandboxes:
            sbx = self._sandboxes[sandbox_id]
            if await sbx.is_running():
                return sbx
            # stale entry — clean up
            del self._sandboxes[sandbox_id]

        settings = get_settings()
        sbx = await AsyncSandbox.create(
            timeout=timeout,
            api_key=settings.E2B_API_KEY,
        )
        self._sandboxes[sandbox_id] = sbx
        logger.info("sandbox_created", sandbox_id=sandbox_id)
        return sbx

    async def get_sandbox(self, sandbox_id: str) -> AsyncSandbox | None:
        """Return an existing sandbox or *None*."""
        sbx = self._sandboxes.get(sandbox_id)
        if sbx is not None and await sbx.is_running():
            return sbx
        return None

    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        """Kill and remove a sandbox.  Returns True if it existed."""
        sbx = self._sandboxes.pop(sandbox_id, None)
        if sbx is None:
            return False
        try:
            await sbx.kill()
        except Exception:
            logger.warning("sandbox_kill_failed", sandbox_id=sandbox_id, exc_info=True)
        logger.info("sandbox_destroyed", sandbox_id=sandbox_id)
        return True

    # ------------------------------------------------------------------
    # Code execution
    # ------------------------------------------------------------------

    async def execute_code(
        self,
        sandbox_id: str,
        code: str,
        *,
        language: str | None = None,
        timeout: float | None = 30.0,
    ) -> ExecutionResult:
        """Execute *code* in the sandbox identified by *sandbox_id*.

        Creates the sandbox on-demand if it does not exist yet.
        """
        sbx = await self.create_sandbox(sandbox_id)

        stdout_parts: list[str] = []
        stderr_parts: list[str] = []

        execution = await sbx.run_code(
            code,
            language=language,
            on_stdout=lambda msg: stdout_parts.append(msg.line),
            on_stderr=lambda msg: stderr_parts.append(msg.line),
            timeout=timeout,
        )

        results = []
        if execution.results:
            for r in execution.results:
                entry: dict = {}
                if r.text:
                    entry["text"] = r.text
                if r.png:
                    entry["png"] = r.png
                if r.html:
                    entry["html"] = r.html
                if r.json:
                    entry["json"] = r.json
                if r.svg:
                    entry["svg"] = r.svg
                if entry:
                    results.append(entry)

        return ExecutionResult(
            stdout="\n".join(stdout_parts),
            stderr="\n".join(stderr_parts),
            error=str(execution.error) if execution.error else None,
            results=results,
            execution_count=execution.execution_count or 0,
        )

    async def execute_command(
        self,
        sandbox_id: str,
        command: str,
        *,
        timeout: float | None = 30.0,
    ) -> ExecutionResult:
        """Run a shell command in the sandbox."""
        sbx = await self.create_sandbox(sandbox_id)
        result = await sbx.commands.run(command, timeout=timeout)

        return ExecutionResult(
            stdout=result.stdout,
            stderr=result.stderr,
            error=None if result.exit_code == 0 else f"exit code {result.exit_code}",
        )

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    async def upload_file(
        self,
        sandbox_id: str,
        path: str,
        content: bytes,
    ) -> str:
        """Upload *content* to *path* inside the sandbox."""
        sbx = await self.create_sandbox(sandbox_id)
        await sbx.files.write(path, content)
        logger.info("file_uploaded", sandbox_id=sandbox_id, path=path)
        return path

    async def download_file(
        self,
        sandbox_id: str,
        path: str,
    ) -> bytes:
        """Download a file from the sandbox."""
        sbx = await self.create_sandbox(sandbox_id)
        content = await sbx.files.read(path)
        return content

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def destroy_all(self) -> None:
        """Kill all tracked sandboxes (e.g. on server shutdown)."""
        ids = list(self._sandboxes.keys())
        for sid in ids:
            await self.destroy_sandbox(sid)
        logger.info("all_sandboxes_destroyed", count=len(ids))


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_service: E2BService | None = None


def get_e2b_service() -> E2BService:
    """Return the global E2B service instance."""
    global _service
    if _service is None:
        _service = E2BService()
    return _service
