"""Application settings — loaded from environment variables via Pydantic Settings."""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    APP_NAME: str = "omni-agent-hub"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"  # development | staging | production
    BACKEND_PORT: int = 8000
    BACKEND_HOST: str = "::"  # Listen on all interfaces (required for container deployment like Cloud Run)
    LOG_LEVEL: str = "INFO"

    # --- Google Cloud / Vertex AI ---
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_CLOUD_LOCATION: str = "us-central1"
    GOOGLE_GENAI_USE_VERTEXAI: bool = True
    GOOGLE_API_KEY: str = ""  # Alternative to Vertex AI for local dev
    GOOGLE_APPLICATION_CREDENTIALS: str = ""  # Path to service account JSON

    # --- Vertex AI Agent Engine ---
    AGENT_ENGINE_NAME: str = ""  # projects/.../locations/.../reasoningEngines/...
    USE_AGENT_ENGINE_SESSIONS: bool = True
    USE_AGENT_ENGINE_MEMORY_BANK: bool = True
    USE_AGENT_ENGINE_CODE_EXECUTION: bool = True
    AGENT_ENGINE_SESSION_TTL: str = "604800s"  # 7 days
    AGENT_ENGINE_SANDBOX_TTL: str = "86400s"  # 24 hours

    # --- Firebase ---
    FIREBASE_PROJECT_ID: str = ""
    FIREBASE_SERVICE_ACCOUNT: str = ""  # Path to service account JSON

    # --- E2B Sandbox ---
    E2B_API_KEY: str = ""

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # --- Model Names ---
    LIVE_MODEL: str = "gemini-live-2.5-flash-native-audio"  # Vertex AI native audio model
    TEXT_MODEL: str = "gemini-2.5-flash"  # Standard text model

    # --- GCS (Cloud Storage) ---
    GCS_BUCKET_NAME: str = "omni-artifacts"

    # --- URLs (OAuth callbacks, CORS postMessage) ---
    BACKEND_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:5173"

    # --- Google OAuth (for Google Calendar / Drive plugins) ---
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# ── Export critical env vars so google-genai / google-auth / ADK can find them ──
# Pydantic reads .env into Python but doesn't set os.environ; the Google
# SDKs check os.environ directly.
_ENV_EXPORTS = {
    "GOOGLE_GENAI_USE_VERTEXAI": str(settings.GOOGLE_GENAI_USE_VERTEXAI).lower(),
    "GOOGLE_CLOUD_PROJECT": settings.GOOGLE_CLOUD_PROJECT,
    "GOOGLE_CLOUD_LOCATION": settings.GOOGLE_CLOUD_LOCATION,
}
if settings.GOOGLE_API_KEY:
    _ENV_EXPORTS["GOOGLE_API_KEY"] = settings.GOOGLE_API_KEY
if settings.GOOGLE_APPLICATION_CREDENTIALS:
    # Resolve relative path (e.g. "firebase-sa.json") to absolute so
    # google-auth can find it regardless of CWD.
    _cred_path = settings.GOOGLE_APPLICATION_CREDENTIALS
    if not os.path.isabs(_cred_path):
        _cred_path = os.path.join(os.path.dirname(__file__), os.pardir, _cred_path)
    _cred_path = os.path.abspath(_cred_path)
    _ENV_EXPORTS["GOOGLE_APPLICATION_CREDENTIALS"] = _cred_path

# Export URLs and Google OAuth creds so services using os.environ.get() pick them up
if settings.BACKEND_URL:
    _ENV_EXPORTS["BACKEND_URL"] = settings.BACKEND_URL
if settings.FRONTEND_URL:
    _ENV_EXPORTS["FRONTEND_URL"] = settings.FRONTEND_URL
if settings.GOOGLE_OAUTH_CLIENT_ID:
    _ENV_EXPORTS["GOOGLE_OAUTH_CLIENT_ID"] = settings.GOOGLE_OAUTH_CLIENT_ID
if settings.GOOGLE_OAUTH_CLIENT_SECRET:
    _ENV_EXPORTS["GOOGLE_OAUTH_CLIENT_SECRET"] = settings.GOOGLE_OAUTH_CLIENT_SECRET

for _k, _v in _ENV_EXPORTS.items():
    if _v and not os.environ.get(_k):
        os.environ[_k] = _v
