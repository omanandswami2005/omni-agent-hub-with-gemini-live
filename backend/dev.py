"""Dev server shortcut: `uv run dev.py`"""
import uvicorn
from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        reload=True,
        reload_dirs=["app", ".env"],
        env_file=".env",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        timeout_graceful_shutdown=3,
    )
