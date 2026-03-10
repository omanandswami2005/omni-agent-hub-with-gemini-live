"""Auth endpoints — token verification & current user info."""

from fastapi import APIRouter

from app.middleware.auth_middleware import AuthenticatedUser, CurrentUser

router = APIRouter()


@router.post("/verify")
async def verify_token(user: CurrentUser) -> dict:
    """Verify a Firebase ID token and return the user profile.

    The token is passed via `Authorization: Bearer <token>` header.
    If valid, returns user info; otherwise 401.
    """
    return _user_response(user)


@router.get("/me")
async def get_me(user: CurrentUser) -> dict:
    """Return the currently authenticated user's profile."""
    return _user_response(user)


def _user_response(user: AuthenticatedUser) -> dict:
    return {
        "user_id": user.uid,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
    }
