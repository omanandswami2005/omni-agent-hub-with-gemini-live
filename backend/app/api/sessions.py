"""GET/DELETE /sessions — session history."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_sessions():
    # TODO: Fetch session history from Agent Engine Sessions / Firestore
    return []


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    # TODO: Delete session
    return {"status": "deleted", "session_id": session_id}
