"""Native plugin — Google Jules (AI coding agent).

Allows the user to delegate coding tasks to Jules via its REST API.
Jules investigates code, creates plans, executes fixes, and creates PRs
on connected GitHub repositories.

Authentication: Per-user API key from https://jules.google.com/settings#api
"""

from __future__ import annotations

from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext

from app.models.plugin import (
    PluginCategory,
    PluginKind,
    PluginManifest,
    ToolSummary,
)

MANIFEST = PluginManifest(
    id="google-jules",
    name="Google Jules",
    description="Delegate coding tasks to Google's AI coding agent Jules. "
    "Jules can analyze repos, create plans, write code, run tests, and open PRs.",
    version="0.1.0",
    author="Omni Hub Team",
    category=PluginCategory.DEV,
    kind=PluginKind.NATIVE,
    icon="jules",
    tags=["code_execution", "dev", "*"],
    module="app.plugins.jules_plugin",
    factory="get_tools",
    requires_auth=True,
    env_keys=["JULES_API_KEY"],
    tools_summary=[
        ToolSummary(
            name="jules_list_sources",
            description="List GitHub repositories connected to Jules",
        ),
        ToolSummary(
            name="jules_create_session",
            description="Create a new Jules coding session (task) on a repository",
        ),
        ToolSummary(
            name="jules_list_sessions",
            description="List recent Jules coding sessions",
        ),
        ToolSummary(
            name="jules_get_session",
            description="Get details and status of a Jules session",
        ),
        ToolSummary(
            name="jules_send_message",
            description="Send a follow-up message to an active Jules session",
        ),
        ToolSummary(
            name="jules_approve_plan",
            description="Approve a pending plan in a Jules session",
        ),
    ],
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE_URL = "https://jules.googleapis.com/v1alpha"
_PLUGIN_ID = "google-jules"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_api_key(tool_context: ToolContext | None) -> str | None:
    """Retrieve the Jules API key from user secrets."""
    if tool_context is None:
        return None
    user_id = getattr(tool_context, "user_id", None)
    if not user_id:
        return None
    from app.services import secret_service
    try:
        secrets = secret_service.load_secrets(user_id, _PLUGIN_ID)
        return secrets.get("JULES_API_KEY")
    except Exception:
        return None


def _headers(api_key: str) -> dict[str, str]:
    return {"x-goog-api-key": api_key, "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def jules_list_sources(
    tool_context: ToolContext | None = None,
) -> dict:
    """List GitHub repositories connected to Jules.

    Returns:
        A dict with list of connected sources (repos).
    """
    import httpx

    api_key = await _get_api_key(tool_context)
    if not api_key:
        return {"error": "Jules API key not configured. Add your key in the Integrations page."}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{_BASE_URL}/sources",
            headers=_headers(api_key),
        )
        if resp.status_code == 401:
            return {"error": "Invalid Jules API key. Please update it in Integrations."}
        resp.raise_for_status()
        data = resp.json()

    sources = []
    for s in data.get("sources", []):
        gh = s.get("githubRepo", {})
        sources.append({
            "name": s.get("name", ""),
            "owner": gh.get("owner", ""),
            "repo": gh.get("repo", ""),
            "default_branch": gh.get("defaultBranch", {}).get("displayName", "main"),
        })
    return {"sources": sources, "count": len(sources)}


async def jules_create_session(
    prompt: str,
    source: str = "",
    branch: str = "main",
    title: str = "",
    auto_create_pr: bool = False,
    tool_context: ToolContext | None = None,
) -> dict:
    """Create a new Jules coding session to delegate a task.

    Args:
        prompt: Detailed description of the coding task for Jules.
        source: Source name (e.g. 'sources/github-owner-repo'). Use jules_list_sources to find it.
        branch: Git branch to work from (default: main).
        title: Optional title for the session.
        auto_create_pr: If true, Jules will automatically create a PR when done.

    Returns:
        A dict with the created session details and URL.
    """
    import httpx

    api_key = await _get_api_key(tool_context)
    if not api_key:
        return {"error": "Jules API key not configured. Add your key in the Integrations page."}

    body: dict = {"prompt": prompt}
    if title:
        body["title"] = title
    if source:
        body["sourceContext"] = {
            "source": source,
            "githubRepoContext": {"startingBranch": branch},
        }
    if auto_create_pr:
        body["automationMode"] = "AUTO_CREATE_PR"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{_BASE_URL}/sessions",
            headers=_headers(api_key),
            json=body,
        )
        if resp.status_code == 401:
            return {"error": "Invalid Jules API key."}
        resp.raise_for_status()
        data = resp.json()

    return {
        "session_id": data.get("id", ""),
        "name": data.get("name", ""),
        "title": data.get("title", ""),
        "state": data.get("state", ""),
        "url": data.get("url", ""),
        "prompt": data.get("prompt", "")[:200],
    }


async def jules_list_sessions(
    page_size: int = 10,
    tool_context: ToolContext | None = None,
) -> dict:
    """List recent Jules coding sessions.

    Args:
        page_size: Number of sessions to return (1-100).

    Returns:
        A dict with list of sessions and their states.
    """
    import httpx

    api_key = await _get_api_key(tool_context)
    if not api_key:
        return {"error": "Jules API key not configured. Add your key in the Integrations page."}

    page_size = max(1, min(100, page_size))
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{_BASE_URL}/sessions",
            headers=_headers(api_key),
            params={"pageSize": str(page_size)},
        )
        if resp.status_code == 401:
            return {"error": "Invalid Jules API key."}
        resp.raise_for_status()
        data = resp.json()

    sessions = []
    for s in data.get("sessions", []):
        sessions.append({
            "id": s.get("id", ""),
            "title": s.get("title", ""),
            "state": s.get("state", ""),
            "url": s.get("url", ""),
            "created": s.get("createTime", ""),
            "updated": s.get("updateTime", ""),
        })
    return {"sessions": sessions, "count": len(sessions)}


async def jules_get_session(
    session_id: str,
    tool_context: ToolContext | None = None,
) -> dict:
    """Get details and status of a Jules session.

    Args:
        session_id: The session ID to retrieve.

    Returns:
        A dict with full session details including outputs.
    """
    import httpx

    api_key = await _get_api_key(tool_context)
    if not api_key:
        return {"error": "Jules API key not configured. Add your key in the Integrations page."}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{_BASE_URL}/sessions/{session_id}",
            headers=_headers(api_key),
        )
        if resp.status_code == 401:
            return {"error": "Invalid Jules API key."}
        if resp.status_code == 404:
            return {"error": f"Session '{session_id}' not found."}
        resp.raise_for_status()
        data = resp.json()

    result = {
        "id": data.get("id", ""),
        "title": data.get("title", ""),
        "state": data.get("state", ""),
        "prompt": data.get("prompt", ""),
        "url": data.get("url", ""),
        "created": data.get("createTime", ""),
        "updated": data.get("updateTime", ""),
    }

    # Include outputs (PRs) if available
    outputs = data.get("outputs", [])
    if outputs:
        prs = []
        for o in outputs:
            pr = o.get("pullRequest", {})
            if pr:
                prs.append({
                    "url": pr.get("url", ""),
                    "title": pr.get("title", ""),
                    "description": pr.get("description", "")[:300],
                })
        result["pull_requests"] = prs

    return result


async def jules_send_message(
    session_id: str,
    message: str,
    tool_context: ToolContext | None = None,
) -> dict:
    """Send a follow-up message to an active Jules session.

    Args:
        session_id: The session ID to message.
        message: The message/instruction to send to Jules.

    Returns:
        A dict confirming the message was sent.
    """
    import httpx

    api_key = await _get_api_key(tool_context)
    if not api_key:
        return {"error": "Jules API key not configured. Add your key in the Integrations page."}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{_BASE_URL}/sessions/{session_id}:sendMessage",
            headers=_headers(api_key),
            json={"prompt": message},
        )
        if resp.status_code == 401:
            return {"error": "Invalid Jules API key."}
        if resp.status_code == 404:
            return {"error": f"Session '{session_id}' not found."}
        resp.raise_for_status()

    return {"success": True, "message": f"Message sent to session {session_id}."}


async def jules_approve_plan(
    session_id: str,
    tool_context: ToolContext | None = None,
) -> dict:
    """Approve a pending plan in a Jules session.

    Args:
        session_id: The session ID with a pending plan.

    Returns:
        A dict confirming the plan was approved.
    """
    import httpx

    api_key = await _get_api_key(tool_context)
    if not api_key:
        return {"error": "Jules API key not configured. Add your key in the Integrations page."}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{_BASE_URL}/sessions/{session_id}:approvePlan",
            headers=_headers(api_key),
            json={},
        )
        if resp.status_code == 401:
            return {"error": "Invalid Jules API key."}
        if resp.status_code == 404:
            return {"error": f"Session '{session_id}' not found."}
        resp.raise_for_status()

    return {"success": True, "message": f"Plan approved for session {session_id}."}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_tools() -> list[FunctionTool]:
    return [
        FunctionTool(jules_list_sources),
        FunctionTool(jules_create_session),
        FunctionTool(jules_list_sessions),
        FunctionTool(jules_get_session),
        FunctionTool(jules_send_message),
        FunctionTool(jules_approve_plan),
    ]
