"""Email ADK tool — stub for sending emails.

This is a placeholder implementation that logs the email details and
returns a success message.  It will be replaced by a Courier MCP
integration later.

Registered under the ``COMMUNICATION`` capability so it's automatically
available to personas with that tag (e.g. ``assistant``).
"""

from __future__ import annotations

from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext

from app.utils.logging import get_logger

logger = get_logger(__name__)


async def send_email(
    to: str,
    subject: str,
    body: str,
    tool_context: ToolContext | None = None,
) -> str:
    """Compose and send an email to the specified recipient.

    This is a stub — the email is logged but not actually
    delivered.  A Courier MCP integration will replace this.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain-text email body.

    Returns:
        A confirmation message describing what was sent.
    """
    user_id = tool_context.user_id if tool_context else "unknown"

    logger.info(
        "email_send_stub",
        user_id=user_id,
        to=to,
        subject=subject,
        body_len=len(body),
    )

    # TODO: Replace with actual Courier MCP call
    return (
        f"Email sent successfully to {to} with subject '{subject}'. "
        f"(Stub — {len(body)} chars of body logged, not actually delivered. "
        "Courier MCP integration pending.)"
    )


send_email_tool = FunctionTool(send_email)


def get_email_tools() -> list[FunctionTool]:
    """Return email tools."""
    return [send_email_tool]
