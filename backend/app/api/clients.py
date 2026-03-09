"""GET /clients — connected device status."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_clients():
    # TODO: Return connected clients from ConnectionManager registry
    return []
