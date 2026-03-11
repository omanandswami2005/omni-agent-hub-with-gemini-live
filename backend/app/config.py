"""Application settings — loaded from environment variables via Pydantic Settings."""

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
    BACKEND_HOST: str = "0.0.0.0"  # Listen on all interfaces (required for container deployment like Cloud Run)
    LOG_LEVEL: str = "INFO"

    # --- Google Cloud / Vertex AI ---
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_CLOUD_LOCATION: str = "us-central1"
    GOOGLE_GENAI_USE_VERTEXAI: bool = True
    GOOGLE_API_KEY: str = ""  # Alternative to Vertex AI for local dev

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

    # --- GCS (Cloud Storage) ---
    GCS_BUCKET_NAME: str = "omni-artifacts"

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
