"""Tests for AgentEngineService wrappers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.agent_engine_service import AgentEngineService


@pytest.fixture()
def svc():
    service = AgentEngineService()
    service._settings.GOOGLE_GENAI_USE_VERTEXAI = True
    service._settings.GOOGLE_CLOUD_PROJECT = "test-proj"
    service._settings.AGENT_ENGINE_NAME = "projects/p/locations/us-central1/reasoningEngines/123"
    return service


def test_get_reasoning_engine_id(svc):
    assert svc.get_reasoning_engine_id() == "123"


@pytest.mark.asyncio
async def test_retrieve_memories_similarity(svc):
    mock_item = MagicMock()
    mock_item.memory.fact = "prefers concise answers"

    mock_client = MagicMock()
    mock_client.agent_engines.memories.retrieve.return_value = [mock_item]
    svc._client = mock_client

    facts = await svc.retrieve_memories(user_id="u1", query="preferences", top_k=5)

    assert facts == ["prefers concise answers"]
    mock_client.agent_engines.memories.retrieve.assert_called_once()
    kwargs = mock_client.agent_engines.memories.retrieve.call_args.kwargs
    assert kwargs["scope"] == {"user_id": "u1"}
    assert kwargs["similarity_search_params"]["search_query"] == "preferences"


@pytest.mark.asyncio
async def test_execute_code_decodes_text_output(svc):
    output = MagicMock()
    output.mime_type = "text/plain"
    output.data = b"hello from sandbox"

    sandbox_response = MagicMock()
    sandbox_response.outputs = [output]

    op = MagicMock()
    op.response = MagicMock()
    op.response.name = "reasoningEngines/123/sandboxEnvironments/sbx1"

    mock_client = MagicMock()
    mock_client.agent_engines.sandboxes.create.return_value = op
    mock_client.agent_engines.sandboxes.execute_code.return_value = sandbox_response

    svc._client = mock_client
    result = await svc.execute_code(sandbox_key="abc", code="print('hello')")

    assert result["provider"] == "agent_engine"
    assert "hello from sandbox" in result["stdout"]
    assert result["sandbox_name"].endswith("sbx1")
