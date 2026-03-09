"""WebSocket client for desktop-to-server communication."""

# TODO: Implement:
#   - Raw WebSocket connection using `websockets` library
#   - Auth via token query param (same as dashboard)
#   - Binary audio frames (sounddevice capture → 16kHz PCM)
#   - JSON control messages (capabilities registration, cross-client actions)
#   - Exponential backoff reconnection
#   - Heartbeat/ping-pong
#   - Handle incoming CrossClientMessage actions (screenshot, click, type, etc.)

import asyncio
import logging

logger = logging.getLogger(__name__)


class DesktopWSClient:
    """Raw WebSocket client for Omni server connection."""

    def __init__(self, server_url: str, token: str):
        self.server_url = server_url
        self.token = token
        self.ws = None
        self.connected = False

    async def connect(self):
        """Establish WebSocket connection with auth."""
        pass

    async def send_audio(self, pcm_data: bytes):
        """Send raw PCM16 audio as binary frame."""
        pass

    async def send_json(self, message: dict):
        """Send JSON control message as text frame."""
        pass

    async def listen(self):
        """Listen for incoming messages and dispatch to handlers."""
        pass

    async def disconnect(self):
        """Gracefully close connection."""
        pass
