"""Dev server shortcut: `uv run dev.py`"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        reload=True,
        reload_dirs=["app", ".env"],
        env_file=".env",
        port=8000,
        timeout_graceful_shutdown=3,
    )
