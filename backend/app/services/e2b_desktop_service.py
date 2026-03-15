"""E2B Desktop service — virtual cloud desktop with streaming, mouse, keyboard.

Wraps the ``e2b_desktop.Sandbox`` to provide:
  - Desktop lifecycle (create, destroy, status)
  - Screen streaming via VNC/WebRTC URL
  - Mouse/keyboard control
  - App launching and window management
  - Screenshot capture
  - File injection from GCS
  - Shell command execution

Each user gets at most one desktop sandbox at a time.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import StrEnum

from app.config import get_settings
from app.services.event_bus import get_event_bus
from app.utils.logging import get_logger

logger = get_logger(__name__)


class DesktopStatus(StrEnum):
    """Lifecycle states for an E2B Desktop sandbox."""

    CREATING = "creating"
    READY = "ready"
    STREAMING = "streaming"
    WORKING = "working"
    IDLE = "idle"
    DESTROYED = "destroyed"
    ERROR = "error"


@dataclass
class DesktopInfo:
    """Metadata about a running desktop sandbox."""

    user_id: str
    sandbox_id: str
    status: DesktopStatus
    stream_url: str = ""
    auth_key: str = ""
    created_at: float = 0.0


class E2BDesktopService:
    """Manages E2B Desktop sandbox lifecycle and interactions.

    One desktop per user. Desktops are kept alive until explicitly destroyed
    or the server shuts down.
    """

    def __init__(self) -> None:
        # {user_id: (Sandbox, DesktopInfo)}
        self._desktops: dict[str, tuple] = {}
        self._event_bus = get_event_bus()

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def create_desktop(
        self,
        user_id: str,
        *,
        timeout: int = 600,
    ) -> DesktopInfo:
        """Create a new E2B Desktop sandbox for a user.

        Returns immediately with DesktopInfo. If a desktop already exists,
        returns its info.
        """
        if user_id in self._desktops:
            existing = await self.get_desktop_info(user_id)
            if existing is not None:
                return existing

        from e2b_desktop import Sandbox

        settings = get_settings()
        info = DesktopInfo(
            user_id=user_id,
            sandbox_id="",
            status=DesktopStatus.CREATING,
            created_at=time.time(),
        )
        await self._publish_status(info)

        try:
            sandbox = Sandbox.create(timeout=timeout, api_key=settings.E2B_API_KEY)
            info.sandbox_id = sandbox.sandbox_id
            info.status = DesktopStatus.READY

            # Start streaming with auth
            sandbox.stream.start(require_auth=True)
            auth_key = sandbox.stream.get_auth_key()
            stream_url = sandbox.stream.get_url(auth_key=auth_key)
            info.stream_url = stream_url
            info.auth_key = auth_key
            info.status = DesktopStatus.STREAMING

            self._desktops[user_id] = (sandbox, info)
            await self._publish_status(info)
            logger.info(
                "desktop_created",
                user_id=user_id,
                sandbox_id=info.sandbox_id,
            )
            return info

        except Exception:
            info.status = DesktopStatus.ERROR
            await self._publish_status(info)
            logger.exception("desktop_creation_failed", user_id=user_id)
            raise

    async def get_desktop_info(self, user_id: str) -> DesktopInfo | None:
        """Return desktop info for a user, or None.

        Also verifies the sandbox is still alive on E2B's side. If the
        sandbox has expired, cleans up the stale entry and returns None.
        """
        entry = self._desktops.get(user_id)
        if not entry:
            return None
        sandbox, info = entry
        if info.status == DesktopStatus.DESTROYED:
            return None
        # Probe the sandbox to check it's still alive
        if not self._is_sandbox_alive(sandbox):
            logger.warning("stale_sandbox_detected", user_id=user_id, sandbox_id=info.sandbox_id)
            self._desktops.pop(user_id, None)
            info.status = DesktopStatus.DESTROYED
            await self._publish_status(info)
            return None
        return info

    async def destroy_desktop(self, user_id: str) -> bool:
        """Stop and destroy a user's desktop sandbox."""
        entry = self._desktops.pop(user_id, None)
        if not entry:
            return False

        import contextlib

        sandbox, info = entry
        with contextlib.suppress(Exception):
            sandbox.stream.stop()
        try:
            sandbox.kill()
        except Exception:
            logger.warning("desktop_kill_failed", user_id=user_id, exc_info=True)

        info.status = DesktopStatus.DESTROYED
        await self._publish_status(info)
        logger.info("desktop_destroyed", user_id=user_id)
        return True

    # ── Mouse & Keyboard ──────────────────────────────────────────────

    async def screenshot(self, user_id: str) -> bytes:
        """Take a screenshot of the desktop."""
        sandbox = self._get_sandbox(user_id)
        return sandbox.screenshot()

    async def left_click(self, user_id: str, x: int, y: int) -> None:
        sandbox = self._get_sandbox(user_id)
        sandbox.left_click(x, y)

    async def right_click(self, user_id: str, x: int, y: int) -> None:
        sandbox = self._get_sandbox(user_id)
        sandbox.right_click(x, y)

    async def double_click(self, user_id: str, x: int, y: int) -> None:
        sandbox = self._get_sandbox(user_id)
        sandbox.double_click(x, y)

    async def move_mouse(self, user_id: str, x: int, y: int) -> None:
        sandbox = self._get_sandbox(user_id)
        sandbox.move_mouse(x, y)

    async def scroll(self, user_id: str, x: int, y: int, direction: str = "down", amount: int = 3) -> None:
        sandbox = self._get_sandbox(user_id)
        sandbox.move_mouse(x, y)
        sandbox.scroll(direction=direction, amount=amount)

    async def drag(self, user_id: str, start_x: int, start_y: int, end_x: int, end_y: int) -> None:
        sandbox = self._get_sandbox(user_id)
        sandbox.drag((start_x, start_y), (end_x, end_y))

    async def write_text(self, user_id: str, text: str) -> None:
        """Type text using keyboard."""
        sandbox = self._get_sandbox(user_id)
        sandbox.write(text)

    async def press_keys(self, user_id: str, keys: list[str]) -> None:
        """Press key combination (e.g. ['ctrl', 'c'])."""
        sandbox = self._get_sandbox(user_id)
        sandbox.press(keys)

    # ── App & Window Management ───────────────────────────────────────

    async def launch_app(self, user_id: str, app_name: str) -> None:
        """Launch an application (e.g. 'google-chrome', 'firefox', 'code')."""
        sandbox = self._get_sandbox(user_id)
        sandbox.launch(app_name)

    async def open_url(self, user_id: str, url: str) -> None:
        """Open a URL in the browser."""
        sandbox = self._get_sandbox(user_id)
        sandbox.launch("google-chrome", ["--no-sandbox", url])

    async def get_windows(self, user_id: str, app_name: str = "") -> list[dict]:
        """Get list of application windows. app_name is required by the SDK."""
        sandbox = self._get_sandbox(user_id)
        if not app_name:
            raise ValueError("app_name is required to list windows")
        try:
            window_ids = sandbox.get_application_windows(app_name)
        except Exception:
            # xdotool exits 1 when no windows match
            return []
        return [{"id": wid, "app": app_name} for wid in window_ids if wid]

    # ── Shell Commands ────────────────────────────────────────────────

    async def run_command(self, user_id: str, command: str, timeout: float = 30.0) -> dict:
        """Run a shell command in the desktop sandbox."""
        sandbox = self._get_sandbox(user_id)
        result = sandbox.commands.run(command, timeout=timeout)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
        }

    # ── File Operations ───────────────────────────────────────────────

    async def upload_file(self, user_id: str, path: str, content: bytes) -> str:
        """Upload file to the desktop sandbox."""
        sandbox = self._get_sandbox(user_id)
        sandbox.files.write(path, content)
        return path

    async def download_file(self, user_id: str, path: str) -> bytes:
        """Download file from the desktop sandbox."""
        sandbox = self._get_sandbox(user_id)
        return sandbox.files.read(path, format="bytes")

    async def inject_from_gcs(self, user_id: str, gcs_path: str, sandbox_path: str) -> str:
        """Download a file from GCS and upload it to the desktop sandbox."""
        from app.services.storage_service import get_storage_service

        storage = get_storage_service()
        content = storage.download_bytes(gcs_path)
        await self.upload_file(user_id, sandbox_path, content)
        logger.info(
            "file_injected_from_gcs",
            user_id=user_id,
            gcs_path=gcs_path,
            sandbox_path=sandbox_path,
        )
        return sandbox_path

    # ── Internal ──────────────────────────────────────────────────────

    def _get_sandbox(self, user_id: str):
        """Get the sandbox instance for a user, raising if not found."""
        entry = self._desktops.get(user_id)
        if not entry:
            raise RuntimeError(f"No desktop sandbox for user {user_id}. Call create_desktop first.")
        sandbox, info = entry
        if info.status == DesktopStatus.DESTROYED:
            raise RuntimeError(f"Desktop sandbox for user {user_id} has been destroyed.")
        return sandbox

    @staticmethod
    def _is_sandbox_alive(sandbox) -> bool:
        """Check whether an E2B sandbox is still running."""
        try:
            sandbox.commands.run("echo ok", timeout=5)
            return True
        except Exception:
            return False

    async def _publish_status(self, info: DesktopInfo) -> None:
        """Publish desktop status to EventBus."""
        event = json.dumps({
            "type": "e2b_desktop_status",
            "desktop": {
                "sandbox_id": info.sandbox_id,
                "status": info.status.value,
                "stream_url": info.stream_url,
            },
            "timestamp": time.time(),
        })
        await self._event_bus.publish(info.user_id, event)

    async def destroy_all(self) -> None:
        """Destroy all active desktops (e.g. on server shutdown)."""
        user_ids = list(self._desktops.keys())
        for uid in user_ids:
            await self.destroy_desktop(uid)
        logger.info("all_desktops_destroyed", count=len(user_ids))


# ── Module singleton ──────────────────────────────────────────────────

_service: E2BDesktopService | None = None


def get_e2b_desktop_service() -> E2BDesktopService:
    global _service
    if _service is None:
        _service = E2BDesktopService()
    return _service
