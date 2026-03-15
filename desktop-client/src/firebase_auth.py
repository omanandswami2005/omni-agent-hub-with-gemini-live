"""Firebase Auth client for the desktop app.

Uses the Firebase Auth REST API (identitytoolkit) so we avoid pulling
in the full Firebase Python Admin SDK.  Supports:
  - Email / password sign-in & sign-up
  - Token refresh via the securetoken endpoint
"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

_SIGN_IN_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
)
_SIGN_UP_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signUp"
)
_REFRESH_URL = "https://securetoken.googleapis.com/v1/token"
_LOOKUP_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:lookup"
)


class AuthResult:
    """Holds the result of a Firebase auth operation."""

    __slots__ = (
        "id_token", "refresh_token", "user_id", "email",
        "display_name", "expires_at",
    )

    def __init__(
        self,
        id_token: str,
        refresh_token: str,
        user_id: str,
        email: str,
        display_name: str = "",
        expires_in: int = 3600,
    ) -> None:
        self.id_token = id_token
        self.refresh_token = refresh_token
        self.user_id = user_id
        self.email = email
        self.display_name = display_name
        self.expires_at = time.time() + expires_in

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at - 60  # 1-min safety margin


class FirebaseAuth:
    """Stateless helper that talks to Firebase Auth REST endpoints."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    # ── sign-in / sign-up ─────────────────────────────────────────

    def sign_in(self, email: str, password: str) -> AuthResult:
        """Sign in with email + password.  Raises on failure."""
        resp = httpx.post(
            _SIGN_IN_URL,
            params={"key": self.api_key},
            json={
                "email": email,
                "password": password,
                "returnSecureToken": True,
            },
            timeout=15,
        )
        return self._handle_response(resp)

    def sign_up(self, email: str, password: str) -> AuthResult:
        """Create a new account with email + password."""
        resp = httpx.post(
            _SIGN_UP_URL,
            params={"key": self.api_key},
            json={
                "email": email,
                "password": password,
                "returnSecureToken": True,
            },
            timeout=15,
        )
        return self._handle_response(resp)

    def refresh_token(self, refresh_tok: str) -> AuthResult:
        """Exchange a refresh token for a new id token."""
        resp = httpx.post(
            _REFRESH_URL,
            params={"key": self.api_key},
            json={
                "grant_type": "refresh_token",
                "refresh_token": refresh_tok,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            body = resp.json()
            err = body.get("error", {}).get("message", resp.text)
            raise RuntimeError(f"Token refresh failed: {err}")
        data = resp.json()
        return AuthResult(
            id_token=data["id_token"],
            refresh_token=data["refresh_token"],
            user_id=data["user_id"],
            email="",  # refresh response doesn't include email
            expires_in=int(data.get("expires_in", 3600)),
        )

    # ── internals ─────────────────────────────────────────────────

    @staticmethod
    def _handle_response(resp: httpx.Response) -> AuthResult:
        if resp.status_code != 200:
            body = resp.json()
            code = body.get("error", {}).get("message", "UNKNOWN_ERROR")
            raise RuntimeError(_friendly_error(code))
        data = resp.json()
        return AuthResult(
            id_token=data["idToken"],
            refresh_token=data["refreshToken"],
            user_id=data["localId"],
            email=data.get("email", ""),
            display_name=data.get("displayName", ""),
            expires_in=int(data.get("expiresIn", 3600)),
        )


def _friendly_error(code: str) -> str:
    """Map Firebase error codes to human-readable messages."""
    _MAP = {
        "EMAIL_NOT_FOUND": "No account found with that email.",
        "INVALID_PASSWORD": "Incorrect password.",
        "INVALID_LOGIN_CREDENTIALS": "Invalid email or password.",
        "USER_DISABLED": "This account has been disabled.",
        "EMAIL_EXISTS": "An account with this email already exists.",
        "WEAK_PASSWORD": "Password must be at least 6 characters.",
        "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many failed attempts. Try again later.",
        "INVALID_EMAIL": "Please enter a valid email address.",
    }
    return _MAP.get(code, f"Authentication failed ({code})")
