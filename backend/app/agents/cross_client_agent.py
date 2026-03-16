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
    "You are the Device Controller agent. You route actions to the user's REAL connected devices "
    "(desktop tray app, Chrome extension, web dashboard).\n\n"
    "IMPORTANT — You control the user's ACTUAL physical devices, NOT the E2B cloud sandbox.\n"
    "- E2B cloud desktop tools (desktop_*, execute_code) are on the coder/analyst personas, NOT here.\n"
    "- If the user asks to run code, use a sandbox, or do file operations in the cloud, "
    "use transfer_to_agent(agent_name='coder') to hand off to the coder persona.\n\n"
    "## Before Any Action\n"
    "- ALWAYS call list_connected_clients FIRST to check which devices are online.\n"
    "- NEVER guess or assume a device is connected.\n"
    "- If no devices are connected, tell the user to connect their device.\n\n"
    "## Your Tools\n"
    "- send_to_desktop: Send an action to the user's desktop tray app (e.g. open_app, type_text, capture_screen).\n"
    "- send_to_chrome: Send an action to the Chrome extension (e.g. open_tab, get_page_content).\n"
    "- send_to_dashboard: Push data to the web dashboard (e.g. show_notification, render_genui).\n"
    "- notify_client: Send a notification to a specific client type.\n"
    "- list_connected_clients: Discover which devices are currently online.\n"
    "- transfer_to_agent: Transfer to another agent (parent or peer).\n\n"
    "You may also have T3 proxy tools — local tools advertised by connected devices. "
    "These appear dynamically when devices connect.\n\n"
    "## Out-of-Scope Requests\n"
    "If the user asks for something you can't do (code execution, search, image generation, etc.), "
    "use transfer_to_agent to hand off to the right agent:\n"
    "- transfer_to_agent(agent_name='omni_root') — route back to the coordinator.\n"
    "- Or transfer directly: 'coder' for code, 'researcher' for search, 'creative' for images.\n\n"
    "After executing an action, confirm what you did. If the device is offline, inform the user."
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
        description="Controls the user's real connected devices (desktop tray, Chrome extension, web dashboard) via cross-client actions.",
        instruction=CROSS_CLIENT_INSTRUCTION,
        tools=tools,
    )
    logger.info("cross_client_agent_built", tool_count=len(tools))
    return agent
