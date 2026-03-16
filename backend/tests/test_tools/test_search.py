"""Tests for Google Search grounding tool (Task 9)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.tools.search import (
    GoogleSearchAgentTool,
    GoogleSearchTool,
    get_search_tool,
    get_search_tools,
)

# ── Singleton behaviour ──────────────────────────────────────────────


class TestGetSearchTool:
    """Tests for the get_search_tool() factory."""

    def setup_method(self):
        """Reset the singleton before each test."""
        import app.tools.search as mod

        mod._search_tool = None

    def test_returns_google_search_tool_instance(self):
        tool = get_search_tool()
        assert isinstance(tool, GoogleSearchAgentTool)

    def test_singleton_returns_same_instance(self):
        tool1 = get_search_tool()
        tool2 = get_search_tool()
        assert tool1 is tool2

    def test_tool_name_is_google_search_agent(self):
        tool = get_search_tool()
        assert tool.name == "google_search_agent"


# ── get_search_tools list ────────────────────────────────────────────


class TestGetSearchTools:
    """Tests for the get_search_tools() list factory."""

    def setup_method(self):
        import app.tools.search as mod

        mod._search_tool = None

    def test_returns_list(self):
        tools = get_search_tools()
        assert isinstance(tools, list)

    def test_contains_google_search_tool(self):
        tools = get_search_tools()
        assert len(tools) >= 1
        assert isinstance(tools[0], GoogleSearchAgentTool)

    def test_list_tool_is_same_singleton(self):
        tools = get_search_tools()
        tool = get_search_tool()
        assert tools[0] is tool


# ── Tool declaration (model built-in) ────────────────────────────────


class TestGoogleSearchToolDeclaration:
    """The tool is a model built-in — it returns None for declaration."""

    def test_declaration_is_none(self):
        tool = GoogleSearchTool()
        assert tool._get_declaration() is None


# ── process_llm_request injects GoogleSearch ─────────────────────────


class TestProcessLlmRequest:
    """Verify that the tool injects GoogleSearch into the LLM config."""

    @pytest.fixture()
    def tool(self):
        return GoogleSearchTool()

    @pytest.fixture()
    def llm_request(self):
        from google.genai import types

        req = MagicMock()
        req.model = "gemini-2.5-flash-lite"
        req.config = types.GenerateContentConfig()
        req.config.tools = []
        return req

    @pytest.fixture()
    def tool_context(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_injects_google_search_for_gemini_model(self, tool, llm_request, tool_context):
        await tool.process_llm_request(tool_context=tool_context, llm_request=llm_request)
        assert len(llm_request.config.tools) == 1
        tool_decl = llm_request.config.tools[0]
        assert tool_decl.google_search is not None

    @pytest.mark.asyncio
    async def test_raises_for_unsupported_model(self, tool, tool_context):
        req = MagicMock()
        req.model = "unsupported-model-xyz"
        req.config = MagicMock()
        req.config.tools = []
        with pytest.raises(ValueError, match="not supported"):
            await tool.process_llm_request(tool_context=tool_context, llm_request=req)


# ── Agent factory integration ────────────────────────────────────────


class TestAgentFactorySearchIntegration:
    """Verify search tools are wired to the correct personas."""

    def test_researcher_gets_search_tool(self):
        from app.agents.agent_factory import _default_tools_for_persona

        tools = _default_tools_for_persona("researcher")
        assert any(isinstance(t, GoogleSearchAgentTool) for t in tools)

    def test_assistant_gets_search_tool(self):
        from app.agents.agent_factory import _default_tools_for_persona

        tools = _default_tools_for_persona("assistant")
        assert any(isinstance(t, GoogleSearchAgentTool) for t in tools)

    def test_analyst_gets_search_tool(self):
        from app.agents.agent_factory import _default_tools_for_persona

        tools = _default_tools_for_persona("analyst")
        assert any(isinstance(t, GoogleSearchAgentTool) for t in tools)

    def test_creative_does_not_get_search_tool(self):
        from app.agents.agent_factory import _default_tools_for_persona

        tools = _default_tools_for_persona("creative")
        assert not any(isinstance(t, GoogleSearchAgentTool) for t in tools)

    def test_coder_does_not_get_search_tool(self):
        from app.agents.agent_factory import _default_tools_for_persona

        tools = _default_tools_for_persona("coder")
        assert not any(isinstance(t, GoogleSearchAgentTool) for t in tools)


# ── create_agent passes tools through ────────────────────────────────


class TestCreateAgentWithSearchTools:
    """Verify create_agent() wires tools onto the Agent instance."""

    def test_researcher_agent_has_tools(self):
        from app.agents.agent_factory import create_agent
        from app.models.persona import PersonaResponse

        persona = PersonaResponse(
            id="researcher",
            user_id="system",
            name="Sage",
            voice="Kore",
            system_instruction="You are Sage.",
            mcp_ids=[],
            avatar_url="",
            is_default=True,
        )
        agent = create_agent(persona)
        assert any(isinstance(t, GoogleSearchAgentTool) for t in agent.tools)

    def test_creative_agent_has_no_tools(self):
        from app.agents.agent_factory import create_agent
        from app.models.persona import PersonaResponse

        persona = PersonaResponse(
            id="creative",
            user_id="system",
            name="Muse",
            voice="Leda",
            system_instruction="You are Muse.",
            mcp_ids=[],
            avatar_url="",
            is_default=True,
        )
        agent = create_agent(persona)
        assert not any(isinstance(t, GoogleSearchAgentTool) for t in agent.tools)


# ── Module exports ───────────────────────────────────────────────────


class TestModuleExports:
    """Verify __all__ and convenience re-exports."""

    def test_all_exports(self):
        from app.tools import search

        assert hasattr(search, "__all__")
        assert "get_search_tool" in search.__all__
        assert "get_search_tools" in search.__all__
        assert "builtin_google_search" in search.__all__

    def test_builtin_reexport(self):
        from app.tools.search import builtin_google_search

        assert builtin_google_search.name == "google_search"
