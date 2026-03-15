"""Native plugin — Google Calendar (per-user OAuth).

Each user connects their own Google account via OAuth 2.0.  Tools then
operate on *that user's* calendar using their personal access token.

Scopes: https://www.googleapis.com/auth/calendar
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

GOOGLE_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]

MANIFEST = PluginManifest(
    id="google-calendar",
    name="Google Calendar",
    description="Read, create, and manage events on your Google Calendar. "
    "Each user connects their own Google account via OAuth.",
    version="0.1.0",
    author="Omni Hub Team",
    category=PluginCategory.PRODUCTIVITY,
    kind=PluginKind.NATIVE,
    icon="google-calendar",
    tags=["productivity", "gcp", "calendar"],
    module="app.plugins.google_calendar_plugin",
    factory="get_tools",
    requires_auth=True,
    google_oauth_scopes=GOOGLE_CALENDAR_SCOPES,
    tools_summary=[
        ToolSummary(
            name="list_calendar_events",
            description="List upcoming events from the user's Google Calendar",
        ),
        ToolSummary(
            name="create_calendar_event",
            description="Create a new event on the user's Google Calendar",
        ),
        ToolSummary(
            name="delete_calendar_event",
            description="Delete an event from the user's Google Calendar",
        ),
    ],
)

# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

_API = "https://www.googleapis.com/calendar/v3"
_PLUGIN_ID = "google-calendar"


async def _get_token(tool_context: ToolContext | None) -> str | None:
    """Get the Google OAuth access token from the session context."""
    if tool_context is None:
        return None
    user_id = getattr(tool_context, "user_id", None)
    if not user_id:
        return None
    from app.services.google_oauth_service import get_google_oauth_service
    goauth = get_google_oauth_service()
    return await goauth.get_valid_token(user_id, _PLUGIN_ID)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def list_calendar_events(
    max_results: int = 10,
    tool_context: ToolContext | None = None,
) -> dict:
    """List upcoming events from the user's Google Calendar.

    Args:
        max_results: Maximum number of events to return (1-50).

    Returns:
        A dict with the list of upcoming events.
    """
    from datetime import UTC, datetime

    import httpx

    access_token = await _get_token(tool_context)
    if not access_token:
        return {"error": "Not connected. Please connect your Google account first via the Integrations page."}

    max_results = max(1, min(50, max_results))
    now = datetime.now(UTC).isoformat()

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{_API}/calendars/primary/events",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "maxResults": str(max_results),
                "timeMin": now,
                "singleEvents": "true",
                "orderBy": "startTime",
            },
        )
        if resp.status_code == 401:
            return {"error": "Token expired or revoked. Please reconnect your Google account."}
        resp.raise_for_status()
        data = resp.json()

    events = []
    for item in data.get("items", []):
        start = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date", "")
        end = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date", "")
        events.append(
            {
                "id": item.get("id"),
                "summary": item.get("summary", "(No title)"),
                "start": start,
                "end": end,
                "location": item.get("location", ""),
                "description": item.get("description", "")[:200],
            }
        )

    return {"events": events, "count": len(events)}


async def create_calendar_event(
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    tool_context: ToolContext | None = None,
) -> dict:
    """Create a new event on the user's Google Calendar.

    Args:
        summary: Title of the event.
        start_time: Start time in ISO 8601 format (e.g. 2026-03-15T10:00:00-05:00).
        end_time: End time in ISO 8601 format.
        description: Optional description.
        location: Optional location.

    Returns:
        A dict with the created event details.
    """
    import httpx

    access_token = await _get_token(tool_context)
    if not access_token:
        return {"error": "Not connected. Please connect your Google account first via the Integrations page."}

    body: dict = {
        "summary": summary,
        "start": {"dateTime": start_time},
        "end": {"dateTime": end_time},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{_API}/calendars/primary/events",
            headers={"Authorization": f"Bearer {access_token}"},
            json=body,
        )
        if resp.status_code == 401:
            return {"error": "Token expired or revoked. Please reconnect your Google account."}
        resp.raise_for_status()
        event = resp.json()

    return {
        "success": True,
        "event_id": event.get("id"),
        "summary": event.get("summary"),
        "link": event.get("htmlLink"),
    }


async def delete_calendar_event(
    event_id: str,
    tool_context: ToolContext | None = None,
) -> dict:
    """Delete an event from the user's Google Calendar.

    Args:
        event_id: The ID of the event to delete.

    Returns:
        A dict with the deletion status.
    """
    import httpx

    access_token = await _get_token(tool_context)
    if not access_token:
        return {"error": "Not connected. Please connect your Google account first via the Integrations page."}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.delete(
            f"{_API}/calendars/primary/events/{event_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 401:
            return {"error": "Token expired or revoked. Please reconnect your Google account."}
        if resp.status_code == 404:
            return {"error": f"Event '{event_id}' not found."}
        resp.raise_for_status()

    return {"success": True, "message": f"Event '{event_id}' deleted."}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_tools() -> list[FunctionTool]:
    return [
        FunctionTool(list_calendar_events),
        FunctionTool(create_calendar_event),
        FunctionTool(delete_calendar_event),
    ]
