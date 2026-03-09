"""Client device Pydantic schemas."""

from pydantic import BaseModel


class ClientInfo(BaseModel):
    user_id: str
    client_type: str  # "web" | "mobile" | "desktop" | "chrome_ext" | "esp32"
    connected_at: str
    last_ping: str


class ClientStatus(BaseModel):
    clients: list[ClientInfo] = []
    total_connected: int = 0
