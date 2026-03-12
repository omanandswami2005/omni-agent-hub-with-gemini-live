"""Cross-Client Orchestrator — a dedicated sub-agent for device actions.

Owns all T3 proxy tools (client-advertised local tools) and the built-in
cross-client action tools (send_to_desktop, send_to_chrome, etc.).
The root agent can ``transfer_to_agent`` here when the user request
involves controlling a connected device or forwarding data between clients.
"""

from __future__ import annotations

from google.adk.agents import Agent

from app.agents.agent_factory import LIVE_MODEL
from app.tools.cross_client import get_cross_client_tools
from app.utils.logging import get_logger

logger = get_logger(__name__)

CROSS_CLIENT_INSTRUCTION = (
    "You are the Device Controller agent.  You can send actions to the "
    "user's connected devices (desktop tray, Chrome extension, web dashboard) "
    "and invoke any client-local tools they advertise.\n\n"
    "Available actions:\n"
    "- send_to_desktop: launch apps, type text, capture screen on the desktop\n"
    "- send_to_chrome: open tabs, get page content in the browser extension\n"
    "- send_to_dashboard: push notifications or rendered UI to the web dashboard\n"
    "- notify_client: send a notification to a specific client\n"
    "- list_connected_clients: discover which devices are online\n\n"
    "You also have access to any client-local tools the user's devices have "
    "registered (T3 proxy tools).\n\n"
    "Always confirm what you did after executing an action."
)


def build_cross_client_agent(
    device_tools: list | None = None,
    model: str | None = None,
) -> Agent:
    """Build the cross-client orchestrator sub-agent.

    Parameters
    ----------
    device_tools:
        T3 proxy tools from ``ToolRegistry``'s ``__device__`` key.
    model:
        Override model.  Defaults to ``LIVE_MODEL``.
    """
    tools = get_cross_client_tools()
    if device_tools:
        tools.extend(device_tools)

    agent = Agent(
        name="device_agent",
        model=model or LIVE_MODEL,
        instruction=CROSS_CLIENT_INSTRUCTION,
        tools=tools,
    )
    logger.info("cross_client_agent_built", tool_count=len(tools))
    return agent
