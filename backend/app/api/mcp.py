"""GET/POST /mcp — plugin store management."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_mcps():
    # TODO: Return available + installed MCPs from Firestore
    return []


@router.post("/toggle")
async def toggle_mcp():
    # TODO: Enable/disable MCP plugin for user session
    return {"status": "toggled"}
