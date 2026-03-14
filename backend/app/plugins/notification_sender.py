"""Example native plugin — Notification Sender.

Demonstrates how a third-party developer can create a plugin that
integrates with the Omni Hub backend.  This plugin provides tools
for sending notifications to various channels.

To create your own plugin:
1. Create a new .py file in this directory
2. Define a MANIFEST (PluginManifest)
3. Implement a factory function that returns list[FunctionTool]
4. The PluginRegistry auto-discovers it at startup
"""

from __future__ import annotations

from google.adk.tools import FunctionTool

from app.models.plugin import (
    PluginCategory,
    PluginKind,
    PluginManifest,
    ToolSummary,
)

# ---------------------------------------------------------------------------
# Plugin manifest — this is all the registry needs to discover the plugin
# ---------------------------------------------------------------------------

MANIFEST = PluginManifest(
    id="notification-sender",
    name="Notification Sender",
    description="Send notifications via various channels (webhook, log). "
    "Extensible template for Telegram, Slack, Email, SMS integrations.",
    version="0.1.0",
    author="Omni Hub Team",
    category=PluginCategory.COMMUNICATION,
    kind=PluginKind.NATIVE,
    icon="bell",
    tags=["communication"],
    module="app.plugins.notification_sender",
    factory="get_tools",
    tools_summary=[
        ToolSummary(
            name="send_notification",
            description="Send a notification message to a specified channel",
        ),
        ToolSummary(
            name="list_notification_channels",
            description="List available notification channels",
        ),
    ],
)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def send_notification(
    message: str,
    channel: str = "log",
    title: str = "",
) -> dict:
    """Send a notification message to a specified channel.

    Args:
        message: The notification message to send.
        channel: The channel to send to. Options: 'log', 'webhook'.
                 Future: 'telegram', 'slack', 'email', 'sms'.
        title: Optional title for the notification.

    Returns:
        A dict with success status and delivery details.
    """
    import logging

    if channel == "log":
        logging.getLogger("notification").info(
            "NOTIFICATION: %s — %s",
            title or "Alert",
            message,
        )
        return {
            "success": True,
            "channel": "log",
            "message": f"Logged notification: {title or 'Alert'} — {message}",
        }
    elif channel == "webhook":
        # Placeholder for webhook delivery
        return {
            "success": True,
            "channel": "webhook",
            "message": "Webhook notification would be sent here.",
            "note": "Configure NOTIFICATION_WEBHOOK_URL to enable.",
        }
    else:
        return {
            "success": False,
            "error": f"Unknown channel '{channel}'. Available: log, webhook.",
        }


async def list_notification_channels() -> dict:
    """List available notification channels and their status.

    Returns:
        A dict with available channels and their configuration status.
    """
    return {
        "channels": [
            {"id": "log", "name": "Log Output", "status": "active"},
            {"id": "webhook", "name": "Webhook", "status": "configure"},
            {"id": "telegram", "name": "Telegram", "status": "coming_soon"},
            {"id": "slack", "name": "Slack", "status": "coming_soon"},
            {"id": "email", "name": "Email", "status": "coming_soon"},
            {"id": "sms", "name": "SMS", "status": "coming_soon"},
        ],
    }


# ---------------------------------------------------------------------------
# Factory function (called by PluginRegistry)
# ---------------------------------------------------------------------------


def get_tools() -> list[FunctionTool]:
    """Return all tools provided by this plugin."""
    return [
        FunctionTool(send_notification),
        FunctionTool(list_notification_channels),
    ]
