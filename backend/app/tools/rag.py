"""RAG Engine ADK tools — document upload, indexing, and retrieval.

Uses Vertex AI RAG Engine via REST API for corpus management and the
``google.genai`` SDK for grounded generation against those corpora.
"""

from __future__ import annotations

import google.auth
import google.auth.transport.requests
from google import genai
from google.adk.tools import FunctionTool
from google.genai import types
from httpx import AsyncClient

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Lazy clients
# ---------------------------------------------------------------------------

_genai_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _genai_client
    if _genai_client is None:
        settings = get_settings()
        _genai_client = genai.Client(
            vertexai=settings.GOOGLE_GENAI_USE_VERTEXAI,
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        )
    return _genai_client


def _get_access_token() -> str:
    """Return a fresh access token from ADC."""
    credentials, _ = google.auth.default()
    credentials.refresh(google.auth.transport.requests.Request())
    return credentials.token


# In-memory mapping of user_id → corpus resource name
_user_corpora: dict[str, str] = {}

RAG_MODEL = "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# Vertex AI RAG Engine REST helpers
# ---------------------------------------------------------------------------

def _rag_base_url() -> str:
    settings = get_settings()
    return (
        f"https://{settings.GOOGLE_CLOUD_LOCATION}-aiplatform.googleapis.com/v1"
        f"/projects/{settings.GOOGLE_CLOUD_PROJECT}"
        f"/locations/{settings.GOOGLE_CLOUD_LOCATION}"
    )


async def _create_corpus_rest(display_name: str) -> str:
    """Create a RAG corpus via REST API, return its resource name."""
    url = f"{_rag_base_url()}/ragCorpora"
    token = _get_access_token()
    async with AsyncClient() as http:
        resp = await http.post(
            url,
            json={"display_name": display_name},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
    # Long-running operation — extract corpus name from metadata or response
    name = data.get("name", "")
    # If it's an LRO, the corpus name is in metadata.resource
    if "metadata" in data:
        name = data["metadata"].get("resource", name)
    return name


async def _import_file_rest(corpus_name: str, gcs_uri: str) -> None:
    """Import a GCS file into a RAG corpus via REST API."""
    url = f"{_rag_base_url()}/ragCorpora/{corpus_name.split('/')[-1]}/ragFiles:import"
    token = _get_access_token()
    async with AsyncClient() as http:
        resp = await http.post(
            url,
            json={
                "import_rag_files_config": {
                    "gcs_source": {"uris": [gcs_uri]},
                },
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=60.0,
        )
        resp.raise_for_status()


# ---------------------------------------------------------------------------
# Tool: upload_document
# ---------------------------------------------------------------------------


async def upload_document(
    file_gcs_uri: str,
    user_id: str = "default",
    corpus_display_name: str | None = None,
) -> dict:
    """Upload a document to the user's RAG corpus for later retrieval.

    The file must already be in GCS (use storage service to upload first).

    Args:
        file_gcs_uri: GCS URI of the document (``gs://bucket/path``).
        user_id: Owner of the corpus.
        corpus_display_name: Human-readable name for a new corpus.

    Returns:
        A dict with ``corpus_name`` and ``status``.
    """
    corpus_name = await _ensure_corpus(user_id, corpus_display_name)

    await _import_file_rest(corpus_name, file_gcs_uri)

    logger.info(
        "document_uploaded",
        user_id=user_id,
        corpus=corpus_name,
        gcs_uri=file_gcs_uri,
    )
    return {
        "corpus_name": corpus_name,
        "file": file_gcs_uri,
        "status": "imported",
    }


# ---------------------------------------------------------------------------
# Tool: search_documents
# ---------------------------------------------------------------------------


async def search_documents(
    query: str,
    user_id: str = "default",
) -> dict:
    """Search the user's uploaded documents using semantic retrieval.

    Args:
        query: Natural-language search query.
        user_id: Owner of the RAG corpus to search.

    Returns:
        A dict with ``chunks`` (relevant passages) and ``answer``.
    """
    corpus_name = _user_corpora.get(user_id)
    if not corpus_name:
        return {"chunks": [], "answer": "No documents uploaded yet."}

    client = _get_client()

    # Use Gemini with Vertex RAG Store retrieval for grounded answers
    response = await client.aio.models.generate_content(
        model=RAG_MODEL,
        contents=query,
        config=types.GenerateContentConfig(
            tools=[
                types.Tool(
                    retrieval=types.Retrieval(
                        vertex_rag_store=types.VertexRagStore(
                            rag_resources=[
                                types.VertexRagStoreRagResource(
                                    rag_corpus=corpus_name,
                                ),
                            ],
                        ),
                    ),
                ),
            ],
        ),
    )

    answer = ""
    chunks: list[dict] = []

    if response.candidates:
        candidate = response.candidates[0]
        if candidate.content and candidate.content.parts:
            answer = "".join(p.text for p in candidate.content.parts if p.text)
        # Extract grounding metadata if available
        if candidate.grounding_metadata and candidate.grounding_metadata.grounding_chunks:
            for chunk in candidate.grounding_metadata.grounding_chunks:
                entry: dict = {}
                if chunk.retrieved_context:
                    entry["uri"] = chunk.retrieved_context.uri
                    entry["title"] = chunk.retrieved_context.title
                if chunk.web:
                    entry["web_uri"] = chunk.web.uri
                    entry["web_title"] = chunk.web.title
                if entry:
                    chunks.append(entry)

    logger.info(
        "documents_searched",
        user_id=user_id,
        query=query[:80],
        chunk_count=len(chunks),
    )

    return {
        "answer": answer,
        "chunks": chunks,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _ensure_corpus(
    user_id: str,
    display_name: str | None = None,
) -> str:
    """Return the corpus resource name for *user_id*, creating if needed."""
    if user_id in _user_corpora:
        return _user_corpora[user_id]

    name = display_name or f"omni-{user_id}"
    corpus_name = await _create_corpus_rest(name)
    _user_corpora[user_id] = corpus_name
    logger.info("corpus_created", user_id=user_id, corpus=corpus_name)
    return corpus_name


# ---------------------------------------------------------------------------
# Pre-built FunctionTool instances
# ---------------------------------------------------------------------------

upload_document_tool = FunctionTool(upload_document)
search_documents_tool = FunctionTool(search_documents)


def get_rag_tools() -> list[FunctionTool]:
    """Return RAG-related tools."""
    return [upload_document_tool, search_documents_tool]
