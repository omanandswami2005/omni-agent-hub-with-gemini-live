"""Application settings — loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "omni-agent-hub"

    # Google Cloud
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_CLOUD_LOCATION: str = "us-central1"
    GOOGLE_GENAI_USE_VERTEXAI: bool = True

    # Firebase
    FIREBASE_PROJECT_ID: str = ""

    # E2B
    E2B_API_KEY: str = ""

    # App
    BACKEND_PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:5173"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # GCS
    GCS_BUCKET_NAME: str = "omni-artifacts"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
