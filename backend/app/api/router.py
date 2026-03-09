"""FastAPI router aggregator — mounts all sub-routers."""

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.personas import router as personas_router
from app.api.sessions import router as sessions_router
from app.api.mcp import router as mcp_router
from app.api.clients import router as clients_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(personas_router, prefix="/personas", tags=["personas"])
api_router.include_router(sessions_router, prefix="/sessions", tags=["sessions"])
api_router.include_router(mcp_router, prefix="/mcp", tags=["mcp"])
api_router.include_router(clients_router, prefix="/clients", tags=["clients"])

# WebSocket endpoints are mounted directly on the app in main.py
# because they use @app.websocket() decorator
