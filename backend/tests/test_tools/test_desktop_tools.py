"""Tests for the E2B desktop ADK tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.desktop_tools import (
    desktop_bash,
    desktop_click,
    desktop_hotkey,
    desktop_launch,
    desktop_screenshot,
    desktop_type,
    get_desktop_tools,
)

_SVC = "app.tools.desktop_tools.get_e2b_desktop_service"


def _mock_svc():
    svc = MagicMock()
    svc.screenshot = AsyncMock(return_value=b"\x89PNG fake")
    svc.left_click = AsyncMock()
    svc.right_click = AsyncMock()
    svc.double_click = AsyncMock()
    svc.write_text = AsyncMock()
    svc.press_keys = AsyncMock()
    svc.launch_app = AsyncMock()
    svc.run_command = AsyncMock(return_value={"stdout": "hello", "stderr": "", "exit_code": 0})
    return svc


class TestDesktopScreenshot:
    @pytest.mark.asyncio
    @patch(_SVC)
    async def test_returns_image(self, mock_get_svc):
        svc = _mock_svc()
        mock_get_svc.return_value = svc
        result = await desktop_screenshot(user_id="u1")
        assert "image_base64" in result
        assert result["mime_type"] == "image/png"
        svc.screenshot.assert_awaited_once_with("u1")


class TestDesktopClick:
    @pytest.mark.asyncio
    @patch(_SVC)
    async def test_sends_coordinates(self, mock_get_svc):
        svc = _mock_svc()
        mock_get_svc.return_value = svc
        result = await desktop_click(x=100, y=200, user_id="u1")
        assert result["clicked"] is True
        assert result["x"] == 100 and result["y"] == 200
        svc.left_click.assert_awaited_once_with("u1", 100, 200)


class TestDesktopType:
    @pytest.mark.asyncio
    @patch(_SVC)
    async def test_sends_text(self, mock_get_svc):
        svc = _mock_svc()
        mock_get_svc.return_value = svc
        result = await desktop_type(text="hello", user_id="u1")
        assert result["typed"] is True
        svc.write_text.assert_awaited_once_with("u1", "hello")


class TestDesktopHotkey:
    @pytest.mark.asyncio
    @patch(_SVC)
    async def test_sends_key_combo(self, mock_get_svc):
        svc = _mock_svc()
        mock_get_svc.return_value = svc
        result = await desktop_hotkey(keys=["ctrl", "c"], user_id="u1")
        assert result["pressed"] is True
        svc.press_keys.assert_awaited_once_with("u1", ["ctrl", "c"])


class TestDesktopLaunch:
    @pytest.mark.asyncio
    @patch(_SVC)
    async def test_sends_app_name(self, mock_get_svc):
        svc = _mock_svc()
        mock_get_svc.return_value = svc
        result = await desktop_launch(app_name="firefox", user_id="u1")
        assert result["launched"] is True
        svc.launch_app.assert_awaited_once_with("u1", "firefox")


class TestDesktopBash:
    @pytest.mark.asyncio
    @patch(_SVC)
    async def test_runs_command(self, mock_get_svc):
        svc = _mock_svc()
        mock_get_svc.return_value = svc
        result = await desktop_bash(command="echo hi", user_id="u1")
        assert result["stdout"] == "hello"
        svc.run_command.assert_awaited_once_with("u1", "echo hi")


class TestGetDesktopTools:
    def test_returns_twenty_tools(self):
        tools = get_desktop_tools()
        assert len(tools) == 20

    def test_tool_names(self):
        tools = get_desktop_tools()
        names = {t.name for t in tools}
        assert "desktop_screenshot" in names
        assert "desktop_click" in names
        assert "desktop_bash" in names
        assert "start_desktop" in names
        assert "stop_desktop" in names
