"""GET /clients — connected device status."""

from fastapi import APIRouter, Depends

from app.middleware.auth_middleware import CurrentUser
from app.models.client import ClientInfo
from app.services.connection_manager import ConnectionManager, get_connection_manager

router = APIRouter()


@router.get("")
async def list_clients(
    user: CurrentUser,
    mgr: ConnectionManager = Depends(get_connection_manager),  # noqa: B008
) -> list[ClientInfo]:
    """Return all currently-connected clients for the authenticated user."""
    return mgr.get_connected_clients(user.uid)
