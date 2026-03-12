"""RAG Plugin — Vertex AI document search and retrieval.

Provides ``upload_document`` and ``search_documents`` tools via Vertex AI
RAG Engine.  Enable this plugin to let the agent search your uploaded documents.

Users enable this plugin when they want to:
- Upload PDFs, docs, or text files for the agent to reference
- Search across their personal document library
- Get grounded answers from private content

The plugin wraps the tools in ``app/tools/rag.py`` — no duplicate logic here.
"""

from __future__ import annotations

from google.adk.tools import FunctionTool

from app.models.plugin import PluginCategory, PluginKind, PluginManifest, ToolSummary

# ---------------------------------------------------------------------------
# Plugin manifest — auto-discovered by PluginRegistry at startup
# ---------------------------------------------------------------------------

MANIFEST = PluginManifest(
    id="rag-documents",
    name="Document Search (RAG)",
    description="Upload documents and search them with AI-powered semantic retrieval. "
    "Uses Vertex AI RAG Engine for grounded, citation-backed answers.",
    version="0.1.0",
    author="Omni Hub Team",
    category=PluginCategory.KNOWLEDGE,
    kind=PluginKind.NATIVE,
    icon="document-search",
    module="app.plugins.rag_plugin",
    factory="get_tools",
    tools_summary=[
        ToolSummary(
            name="upload_document",
            description="Upload a GCS document to your personal RAG corpus for AI retrieval",
        ),
        ToolSummary(
            name="search_documents",
            description="Search your uploaded documents with a natural-language query",
        ),
    ],
)


# ---------------------------------------------------------------------------
# Factory — delegates to the existing tool implementations in app/tools/rag.py
# ---------------------------------------------------------------------------


def get_tools() -> list[FunctionTool]:
    """Return RAG tools. Called by PluginRegistry when plugin is enabled."""
    from app.tools.rag import get_rag_tools
    return get_rag_tools()
