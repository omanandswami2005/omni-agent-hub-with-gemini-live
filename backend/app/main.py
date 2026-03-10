"""FastAPI application factory + lifespan."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.router import api_router
from app.api.ws_events import router as ws_events_router
from app.api.ws_live import router as ws_live_router
from app.config import settings
from app.middleware.cors import setup_cors
from app.utils.errors import register_exception_handlers
from app.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    setup_logging(settings.LOG_LEVEL)
    logger.info(
        "backend_starting",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )
    yield
    logger.info("backend_shutting_down")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # Middleware
    setup_cors(app)

    # Exception handlers
    register_exception_handlers(app)

    # Routes — root /health for Cloud Run probe
    app.include_router(health_router, tags=["health"])
    # All API routes under /api/v1
    app.include_router(api_router)

    # WebSocket routes under /ws
    app.include_router(ws_live_router, prefix="/ws", tags=["websocket"])
    app.include_router(ws_events_router, prefix="/ws", tags=["websocket"])

    return app


app = create_app()
