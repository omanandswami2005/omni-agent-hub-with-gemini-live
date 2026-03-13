"""Tests for code execution ADK tools (Task 10)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.e2b_service import E2BService, ExecutionResult, get_e2b_service
from app.tools.code_exec import (
    execute_code,
    execute_code_tool,
    get_code_exec_tools,
    install_package,
    install_package_tool,
)

# ── Helper fixtures ──────────────────────────────────────────────────


@pytest.fixture()
def mock_service():
    """Return a mock E2BService with all async methods."""
    svc = MagicMock(spec=E2BService)
    svc.execute_code = AsyncMock(
        return_value=ExecutionResult(
            stdout="hello",
            stderr="",
            error=None,
            results=[{"text": "42"}],
            execution_count=1,
        )
    )
    svc.execute_command = AsyncMock(
        return_value=ExecutionResult(
            stdout="Successfully installed pandas",
            stderr="",
            error=None,
        )
    )
    return svc


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the e2b_service singleton between tests."""
    import app.services.e2b_service as mod

    old = mod._service
    mod._service = None
    yield
    mod._service = old


@pytest.fixture(autouse=True)
def _disable_agent_engine_in_tool_tests():
    """Default these tests to the E2B fallback path unless overridden."""
    ae = MagicMock()
    ae.enabled = False
    with patch("app.tools.code_exec.get_agent_engine_service", return_value=ae):
        yield


# ── execute_code tool ────────────────────────────────────────────────


class TestExecuteCode:
    """Tests for the execute_code function."""

    @pytest.mark.asyncio
    async def test_returns_stdout(self, mock_service):
        with patch("app.tools.code_exec.get_e2b_service", return_value=mock_service):
            result = await execute_code("print('hello')")
        assert result["stdout"] == "hello"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_passes_language(self, mock_service):
        with patch("app.tools.code_exec.get_e2b_service", return_value=mock_service):
            await execute_code("console.log(1)", language="javascript")
        mock_service.execute_code.assert_awaited_once()
        _, kwargs = mock_service.execute_code.call_args
        assert kwargs["language"] == "javascript"

    @pytest.mark.asyncio
    async def test_passes_sandbox_id(self, mock_service):
        with patch("app.tools.code_exec.get_e2b_service", return_value=mock_service):
            await execute_code("1+1", sandbox_id="user1:sess1")
        args, _ = mock_service.execute_code.call_args
        assert args[0] == "user1:sess1"

    @pytest.mark.asyncio
    async def test_returns_results(self, mock_service):
        with patch("app.tools.code_exec.get_e2b_service", return_value=mock_service):
            result = await execute_code("42")
        assert result["results"] == [{"text": "42"}]

    @pytest.mark.asyncio
    async def test_returns_error(self, mock_service):
        mock_service.execute_code.return_value = ExecutionResult(
            stdout="",
            stderr="traceback",
            error="NameError: name 'x' is not defined",
        )
        with patch("app.tools.code_exec.get_e2b_service", return_value=mock_service):
            result = await execute_code("x")
        assert result["error"] == "NameError: name 'x' is not defined"
        assert result["stderr"] == "traceback"

    @pytest.mark.asyncio
    async def test_default_sandbox_id(self, mock_service):
        with patch("app.tools.code_exec.get_e2b_service", return_value=mock_service):
            await execute_code("1")
        args, _ = mock_service.execute_code.call_args
        assert args[0] == "default"

    @pytest.mark.asyncio
    async def test_uses_agent_engine_when_enabled(self):
        ae = MagicMock()
        ae.enabled = True
        ae.execute_code = AsyncMock(
            return_value={
                "stdout": "from-agent-engine",
                "stderr": "",
                "error": None,
                "results": [],
                "provider": "agent_engine",
            }
        )
        with patch("app.tools.code_exec.get_agent_engine_service", return_value=ae):
            result = await execute_code("print('x')", sandbox_id="s1")
        assert result["provider"] == "agent_engine"
        ae.execute_code.assert_awaited_once_with(sandbox_key="s1", code="print('x')")


# ── install_package tool ─────────────────────────────────────────────


class TestInstallPackage:
    """Tests for the install_package function."""

    @pytest.mark.asyncio
    async def test_installs_with_pip(self, mock_service):
        with patch("app.tools.code_exec.get_e2b_service", return_value=mock_service):
            result = await install_package("pandas")
        mock_service.execute_command.assert_awaited_once()
        args, _ = mock_service.execute_command.call_args
        assert "pip install -q pandas" in args[1]
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_returns_stdout(self, mock_service):
        with patch("app.tools.code_exec.get_e2b_service", return_value=mock_service):
            result = await install_package("numpy")
        assert "Successfully installed" in result["stdout"]

    @pytest.mark.asyncio
    async def test_returns_error_on_failure(self, mock_service):
        mock_service.execute_command.return_value = ExecutionResult(
            stdout="",
            stderr="ERROR: No matching distribution",
            error="exit code 1",
        )
        with patch("app.tools.code_exec.get_e2b_service", return_value=mock_service):
            result = await install_package("nonexistent-pkg-xyz")
        assert result["error"] == "exit code 1"

    @pytest.mark.asyncio
    async def test_passes_sandbox_id(self, mock_service):
        with patch("app.tools.code_exec.get_e2b_service", return_value=mock_service):
            await install_package("requests", sandbox_id="u:s")
        args, _ = mock_service.execute_command.call_args
        assert args[0] == "u:s"

    @pytest.mark.asyncio
    async def test_install_package_uses_agent_engine_when_enabled(self):
        ae = MagicMock()
        ae.enabled = True
        ae.install_package = AsyncMock(
            return_value={"stdout": "ok", "stderr": "", "error": None, "provider": "agent_engine"}
        )
        with patch("app.tools.code_exec.get_agent_engine_service", return_value=ae):
            result = await install_package("pandas", sandbox_id="s2")
        assert result["provider"] == "agent_engine"
        ae.install_package.assert_awaited_once_with(sandbox_key="s2", package="pandas")


# ── FunctionTool instances ───────────────────────────────────────────


class TestFunctionTools:
    """Tests for the pre-built FunctionTool instances."""

    def test_execute_code_tool_exists(self):
        assert execute_code_tool is not None
        assert execute_code_tool.name == "execute_code"

    def test_install_package_tool_exists(self):
        assert install_package_tool is not None
        assert install_package_tool.name == "install_package"

    def test_get_code_exec_tools_returns_list(self):
        tools = get_code_exec_tools()
        assert isinstance(tools, list)
        assert len(tools) == 2

    def test_get_code_exec_tools_contains_both(self):
        tools = get_code_exec_tools()
        names = {t.name for t in tools}
        assert "execute_code" in names
        assert "install_package" in names


# ── E2BService unit tests ───────────────────────────────────────────


class TestE2BService:
    """Unit tests for E2BService (mocked AsyncSandbox)."""

    def test_singleton_returns_same_instance(self):
        svc1 = get_e2b_service()
        svc2 = get_e2b_service()
        assert svc1 is svc2

    def test_starts_with_no_sandboxes(self):
        svc = E2BService()
        assert len(svc._sandboxes) == 0

    @pytest.mark.asyncio
    async def test_create_sandbox_calls_api(self):
        svc = E2BService()
        mock_sbx = AsyncMock()
        mock_sbx.is_running = AsyncMock(return_value=True)

        with patch("app.services.e2b_service.AsyncSandbox") as MockSandbox:
            MockSandbox.create = AsyncMock(return_value=mock_sbx)
            sbx = await svc.create_sandbox("test-id")

        assert sbx is mock_sbx
        assert "test-id" in svc._sandboxes

    @pytest.mark.asyncio
    async def test_create_sandbox_returns_existing(self):
        svc = E2BService()
        mock_sbx = AsyncMock()
        mock_sbx.is_running = AsyncMock(return_value=True)
        svc._sandboxes["test-id"] = mock_sbx

        # Should return existing without calling create
        sbx = await svc.create_sandbox("test-id")
        assert sbx is mock_sbx

    @pytest.mark.asyncio
    async def test_destroy_sandbox(self):
        svc = E2BService()
        mock_sbx = AsyncMock()
        svc._sandboxes["test-id"] = mock_sbx

        result = await svc.destroy_sandbox("test-id")
        assert result is True
        assert "test-id" not in svc._sandboxes
        mock_sbx.kill.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_destroy_nonexistent_sandbox(self):
        svc = E2BService()
        result = await svc.destroy_sandbox("nope")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_sandbox_running(self):
        svc = E2BService()
        mock_sbx = AsyncMock()
        mock_sbx.is_running = AsyncMock(return_value=True)
        svc._sandboxes["test"] = mock_sbx

        sbx = await svc.get_sandbox("test")
        assert sbx is mock_sbx

    @pytest.mark.asyncio
    async def test_get_sandbox_not_running(self):
        svc = E2BService()
        mock_sbx = AsyncMock()
        mock_sbx.is_running = AsyncMock(return_value=False)
        svc._sandboxes["test"] = mock_sbx

        sbx = await svc.get_sandbox("test")
        assert sbx is None


# ── Agent factory integration ────────────────────────────────────────


class TestAgentFactoryIntegration:
    """Verify code_exec tools are wired to correct personas."""

    def test_coder_gets_code_exec_tools(self):
        from app.agents.agent_factory import _CODE_EXEC_PERSONA_IDS

        assert "coder" in _CODE_EXEC_PERSONA_IDS

    def test_analyst_gets_code_exec_tools(self):
        from app.agents.agent_factory import _CODE_EXEC_PERSONA_IDS

        assert "analyst" in _CODE_EXEC_PERSONA_IDS

    def test_assistant_no_code_exec(self):
        from app.agents.agent_factory import _CODE_EXEC_PERSONA_IDS

        assert "assistant" not in _CODE_EXEC_PERSONA_IDS

    def test_creative_no_code_exec(self):
        from app.agents.agent_factory import _CODE_EXEC_PERSONA_IDS

        assert "creative" not in _CODE_EXEC_PERSONA_IDS

    def test_default_tools_include_code_exec_for_coder(self):
        from app.agents.agent_factory import _default_tools_for_persona

        tools = _default_tools_for_persona("coder")
        names = {t.name for t in tools}
        assert "execute_code" in names
        assert "install_package" in names

    def test_default_tools_include_both_for_analyst(self):
        from app.agents.agent_factory import _default_tools_for_persona

        tools = _default_tools_for_persona("analyst")
        names = {t.name for t in tools}
        # analyst gets search + code exec
        assert "google_search_agent" in names
        assert "execute_code" in names
