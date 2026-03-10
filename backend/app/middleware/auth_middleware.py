"""Firebase JWT verification — FastAPI dependency for protected routes."""

from typing import Annotated

import firebase_admin
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

from app.config import settings
from app.utils.errors import AuthenticationError
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ── Firebase App Initialisation (idempotent) ──────────────────────────

_firebase_app: firebase_admin.App | None = None


def _get_firebase_app() -> firebase_admin.App:
    """Lazily initialise the Firebase Admin SDK (once per process)."""
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    try:
        _firebase_app = firebase_admin.get_app()
    except ValueError:
        cred = None
        if settings.FIREBASE_SERVICE_ACCOUNT:
            cred = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT)
        _firebase_app = firebase_admin.initialize_app(
            cred,
            {"projectId": settings.FIREBASE_PROJECT_ID or None},
        )
    return _firebase_app


# ── Bearer token extractor ────────────────────────────────────────────

_bearer_scheme = HTTPBearer(auto_error=False)


# ── Decoded user info attached to request ─────────────────────────────


class AuthenticatedUser:
    """Lightweight wrapper around Firebase decoded token claims."""

    __slots__ = ("claims", "email", "name", "picture", "uid")

    def __init__(self, decoded_token: dict) -> None:
        self.uid: str = decoded_token["uid"]
        self.email: str = decoded_token.get("email", "")
        self.name: str = decoded_token.get("name", "")
        self.picture: str = decoded_token.get("picture", "")
        self.claims: dict = decoded_token


# ── FastAPI dependency ────────────────────────────────────────────────


async def get_current_user(
    request: Request,
    credential: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),  # noqa: B008
) -> AuthenticatedUser:
    """Verify Firebase ID token and return an AuthenticatedUser.

    Usage in route handlers:
        @router.get("/protected")
        async def protected(user: AuthenticatedUser = Depends(get_current_user)):
            ...
    """
    if credential is None:
        raise AuthenticationError("Missing Authorization header")

    token = credential.credentials
    _get_firebase_app()

    try:
        decoded = firebase_auth.verify_id_token(token)
    except firebase_auth.ExpiredIdTokenError as exc:
        raise AuthenticationError("Token expired — please refresh and retry") from exc
    except (firebase_auth.InvalidIdTokenError, firebase_auth.RevokedIdTokenError) as exc:
        raise AuthenticationError("Invalid authentication token") from exc
    except Exception:
        logger.exception("firebase_token_verification_failed")
        raise AuthenticationError("Authentication failed") from None

    user = AuthenticatedUser(decoded)
    # Attach to request.state so middleware / other deps can access it
    request.state.user = user
    return user


# Convenient type alias for route signatures
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
