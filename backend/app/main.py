"""FastAPI application factory + lifespan."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.config import settings
from app.middleware.cors import setup_cors


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print(f"🚀 Omni backend starting — {settings.APP_NAME}")
    yield
    # Shutdown
    print("👋 Omni backend shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        lifespan=lifespan,
    )
    setup_cors(app)
    app.include_router(api_router)
    return app


app = create_app()
