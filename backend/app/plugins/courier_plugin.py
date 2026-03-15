"""Courier Plugin — Email & notification delivery via multiple channels.

Supports:
  - Email via Courier API (user-provided API key) or SMTP fallback
  - Extensible to SMS, push, Slack, etc.

Users store their Courier API key via the Settings panel; the plugin
loads it from GCP Secret Manager at runtime.
"""

from __future__ import annotations

import os

import httpx
from google.adk.tools import FunctionTool

from app.models.plugin import (
    PluginCategory,
    PluginKind,
    PluginManifest,
    ToolSummary,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

MANIFEST = PluginManifest(
    id="courier",
    name="Courier",
    description="Send emails and notifications. Supports Courier API, "
    "Resend, or SMTP. Each user provides their own API key.",
    version="0.1.0",
    author="Omni Hub Team",
    category=PluginCategory.COMMUNICATION,
    kind=PluginKind.NATIVE,
    icon="mail",
    tags=["communication", "email"],
    module="app.plugins.courier_plugin",
    factory="get_tools",
    env_keys=["COURIER_API_KEY"],
    requires_auth=True,
    tools_summary=[
        ToolSummary(name="send_email", description="Send an email to a recipient"),
        ToolSummary(name="send_notification", description="Send a notification via channel"),
    ],
)

# ---------------------------------------------------------------------------
# Courier / Resend API helpers
# ---------------------------------------------------------------------------

_COURIER_SEND_URL = "https://api.courier.com/send"
_RESEND_SEND_URL = "https://api.resend.com/emails"


async def _send_via_courier(api_key: str, to_email: str, subject: str, body: str) -> dict:
    """Send email via Courier API."""
    payload = {
        "message": {
            "to": {"email": to_email},
            "content": {
                "title": subject,
                "body": body,
            },
        }
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _COURIER_SEND_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code in (200, 202):
            data = resp.json()
            return {"success": True, "request_id": data.get("requestId", "")}
        return {"success": False, "error": f"Courier API error: {resp.status_code} — {resp.text}"}


async def _send_via_resend(api_key: str, to_email: str, subject: str, body: str) -> dict:
    """Send email via Resend API (alternative to Courier)."""
    from_email = os.environ.get("RESEND_FROM_EMAIL", "omni@resend.dev")
    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": body.replace("\n", "<br>"),
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _RESEND_SEND_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            return {"success": True, "email_id": data.get("id", "")}
        return {"success": False, "error": f"Resend API error: {resp.status_code} — {resp.text}"}


def _get_api_key(context: dict | None = None) -> tuple[str, str]:
    """Get API key and provider. Returns (key, provider)."""
    # Check for user-provided keys via tool context or env
    courier_key = os.environ.get("COURIER_API_KEY", "")
    resend_key = os.environ.get("RESEND_API_KEY", "")

    if courier_key:
        return courier_key, "courier"
    if resend_key:
        return resend_key, "resend"
    return "", "none"


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def send_email(
    to: str,
    subject: str,
    body: str,
) -> dict:
    """Send an email to a recipient.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body content (plain text or HTML).

    Returns:
        A dict with success status and delivery details.
    """
    if not to or "@" not in to:
        return {"success": False, "error": "Invalid email address"}

    api_key, provider = _get_api_key()

    if provider == "courier":
        result = await _send_via_courier(api_key, to, subject, body)
    elif provider == "resend":
        result = await _send_via_resend(api_key, to, subject, body)
    else:
        return {
            "success": False,
            "error": "No email provider configured. Set COURIER_API_KEY or RESEND_API_KEY.",
        }

    if result.get("success"):
        logger.info("email_sent", to=to, subject=subject, provider=provider)
    else:
        logger.warning("email_send_failed", to=to, error=result.get("error"))

    return {**result, "provider": provider, "to": to, "subject": subject}


async def send_notification(
    message: str,
    channel: str = "email",
    recipient: str = "",
    title: str = "",
) -> dict:
    """Send a notification via the specified channel.

    Args:
        message: The notification message.
        channel: Delivery channel: 'email', 'log', 'webhook'.
        recipient: Recipient address (email/phone depending on channel).
        title: Optional notification title.

    Returns:
        A dict with success status and delivery info.
    """
    if channel == "email":
        if not recipient:
            return {"success": False, "error": "Recipient email required for email channel"}
        return await send_email(to=recipient, subject=title or "Notification from Omni", body=message)
    elif channel == "log":
        logger.info("notification_sent", channel="log", title=title, message=message)
        return {"success": True, "channel": "log", "message": f"Logged: {title} — {message}"}
    else:
        return {"success": False, "error": f"Channel '{channel}' not yet supported. Use 'email' or 'log'."}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_tools() -> list[FunctionTool]:
    return [
        FunctionTool(send_email),
        FunctionTool(send_notification),
    ]
