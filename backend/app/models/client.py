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


class ClientInfo(BaseModel):
    """A single connected client device."""

    user_id: str
    client_type: ClientType = ClientType.WEB
    client_id: str = ""
    connected_at: datetime
    last_ping: datetime


class ClientStatus(BaseModel):
    """Aggregate status of all connected clients for a user."""

    clients: list[ClientInfo] = []

    @property
    def total_connected(self) -> int:
        return len(self.clients)
