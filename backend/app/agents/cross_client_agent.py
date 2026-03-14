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
    "You are the Device Controller agent. You can send actions to the user's connected devices "
    "(desktop tray, Chrome extension, web dashboard) and invoke any client-local tools they advertise.\n\n"
    "IMPORTANT - When checking device capabilities or connected devices:\n"
    "- You MUST use the list_connected_clients tool to discover which devices are currently online\n"
    "- NEVER guess, assume, or hallucinate about device availability or capabilities\n"
    "- If list_connected_clients returns no devices, inform the user that no devices are connected\n"
    "- Only report capabilities that are explicitly returned by the tool\n\n"
    "To check cross-client device capabilities:\n"
    "- Use list_connected_clients to discover which devices are currently online\n"
    "- Each connected device may advertise specific local tools (T3 proxy tools) that you can invoke\n"
    "- Always check device connectivity before attempting to send actions\n\n"
    "Available cross-client actions:\n"
    "- send_to_desktop: launch apps, type text, capture screen on the desktop\n"
    "- send_to_chrome: open tabs, get page content in the browser extension\n"
    "- send_to_dashboard: push notifications or rendered UI to the web dashboard\n"
    "- notify_client: send a notification to a specific client\n"
    "- list_connected_clients: discover which devices are online\n\n"
    "You also have access to any client-local tools the user's devices have "
    "registered (T3 proxy tools). These tools are dynamically discovered based on connected devices.\n\n"
    "Always confirm what you did after executing an action. If a device is not connected, inform the user "
    "and suggest they connect the device first."
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
