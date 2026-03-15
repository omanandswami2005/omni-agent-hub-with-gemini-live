"""FastAPI router aggregator — mounts all sub-routers under /api/v1."""

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.clients import router as clients_router
from app.api.gallery import router as gallery_router
from app.api.health import router as health_router
from app.api.init import router as init_router
from app.api.mcp import router as mcp_router
from app.api.personas import router as personas_router
from app.api.plugins import router as plugins_router
from app.api.sessions import router as sessions_router
from app.api.tasks import router as tasks_router

api_router = APIRouter(prefix="/api/v1")

# Health at /api/v1/health (also mounted at root /health in main.py)
api_router.include_router(health_router, tags=["health"])
api_router.include_router(init_router, tags=["init"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(personas_router, prefix="/personas", tags=["personas"])
api_router.include_router(sessions_router, prefix="/sessions", tags=["sessions"])
api_router.include_router(mcp_router, prefix="/mcp", tags=["mcp"])
api_router.include_router(plugins_router, prefix="/plugins", tags=["plugins"])
api_router.include_router(clients_router, prefix="/clients", tags=["clients"])
api_router.include_router(gallery_router, prefix="/gallery", tags=["gallery"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
