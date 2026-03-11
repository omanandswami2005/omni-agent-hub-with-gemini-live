"""Desktop client configuration."""

from pydantic_settings import BaseSettings


class DesktopConfig(BaseSettings):
    server_url: str = "ws://localhost:8000/ws/live"
    auth_token: str = ""
    audio_device: int | None = None
    capture_quality: int = 75
    allowed_directories: list[str] = ["~"]
    log_level: str = "INFO"

    model_config = {"env_prefix": "OMNI_DESKTOP_", "env_file": ".env"}


config = DesktopConfig()
