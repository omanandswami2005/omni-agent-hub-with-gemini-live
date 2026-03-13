"""Tests for omni_cli.py — local tools, slash commands, client setup."""

from __future__ import annotations

import asyncio
import json
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the cli package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import omni_cli


# ──────────────────────────────────────────────────────────────────────
# _execute_local_tool tests
# ──────────────────────────────────────────────────────────────────────


class TestReadFileTool:
    def test_read_existing_file(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("world", encoding="utf-8")
        result = omni_cli._execute_local_tool("read_file", {"path": str(f)})
        assert result["status"] == "ok"
        assert result["content"] == "world"

    def test_read_missing_file(self):
        result = omni_cli._execute_local_tool("read_file", {"path": "/nonexistent_abc123.txt"})
        assert result["status"] == "error"
        assert "not found" in result["message"].lower() or "No such file" in result["message"]

    def test_read_file_caps_at_50k(self, tmp_path):
        f = tmp_path / "big.txt"
        f.write_text("x" * 60000, encoding="utf-8")
        result = omni_cli._execute_local_tool("read_file", {"path": str(f)})
        assert result["status"] == "ok"
        assert len(result["content"]) == 50000

    def test_read_empty_path(self):
        result = omni_cli._execute_local_tool("read_file", {"path": ""})
        assert result["status"] == "error"


class TestWriteFileTool:
    def test_write_new_file(self, tmp_path):
        target = tmp_path / "output.txt"
        result = omni_cli._execute_local_tool("write_file", {
            "path": str(target),
            "content": "hello",
        })
        assert result["status"] == "ok"
        assert result["bytes_written"] == 5
        assert target.read_text(encoding="utf-8") == "hello"

    def test_write_creates_parents(self, tmp_path):
        target = tmp_path / "a" / "b" / "c.txt"
        result = omni_cli._execute_local_tool("write_file", {
            "path": str(target),
            "content": "nested",
        })
        assert result["status"] == "ok"
        assert target.exists()

    def test_write_empty_content(self, tmp_path):
        target = tmp_path / "empty.txt"
        result = omni_cli._execute_local_tool("write_file", {
            "path": str(target),
            "content": "",
        })
        assert result["status"] == "ok"
        assert result["bytes_written"] == 0
        assert target.read_text() == ""


class TestListDirectoryTool:
    def test_list_directory(self, tmp_path):
        (tmp_path / "a.txt").touch()
        (tmp_path / "b_dir").mkdir()
        result = omni_cli._execute_local_tool("list_directory", {"path": str(tmp_path)})
        assert result["status"] == "ok"
        names = {e["name"] for e in result["entries"]}
        assert "a.txt" in names
        assert "b_dir" in names
        # Check type annotations
        types = {e["name"]: e["type"] for e in result["entries"]}
        assert types["a.txt"] == "file"
        assert types["b_dir"] == "dir"

    def test_list_default_cwd(self):
        result = omni_cli._execute_local_tool("list_directory", {})
        assert result["status"] == "ok"
        assert "entries" in result

    def test_list_nonexistent_dir(self):
        result = omni_cli._execute_local_tool("list_directory", {"path": "/nonexistent_xyz_dir"})
        assert result["status"] == "error"

    def test_list_caps_at_200(self, tmp_path):
        for i in range(210):
            (tmp_path / f"file_{i:04d}.txt").touch()
        result = omni_cli._execute_local_tool("list_directory", {"path": str(tmp_path)})
        assert result["status"] == "ok"
        assert len(result["entries"]) == 200


class TestRunCommandTool:
    def test_run_echo(self):
        result = omni_cli._execute_local_tool("run_command", {"command": "echo hello"})
        assert result["status"] == "ok"
        assert "hello" in result["stdout"]
        assert result["returncode"] == 0

    def test_run_failing_command(self):
        result = omni_cli._execute_local_tool("run_command", {"command": "exit 42"})
        assert result["status"] == "ok"
        assert result["returncode"] == 42

    def test_run_command_stderr(self):
        result = omni_cli._execute_local_tool("run_command", {"command": "echo err >&2"})
        assert result["status"] == "ok"
        assert "err" in result["stderr"]


class TestUnknownTool:
    def test_unknown_tool_returns_error(self):
        result = omni_cli._execute_local_tool("no_such_tool", {})
        assert result["status"] == "error"
        assert "Unknown tool" in result["message"]


# ──────────────────────────────────────────────────────────────────────
# _handle_slash_command tests
# ──────────────────────────────────────────────────────────────────────


class TestSlashCommands:
    @pytest.fixture()
    def ws(self):
        return AsyncMock()

    @pytest.fixture()
    def session_state(self):
        return {"tools": ["google_search", "code_exec"], "other_clients": ["desktop"]}

    @pytest.mark.asyncio
    async def test_help_command(self, ws, session_state, capsys):
        result = await omni_cli._handle_slash_command(ws, "/help", session_state)
        assert result is True
        out = capsys.readouterr().out
        assert "Slash Commands" in out

    @pytest.mark.asyncio
    async def test_quit_returns_false(self, ws, session_state):
        result = await omni_cli._handle_slash_command(ws, "/quit", session_state)
        assert result is False

    @pytest.mark.asyncio
    async def test_persona_sends_message(self, ws, session_state):
        result = await omni_cli._handle_slash_command(ws, "/persona coder", session_state)
        assert result is True
        ws.send.assert_called_once()
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["type"] == "persona_switch"
        assert sent["persona_id"] == "coder"

    @pytest.mark.asyncio
    async def test_persona_missing_id(self, ws, session_state, capsys):
        result = await omni_cli._handle_slash_command(ws, "/persona", session_state)
        assert result is True
        ws.send.assert_not_called()
        out = capsys.readouterr().out
        assert "Usage" in out

    @pytest.mark.asyncio
    async def test_tools_command(self, ws, session_state, capsys):
        result = await omni_cli._handle_slash_command(ws, "/tools", session_state)
        assert result is True
        out = capsys.readouterr().out
        assert "google_search" in out
        assert "code_exec" in out

    @pytest.mark.asyncio
    async def test_tools_empty(self, ws, capsys):
        result = await omni_cli._handle_slash_command(ws, "/tools", {"tools": [], "other_clients": []})
        assert result is True
        out = capsys.readouterr().out
        assert "No tools" in out

    @pytest.mark.asyncio
    async def test_clients_command(self, ws, session_state, capsys):
        result = await omni_cli._handle_slash_command(ws, "/clients", session_state)
        assert result is True
        out = capsys.readouterr().out
        assert "desktop" in out

    @pytest.mark.asyncio
    async def test_clients_empty(self, ws, capsys):
        result = await omni_cli._handle_slash_command(ws, "/clients", {"tools": [], "other_clients": []})
        assert result is True
        out = capsys.readouterr().out
        assert "No other clients" in out

    @pytest.mark.asyncio
    async def test_mcp_toggle_on(self, ws, session_state):
        result = await omni_cli._handle_slash_command(ws, "/mcp weather on", session_state)
        assert result is True
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["type"] == "mcp_toggle"
        assert sent["mcp_id"] == "weather"
        assert sent["enabled"] is True

    @pytest.mark.asyncio
    async def test_mcp_toggle_off(self, ws, session_state):
        result = await omni_cli._handle_slash_command(ws, "/mcp weather off", session_state)
        assert result is True
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["enabled"] is False

    @pytest.mark.asyncio
    async def test_mcp_missing_args(self, ws, session_state, capsys):
        result = await omni_cli._handle_slash_command(ws, "/mcp", session_state)
        assert result is True
        ws.send.assert_not_called()
        out = capsys.readouterr().out
        assert "Usage" in out

    @pytest.mark.asyncio
    async def test_cancel_command(self, ws, session_state):
        result = await omni_cli._handle_slash_command(ws, "/cancel", session_state)
        assert result is True
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["type"] == "control"
        assert sent["action"] == "cancel"

    @pytest.mark.asyncio
    async def test_unknown_command(self, ws, session_state, capsys):
        result = await omni_cli._handle_slash_command(ws, "/foobar", session_state)
        assert result is True
        out = capsys.readouterr().out
        assert "Unknown command" in out


# ──────────────────────────────────────────────────────────────────────
# CLI metadata / constants
# ──────────────────────────────────────────────────────────────────────


class TestConstants:
    def test_local_tools_list(self):
        names = {t["name"] for t in omni_cli.CLI_LOCAL_TOOLS}
        assert names == {"read_file", "write_file", "list_directory", "run_command"}

    def test_capabilities_match_tools(self):
        tool_names = {t["name"] for t in omni_cli.CLI_LOCAL_TOOLS}
        assert set(omni_cli.CLI_CAPABILITIES) == tool_names

    def test_all_tools_have_parameters(self):
        for tool in omni_cli.CLI_LOCAL_TOOLS:
            assert "parameters" in tool
            assert tool["parameters"]["type"] == "object"
            assert "properties" in tool["parameters"]


# ──────────────────────────────────────────────────────────────────────
# parse_args tests
# ──────────────────────────────────────────────────────────────────────


class TestParseArgs:
    def test_defaults(self):
        with patch("sys.argv", ["cli", "--token", "abc"]):
            args = omni_cli.parse_args()
            assert args.server == "ws://localhost:8000"
            assert args.token == "abc"
            assert args.no_tools is False
            assert args.capabilities == ""

    def test_custom_server(self):
        with patch("sys.argv", ["cli", "--server", "ws://myhost:9000", "--token", "t"]):
            args = omni_cli.parse_args()
            assert args.server == "ws://myhost:9000"

    def test_no_tools_flag(self):
        with patch("sys.argv", ["cli", "--token", "t", "--no-tools"]):
            args = omni_cli.parse_args()
            assert args.no_tools is True

    def test_token_file(self):
        with patch("sys.argv", ["cli", "--token-file", "/tmp/tok.txt"]):
            args = omni_cli.parse_args()
            assert args.token_file == "/tmp/tok.txt"

    def test_capabilities(self):
        with patch("sys.argv", ["cli", "--token", "t", "--capabilities", "cap1,cap2"]):
            args = omni_cli.parse_args()
            assert args.capabilities == "cap1,cap2"


# ──────────────────────────────────────────────────────────────────────
# run_client auth handshake tests
# ──────────────────────────────────────────────────────────────────────


class TestRunClientAuth:
    @pytest.mark.asyncio
    async def test_auth_fail_prints_error(self, capsys):
        """If auth returns non-ok, client should print error and return."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(return_value=json.dumps({
            "type": "auth_response",
            "status": "error",
            "error": "invalid token",
        }))
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)

        with patch("omni_cli.websockets.connect", return_value=mock_ws):
            await omni_cli.run_client("ws://localhost:8000", "bad-token")

        out = capsys.readouterr().out
        assert "Auth failed" in out

    @pytest.mark.asyncio
    async def test_auth_sends_correct_payload(self):
        """Auth handshake should include correct type, client_type, tools, capabilities."""
        mock_ws = AsyncMock()
        # Return a valid auth_response, then close connection
        mock_ws.recv = AsyncMock(return_value=json.dumps({
            "type": "auth_response",
            "status": "ok",
            "user_id": "u1",
            "available_tools": [],
            "other_clients_online": [],
        }))
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)
        # Make __aiter__ raise ConnectionClosed immediately for reader
        mock_ws.__aiter__ = MagicMock(return_value=iter([]))

        with patch("omni_cli.websockets.connect", return_value=mock_ws), \
             patch("builtins.input", side_effect=EOFError):
            await omni_cli.run_client("ws://localhost:8000", "tok123", enable_tools=True)

        # First send should be auth
        auth_call = mock_ws.send.call_args_list[0]
        auth_msg = json.loads(auth_call[0][0])
        assert auth_msg["type"] == "auth"
        assert auth_msg["token"] == "tok123"
        assert auth_msg["client_type"] == "cli"
        assert "read_file" in auth_msg["capabilities"]
        assert len(auth_msg["local_tools"]) == 4

    @pytest.mark.asyncio
    async def test_no_tools_sends_empty_capabilities(self):
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(return_value=json.dumps({
            "type": "auth_response",
            "status": "ok",
            "user_id": "u1",
            "available_tools": [],
            "other_clients_online": [],
        }))
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)
        mock_ws.__aiter__ = MagicMock(return_value=iter([]))

        with patch("omni_cli.websockets.connect", return_value=mock_ws), \
             patch("builtins.input", side_effect=EOFError):
            await omni_cli.run_client("ws://localhost:8000", "tok", enable_tools=False)

        auth_msg = json.loads(mock_ws.send.call_args_list[0][0][0])
        assert auth_msg["capabilities"] == []
        assert auth_msg["local_tools"] == []


# ──────────────────────────────────────────────────────────────────────
# Color class sanity
# ──────────────────────────────────────────────────────────────────────


class TestColors:
    def test_reset_is_escape(self):
        assert omni_cli.C.RESET == "\033[0m"

    def test_all_colors_are_strings(self):
        for attr in ("GREEN", "CYAN", "YELLOW", "RED", "MAGENTA", "BLUE", "DIM", "BOLD"):
            assert isinstance(getattr(omni_cli.C, attr), str)
            assert getattr(omni_cli.C, attr).startswith("\033[")
