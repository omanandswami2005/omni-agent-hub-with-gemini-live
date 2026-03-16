"""Desktop client configuration."""

from pydantic_settings import BaseSettings


class DesktopConfig(BaseSettings):
    server_url: str = "wss://omni-backend-fcapusldtq-uc.a.run.app/ws/live"
    auth_token: str = ""
    firebase_api_key: str = "AIzaSyC3a98P8sOUKEwGJuJWp2gA6i7o-CW21pE"
    audio_device: int | None = None
    capture_quality: int = 75
    allowed_directories: list[str] = ["~"]
    log_level: str = "INFO"

    model_config = {"env_prefix": "OMNI_DESKTOP_", "env_file": ".env"}


config = DesktopConfig()
