"""Native plugin — Wikipedia Search.

Provides tools for searching and reading Wikipedia articles using the
``wikipedia`` Python library.  Replaces the broken MCP HTTP approach
since no reliable public Wikipedia MCP endpoint exists.
"""

from __future__ import annotations

import contextlib

from google.adk.tools import FunctionTool

from app.models.plugin import (
    PluginCategory,
    PluginKind,
    PluginManifest,
    ToolSummary,
)

MANIFEST = PluginManifest(
    id="wikipedia",
    name="Wikipedia",
    description="Search and read Wikipedia articles for factual research.",
    version="0.1.0",
    author="Omni Hub Team",
    category=PluginCategory.SEARCH,
    kind=PluginKind.NATIVE,
    icon="wikipedia",
    tags=["search", "knowledge"],
    module="app.plugins.wikipedia_search",
    factory="get_tools",
    tools_summary=[
        ToolSummary(
            name="search_wikipedia",
            description="Search Wikipedia and return a list of matching article titles",
        ),
        ToolSummary(
            name="get_wikipedia_article",
            description="Get the summary or full content of a Wikipedia article",
        ),
    ],
)


async def search_wikipedia(query: str, num_results: int = 5) -> dict:
    """Search Wikipedia for articles matching a query.

    Args:
        query: The search query string.
        num_results: Maximum number of results to return (1-10).

    Returns:
        A dict with matching article titles and any suggestion.
    """
    import wikipedia

    num_results = max(1, min(10, num_results))
    try:
        results = wikipedia.search(query, results=num_results)
        suggestion = None
        with contextlib.suppress(Exception):
            _, suggestion = wikipedia.search(query, results=1, suggestion=True)
        return {
            "results": results,
            "suggestion": suggestion,
            "count": len(results),
        }
    except Exception as exc:
        return {"error": str(exc), "results": []}


async def get_wikipedia_article(
    title: str,
    sentences: int = 5,
    full_page: bool = False,
) -> dict:
    """Get the summary or full content of a Wikipedia article.

    Args:
        title: The exact title of the Wikipedia article.
        sentences: Number of sentences for the summary (ignored if full_page is True).
        full_page: If True, return the full article content instead of just the summary.

    Returns:
        A dict with the article title, summary/content, and URL.
    """
    import wikipedia

    try:
        page = wikipedia.page(title, auto_suggest=True)
        content = page.content if full_page else wikipedia.summary(title, sentences=sentences)
        return {
            "title": page.title,
            "content": content,
            "url": page.url,
            "categories": page.categories[:10],
        }
    except wikipedia.exceptions.DisambiguationError as e:
        return {
            "error": "disambiguation",
            "message": f"'{title}' may refer to multiple articles.",
            "options": e.options[:10],
        }
    except wikipedia.exceptions.PageError:
        return {
            "error": "not_found",
            "message": f"No Wikipedia article found for '{title}'.",
        }
    except Exception as exc:
        return {"error": str(exc)}


def get_tools() -> list[FunctionTool]:
    """Return all tools provided by this plugin."""
    return [
        FunctionTool(search_wikipedia),
        FunctionTool(get_wikipedia_article),
    ]
