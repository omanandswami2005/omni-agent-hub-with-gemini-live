"""GET /health — Cloud Run healthcheck."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "omni-backend"}
