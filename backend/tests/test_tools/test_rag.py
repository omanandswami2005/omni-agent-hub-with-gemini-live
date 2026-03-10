"""Tests for RAG Engine tools (Task 14)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.rag import (
    get_rag_tools,
    search_documents,
    search_documents_tool,
    upload_document,
    upload_document_tool,
)

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset RAG module state between tests."""
    import app.tools.rag as mod

    old_client = mod._genai_client
    old_corpora = mod._user_corpora.copy()
    mod._genai_client = None
    mod._user_corpora.clear()
    yield
    mod._genai_client = old_client
    mod._user_corpora = old_corpora


@pytest.fixture()
def mock_client():
    """Return a mock genai client with async model methods for search."""
    client = MagicMock()
    # aio.models.generate_content (for search)
    candidate = MagicMock()
    candidate.content.parts = [MagicMock(text="The answer is 42.")]
    candidate.grounding_metadata = None
    response = MagicMock()
    response.candidates = [candidate]
    client.aio.models.generate_content = AsyncMock(return_value=response)
    return client


# ── upload_document ──────────────────────────────────────────────────


class TestUploadDocument:
    @pytest.mark.asyncio
    async def test_creates_corpus_and_imports(self):
        with (
            patch(
                "app.tools.rag._create_corpus_rest",
                new_callable=AsyncMock,
                return_value="corpora/abc123",
            ) as mock_create,
            patch(
                "app.tools.rag._import_file_rest",
                new_callable=AsyncMock,
            ) as mock_import,
        ):
            result = await upload_document("gs://bucket/doc.pdf", user_id="u1")
        assert result["status"] == "imported"
        assert result["corpus_name"] == "corpora/abc123"
        mock_create.assert_awaited_once()
        mock_import.assert_awaited_once_with("corpora/abc123", "gs://bucket/doc.pdf")

    @pytest.mark.asyncio
    async def test_reuses_existing_corpus(self):
        import app.tools.rag as mod

        mod._user_corpora["u1"] = "corpora/existing"
        with (
            patch(
                "app.tools.rag._create_corpus_rest",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "app.tools.rag._import_file_rest",
                new_callable=AsyncMock,
            ),
        ):
            result = await upload_document("gs://bucket/doc2.pdf", user_id="u1")
        assert result["corpus_name"] == "corpora/existing"
        mock_create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_passes_gcs_uri_to_import(self):
        with (
            patch(
                "app.tools.rag._create_corpus_rest",
                new_callable=AsyncMock,
                return_value="corpora/new",
            ),
            patch(
                "app.tools.rag._import_file_rest",
                new_callable=AsyncMock,
            ) as mock_import,
        ):
            await upload_document("gs://bucket/report.pdf", user_id="u2")
        mock_import.assert_awaited_once_with("corpora/new", "gs://bucket/report.pdf")

    @pytest.mark.asyncio
    async def test_custom_corpus_name(self):
        with (
            patch(
                "app.tools.rag._create_corpus_rest",
                new_callable=AsyncMock,
                return_value="corpora/custom",
            ) as mock_create,
            patch(
                "app.tools.rag._import_file_rest",
                new_callable=AsyncMock,
            ),
        ):
            await upload_document(
                "gs://b/f.pdf", user_id="u3", corpus_display_name="My Docs"
            )
        mock_create.assert_awaited_once_with("My Docs")


# ── search_documents ─────────────────────────────────────────────────


class TestSearchDocuments:
    @pytest.mark.asyncio
    async def test_no_corpus_returns_empty(self):
        result = await search_documents("what is X?", user_id="nobody")
        assert result["chunks"] == []
        assert "No documents" in result["answer"]

    @pytest.mark.asyncio
    async def test_returns_answer(self, mock_client):
        import app.tools.rag as mod

        mod._user_corpora["u1"] = "corpora/abc123"
        with patch("app.tools.rag._get_client", return_value=mock_client):
            result = await search_documents("what is the answer?", user_id="u1")
        assert "42" in result["answer"]

    @pytest.mark.asyncio
    async def test_passes_corpus_to_retrieval(self, mock_client):
        import app.tools.rag as mod

        mod._user_corpora["u1"] = "corpora/test-corpus"
        with patch("app.tools.rag._get_client", return_value=mock_client):
            await search_documents("query", user_id="u1")
        call_kwargs = mock_client.aio.models.generate_content.call_args[1]
        config = call_kwargs["config"]
        rag_resource = config.tools[0].retrieval.vertex_rag_store.rag_resources[0]
        assert rag_resource.rag_corpus == "corpora/test-corpus"

    @pytest.mark.asyncio
    async def test_extracts_grounding_chunks(self, mock_client):
        import app.tools.rag as mod

        mod._user_corpora["u1"] = "corpora/abc123"

        # Set up grounding metadata
        chunk = MagicMock()
        chunk.retrieved_context = MagicMock()
        chunk.retrieved_context.uri = "gs://bucket/doc.pdf"
        chunk.retrieved_context.title = "Report"
        chunk.web = None
        candidate = mock_client.aio.models.generate_content.return_value.candidates[0]
        candidate.grounding_metadata = MagicMock()
        candidate.grounding_metadata.grounding_chunks = [chunk]

        with patch("app.tools.rag._get_client", return_value=mock_client):
            result = await search_documents("find info", user_id="u1")
        assert len(result["chunks"]) == 1
        assert result["chunks"][0]["uri"] == "gs://bucket/doc.pdf"


# ── FunctionTool instances ───────────────────────────────────────────


class TestFunctionToolInstances:
    def test_upload_document_tool(self):
        assert upload_document_tool.name == "upload_document"

    def test_search_documents_tool(self):
        assert search_documents_tool.name == "search_documents"

    def test_get_rag_tools(self):
        tools = get_rag_tools()
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert "upload_document" in names
        assert "search_documents" in names


# ── Agent factory integration ────────────────────────────────────────


class TestAgentFactoryIntegration:
    def test_researcher_gets_rag(self):
        from app.agents.agent_factory import _RAG_PERSONA_IDS

        assert "researcher" in _RAG_PERSONA_IDS

    def test_analyst_gets_rag(self):
        from app.agents.agent_factory import _RAG_PERSONA_IDS

        assert "analyst" in _RAG_PERSONA_IDS

    def test_coder_no_rag(self):
        from app.agents.agent_factory import _RAG_PERSONA_IDS

        assert "coder" not in _RAG_PERSONA_IDS

    def test_researcher_tools_include_search_documents(self):
        from app.agents.agent_factory import _default_tools_for_persona

        tools = _default_tools_for_persona("researcher")
        names = {t.name for t in tools}
        assert "search_documents" in names
        assert "upload_document" in names
