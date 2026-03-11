"""Client device Pydantic schemas."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class ClientType(StrEnum):
    WEB = "web"
    DESKTOP = "desktop"
    CHROME = "chrome"
    MOBILE = "mobile"
    GLASSES = "glasses"


def detect_os(user_agent: str) -> str:
    """Return a concise OS label from a User-Agent string."""
    ua = (user_agent or "").lower()
    if "android" in ua:
        return "Android"
    if "iphone" in ua or "ipad" in ua or "ipod" in ua:
        return "iOS"
    if "windows" in ua:
        return "Windows"
    if "mac" in ua:
        return "macOS"
    if "linux" in ua or "x11" in ua:
        return "Linux"
    if "cros" in ua or "chromebook" in ua:
        return "ChromeOS"
    return "Unknown"


class ClientInfo(BaseModel):
    """A single connected client device."""

    user_id: str
    client_type: ClientType = ClientType.WEB
    client_id: str = ""
    connected_at: datetime
    last_ping: datetime
    os_name: str = "Unknown"


class ClientStatus(BaseModel):
    """Aggregate status of all connected clients for a user."""

    clients: list[ClientInfo] = []

    @property
    def total_connected(self) -> int:
        return len(self.clients)
