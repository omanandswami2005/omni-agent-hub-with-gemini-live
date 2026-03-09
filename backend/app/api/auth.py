"""POST /auth/verify — Firebase token verification."""

from fastapi import APIRouter

router = APIRouter()


@router.post("/verify")
async def verify_token():
    # TODO: Verify Firebase ID token, return user info
    return {"status": "ok"}
