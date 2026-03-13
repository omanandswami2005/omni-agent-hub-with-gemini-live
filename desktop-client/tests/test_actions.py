"""Tests for desktop actions, file ops, screen capture, and WS client."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# actions.py tests
# ---------------------------------------------------------------------------


class TestClick:
    @patch("src.actions.pyautogui")
    def test_click_at_coordinates(self, mock_pag):
        from src.actions import click

        result = click(100, 200)
        mock_pag.click.assert_called_once_with(100, 200, button="left")
        assert result == {"ok": True, "x": 100, "y": 200, "button": "left"}

    @patch("src.actions.pyautogui")
    def test_click_right_button(self, mock_pag):
        from src.actions import click

        result = click(50, 75, button="right")
        mock_pag.click.assert_called_once_with(50, 75, button="right")
        assert result["button"] == "right"

    @patch("src.actions.pyautogui")
    def test_double_click(self, mock_pag):
        from src.actions import double_click

        result = double_click(300, 400)
        mock_pag.doubleClick.assert_called_once_with(300, 400)
        assert result == {"ok": True, "x": 300, "y": 400}


class TestTypeText:
    @patch("src.actions.pyautogui")
    def test_type_text(self, mock_pag):
        from src.actions import type_text

        result = type_text("hello world")
        mock_pag.typewrite.assert_called_once_with("hello world", interval=0.02)
        assert result == {"ok": True, "length": 11}

    @patch("src.actions.pyautogui")
    def test_type_text_custom_interval(self, mock_pag):
        from src.actions import type_text

        result = type_text("abc", interval=0.05)
        mock_pag.typewrite.assert_called_once_with("abc", interval=0.05)
        assert result["length"] == 3


class TestHotkey:
    @patch("src.actions.pyautogui")
    def test_hotkey_combo(self, mock_pag):
        from src.actions import hotkey

        result = hotkey("ctrl", "c")
        mock_pag.hotkey.assert_called_once_with("ctrl", "c")
        assert result == {"ok": True, "keys": ["ctrl", "c"]}


class TestMouseMovement:
    @patch("src.actions.pyautogui")
    def test_move_mouse(self, mock_pag):
        from src.actions import move_mouse

        result = move_mouse(500, 600)
        mock_pag.moveTo.assert_called_once_with(500, 600)
        assert result == {"ok": True, "x": 500, "y": 600}

    @patch("src.actions.pyautogui")
    def test_scroll(self, mock_pag):
        from src.actions import scroll

        result = scroll(3)
        mock_pag.scroll.assert_called_once_with(3)
        assert result == {"ok": True, "amount": 3}

    @patch("src.actions.pyautogui")
    def test_scroll_at_position(self, mock_pag):
        from src.actions import scroll

        result = scroll(-5, x=100, y=200)
        mock_pag.scroll.assert_called_once_with(-5, 100, 200)
        assert result["amount"] == -5

    @patch("src.actions.pyautogui")
    def test_get_mouse_position(self, mock_pag):
        from src.actions import get_mouse_position

        mock_pag.position.return_value = MagicMock(x=123, y=456)
        result = get_mouse_position()
        assert result == {"x": 123, "y": 456}

    @patch("src.actions.pyautogui")
    def test_get_screen_size(self, mock_pag):
        from src.actions import get_screen_size

        mock_pag.size.return_value = (1920, 1080)
        result = get_screen_size()
        assert result == {"width": 1920, "height": 1080}


class TestOpenApplication:
    @patch("src.actions.subprocess")
    @patch("src.actions.sys")
    def test_open_app_windows(self, mock_sys, mock_sub):
        mock_sys.platform = "win32"
        from src.actions import open_application

        with patch("src.actions.time"):
            result = open_application("notepad")
        assert result["ok"] is True
        assert result["app"] == "notepad"


# ---------------------------------------------------------------------------
# files.py tests
# ---------------------------------------------------------------------------


class TestFileOps:
    def test_list_directory(self, tmp_path):
        from src.files import list_directory, set_allowed_directories

        (tmp_path / "file.txt").write_text("hello")
        (tmp_path / "subdir").mkdir()

        set_allowed_directories([str(tmp_path)])
        result = list_directory(str(tmp_path))
        assert isinstance(result, list)
        names = {e["name"] for e in result}
        assert "file.txt" in names
        assert "subdir" in names

    def test_read_file(self, tmp_path):
        from src.files import read_file, set_allowed_directories

        f = tmp_path / "test.txt"
        f.write_text("content here")
        set_allowed_directories([str(tmp_path)])
        result = read_file(str(f))
        assert result == "content here"

    def test_read_file_denied(self, tmp_path):
        from src.files import read_file, set_allowed_directories

        f = tmp_path / "test.txt"
        f.write_text("secret")
        set_allowed_directories([str(tmp_path / "other")])
        result = read_file(str(f))
        assert isinstance(result, dict)
        assert "error" in result

    def test_write_file(self, tmp_path):
        from src.files import set_allowed_directories, write_file

        set_allowed_directories([str(tmp_path)])
        dest = tmp_path / "output.txt"
        result = write_file(str(dest), "written content")
        assert result["ok"] is True
        assert dest.read_text() == "written content"

    def test_write_file_creates_parents(self, tmp_path):
        from src.files import set_allowed_directories, write_file

        set_allowed_directories([str(tmp_path)])
        dest = tmp_path / "a" / "b" / "deep.txt"
        result = write_file(str(dest), "deep")
        assert result["ok"] is True
        assert dest.read_text() == "deep"

    def test_file_info(self, tmp_path):
        from src.files import file_info, set_allowed_directories

        f = tmp_path / "info.txt"
        f.write_text("data")
        set_allowed_directories([str(tmp_path)])
        result = file_info(str(f))
        assert result["name"] == "info.txt"
        assert result["size"] == 4
        assert result["is_dir"] is False
        assert "modified" in result


# ---------------------------------------------------------------------------
# screen.py tests
# ---------------------------------------------------------------------------


class TestScreenCapture:
    @patch("src.screen.mss.mss")
    def test_capture_screen_returns_jpeg(self, mock_mss_cls):
        """capture_screen should return JPEG bytes."""
        from src.screen import capture_screen

        # Build a fake screenshot: 100x100 BGRA
        width, height = 100, 100
        raw_data = bytes([0, 128, 255, 255] * width * height)  # BGRA

        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 200, "height": 200},  # all
            {"left": 0, "top": 0, "width": width, "height": height},  # primary
        ]
        mock_grab = MagicMock()
        mock_grab.size = (width, height)
        mock_grab.bgra = raw_data
        mock_sct.grab.return_value = mock_grab
        mock_mss_cls.return_value.__enter__ = MagicMock(return_value=mock_sct)
        mock_mss_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = capture_screen(quality=50)
        assert isinstance(result, bytes)
        # JPEG files start with FFD8
        assert result[:2] == b"\xff\xd8"

    @patch("src.screen.mss.mss")
    def test_get_screen_info(self, mock_mss_cls):
        from src.screen import get_screen_info

        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 3840, "height": 1080},
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
            {"left": 1920, "top": 0, "width": 1920, "height": 1080},
        ]
        mock_mss_cls.return_value.__enter__ = MagicMock(return_value=mock_sct)
        mock_mss_cls.return_value.__exit__ = MagicMock(return_value=False)

        info = get_screen_info()
        assert info["primary"]["width"] == 1920
        assert len(info["monitors"]) == 3


# ---------------------------------------------------------------------------
# ws_client.py tests
# ---------------------------------------------------------------------------


class TestWSClient:
    def test_register_handler(self):
        from src.ws_client import DesktopWSClient

        client = DesktopWSClient("ws://localhost:8080/ws/live", "test-token")
        handler = AsyncMock()
        client.register_handler("click", handler)
        assert "click" in client._handlers

    @pytest.mark.asyncio
    async def test_dispatch_calls_handler(self):
        from src.ws_client import DesktopWSClient

        client = DesktopWSClient("ws://localhost:8080/ws/live", "test-token")
        client.ws = AsyncMock()
        client.connected = True

        handler = AsyncMock(return_value={"ok": True})
        client.register_handler("click", handler)

        msg = {
            "type": "cross_client",
            "action": "click",
            "data": {"x": 100, "y": 200},
        }
        await client._dispatch(msg)
        handler.assert_called_once_with(x=100, y=200)

    @pytest.mark.asyncio
    async def test_dispatch_unknown_action_sends_error(self):
        from src.ws_client import DesktopWSClient

        client = DesktopWSClient("ws://localhost:8080/ws/live", "test-token")
        client.ws = AsyncMock()
        client.connected = True

        msg = {
            "type": "cross_client",
            "action": "nonexistent",
            "data": {},
        }
        await client._dispatch(msg)
        # Should have sent error response
        client.ws.send.assert_called_once()
        sent = json.loads(client.ws.send.call_args[0][0])
        assert sent["type"] == "action_response"
        assert "error" in sent["result"]

    @pytest.mark.asyncio
    async def test_ping_pong(self):
        from src.ws_client import DesktopWSClient

        client = DesktopWSClient("ws://localhost:8080/ws/live", "test-token")
        client.ws = AsyncMock()
        client.connected = True

        await client._dispatch({"type": "ping"})
        client.ws.send.assert_called_once()
        sent = json.loads(client.ws.send.call_args[0][0])
        assert sent["type"] == "pong"

    @pytest.mark.asyncio
    async def test_disconnect(self):
        from src.ws_client import DesktopWSClient

        client = DesktopWSClient("ws://localhost:8080/ws/live", "test-token")
        client.ws = AsyncMock()
        client.connected = True
        client._should_run = True

        await client.disconnect()
        assert client.connected is False
        assert client._should_run is False
        assert client.ws is None


# ---------------------------------------------------------------------------
# config.py tests
# ---------------------------------------------------------------------------


class TestConfig:
    def test_default_config(self):
        from src.config import DesktopConfig

        cfg = DesktopConfig()
        assert cfg.server_url == "ws://localhost:8000/ws/live"
        assert cfg.capture_quality == 75
        assert cfg.log_level == "INFO"


# ---------------------------------------------------------------------------
# ws_client interruption / cancellation tests
# ---------------------------------------------------------------------------


class TestWSClientInterruptions:
    @pytest.mark.asyncio
    async def test_cancel_call_cancels_task(self):
        from src.ws_client import DesktopWSClient

        client = DesktopWSClient("ws://localhost:8080/ws/live", "test-token")
        client.ws = AsyncMock()
        client.connected = True

        import asyncio

        async def slow():
            await asyncio.sleep(100)

        task = asyncio.create_task(slow())
        client._active_tasks["abc-123"] = task

        await client.cancel_call("abc-123")
        # Yield to let cancellation propagate
        await asyncio.sleep(0)
        assert task.cancelled()
        assert "abc-123" not in client._active_tasks

    @pytest.mark.asyncio
    async def test_cancel_all_clears_all_tasks(self):
        from src.ws_client import DesktopWSClient

        client = DesktopWSClient("ws://localhost:8080/ws/live", "test-token")
        client.ws = AsyncMock()
        client.connected = True

        import asyncio

        async def slow():
            await asyncio.sleep(100)

        t1 = asyncio.create_task(slow())
        t2 = asyncio.create_task(slow())
        client._active_tasks["c1"] = t1
        client._active_tasks["c2"] = t2

        await client.cancel_all()
        await asyncio.sleep(0)
        assert len(client._active_tasks) == 0
        assert t1.cancelled()
        assert t2.cancelled()

    @pytest.mark.asyncio
    async def test_dispatch_cancel_message(self):
        from src.ws_client import DesktopWSClient

        client = DesktopWSClient("ws://localhost:8080/ws/live", "test-token")
        client.ws = AsyncMock()
        client.connected = True

        import asyncio

        async def slow():
            await asyncio.sleep(100)

        task = asyncio.create_task(slow())
        client._active_tasks["cancel-me"] = task

        await client._dispatch({"type": "cancel", "call_id": "cancel-me"})
        await asyncio.sleep(0)
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_dispatch_cancel_all_message(self):
        from src.ws_client import DesktopWSClient

        client = DesktopWSClient("ws://localhost:8080/ws/live", "test-token")
        client.ws = AsyncMock()
        client.connected = True

        import asyncio

        async def slow():
            await asyncio.sleep(100)

        task = asyncio.create_task(slow())
        client._active_tasks["t1"] = task

        await client._dispatch({"type": "cancel_all"})
        await asyncio.sleep(0)
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_dispatch_status_interrupted(self):
        from src.ws_client import DesktopWSClient

        client = DesktopWSClient("ws://localhost:8080/ws/live", "test-token")
        client.ws = AsyncMock()
        client.connected = True

        import asyncio

        async def slow():
            await asyncio.sleep(100)

        task = asyncio.create_task(slow())
        client._active_tasks["t1"] = task

        await client._dispatch({
            "type": "status",
            "state": "listening",
            "detail": "Interrupted by user",
        })
        await asyncio.sleep(0)
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_tool_invocation_creates_tracked_task(self):
        from src.ws_client import DesktopWSClient

        client = DesktopWSClient("ws://localhost:8080/ws/live", "test-token")
        client.ws = AsyncMock()
        client.connected = True

        handler = AsyncMock(return_value={"ok": True})
        client.register_handler("test_tool", handler)

        await client._dispatch({
            "type": "tool_invocation",
            "call_id": "call-1",
            "tool": "test_tool",
            "args": {"x": 1},
        })

        import asyncio
        await asyncio.sleep(0.05)
        handler.assert_called_once_with(x=1)
