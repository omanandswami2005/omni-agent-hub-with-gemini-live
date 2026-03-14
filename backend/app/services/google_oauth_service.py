"""Google OAuth 2.0 service for per-user Google API access.

Handles the standard Google OAuth 2.0 authorization-code flow so that
each user can connect their own Google account.  Tokens are cached
in-memory and persisted to GCP Secret Manager via ``secret_service``.

Required env vars (from GCP Console > APIs & Services > Credentials):
  GOOGLE_OAUTH_CLIENT_ID
  GOOGLE_OAUTH_CLIENT_SECRET
"""

from __future__ import annotations

import contextlib
import os
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.services import secret_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_REVOKE_URL = "https://oauth2.googleapis.com/revoke"


@dataclass
class GoogleTokens:
    access_token: str
    refresh_token: str | None = None
    expires_at: float = 0.0
    scope: str = ""


class GoogleOAuthService:
    """Manages per-user Google OAuth tokens."""

    def __init__(self) -> None:
        # { (user_id, plugin_id): GoogleTokens }
        self._tokens: dict[tuple[str, str], GoogleTokens] = {}
        # { state_string: (user_id, plugin_id, scopes) }
        self._pending: dict[str, tuple[str, str, list[str]]] = {}

    # ── config ──────────────────────────────────────────────────────

    @staticmethod
    def _client_id() -> str:
        return os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")

    @staticmethod
    def _client_secret() -> str:
        return os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")

    @staticmethod
    def _redirect_uri() -> str:
        backend = os.environ.get("BACKEND_URL", "http://localhost:8000")
        return f"{backend}/api/v1/plugins/google-oauth/callback"

    # ── public API ──────────────────────────────────────────────────

    def start_flow(
        self,
        user_id: str,
        plugin_id: str,
        scopes: list[str],
    ) -> str:
        """Return the Google consent URL for the user to visit."""
        cid = self._client_id()
        if not cid:
            raise ValueError(
                "GOOGLE_OAUTH_CLIENT_ID is not configured. "
                "Create OAuth credentials in GCP Console > APIs & Services > Credentials "
                "and set the GOOGLE_OAUTH_CLIENT_ID environment variable."
            )

        state = secrets.token_urlsafe(32)
        self._pending[state] = (user_id, plugin_id, scopes)

        params = {
            "client_id": cid,
            "redirect_uri": self._redirect_uri(),
            "response_type": "code",
            "scope": " ".join(scopes),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{_AUTH_URL}?{urlencode(params)}"

    async def handle_callback(
        self,
        code: str,
        state: str,
    ) -> tuple[str, str]:
        """Exchange authorization code for tokens.

        Returns (user_id, plugin_id).
        """
        pending = self._pending.pop(state, None)
        if pending is None:
            raise ValueError("Invalid or expired OAuth state")

        user_id, plugin_id, _scopes = pending

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._client_id(),
                    "client_secret": self._client_secret(),
                    "redirect_uri": self._redirect_uri(),
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        tokens = GoogleTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=time.monotonic() + data.get("expires_in", 3600) - 60,
            scope=data.get("scope", ""),
        )
        key = (user_id, plugin_id)
        self._tokens[key] = tokens

        # Persist refresh token to Secret Manager
        if tokens.refresh_token:
            try:
                secret_service.store_secrets(
                    user_id,
                    f"{plugin_id}-google-oauth",
                    {
                        "refresh_token": tokens.refresh_token,
                        "scope": tokens.scope,
                    },
                )
            except Exception:
                logger.warning(
                    "google_oauth_persist_failed",
                    user_id=user_id,
                    plugin_id=plugin_id,
                    exc_info=True,
                )

        logger.info("google_oauth_tokens_received", user_id=user_id, plugin_id=plugin_id)
        return user_id, plugin_id

    async def get_valid_token(self, user_id: str, plugin_id: str) -> str | None:
        """Return a valid access token, refreshing if needed."""
        key = (user_id, plugin_id)
        tokens = self._tokens.get(key)

        # Try loading from Secret Manager if not in memory
        if tokens is None:
            tokens = self._load_from_secret_manager(user_id, plugin_id)
            if tokens:
                self._tokens[key] = tokens

        if tokens is None:
            return None

        # Refresh if expired
        if tokens.expires_at < time.monotonic() and tokens.refresh_token:
            refreshed = await self._refresh(tokens.refresh_token)
            if refreshed:
                tokens.access_token = refreshed.access_token
                tokens.expires_at = refreshed.expires_at
                if refreshed.refresh_token:
                    tokens.refresh_token = refreshed.refresh_token
            else:
                return None

        return tokens.access_token

    def has_tokens(self, user_id: str, plugin_id: str) -> bool:
        key = (user_id, plugin_id)
        if key in self._tokens:
            return True
        loaded = self._load_from_secret_manager(user_id, plugin_id)
        if loaded:
            self._tokens[key] = loaded
            return True
        return False

    def revoke(self, user_id: str, plugin_id: str) -> None:
        key = (user_id, plugin_id)
        tokens = self._tokens.pop(key, None)
        if tokens and tokens.refresh_token:
            with contextlib.suppress(Exception):
                httpx.post(_REVOKE_URL, params={"token": tokens.refresh_token}, timeout=5)
        with contextlib.suppress(Exception):
            secret_service.delete_secrets(user_id, f"{plugin_id}-google-oauth")
        logger.info("google_oauth_revoked", user_id=user_id, plugin_id=plugin_id)

    # ── internal ────────────────────────────────────────────────────

    def _load_from_secret_manager(self, user_id: str, plugin_id: str) -> GoogleTokens | None:
        try:
            data = secret_service.load_secrets(user_id, f"{plugin_id}-google-oauth")
            if data.get("refresh_token"):
                return GoogleTokens(
                    access_token="",  # needs refresh
                    refresh_token=data["refresh_token"],
                    expires_at=0,
                    scope=data.get("scope", ""),
                )
        except Exception:
            pass
        return None

    async def _refresh(self, refresh_token: str) -> GoogleTokens | None:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    _TOKEN_URL,
                    data={
                        "client_id": self._client_id(),
                        "client_secret": self._client_secret(),
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            return GoogleTokens(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token"),
                expires_at=time.monotonic() + data.get("expires_in", 3600) - 60,
                scope=data.get("scope", ""),
            )
        except Exception:
            logger.warning("google_oauth_refresh_failed", exc_info=True)
            return None


# ── singleton ──────────────────────────────────────────────────────

_instance: GoogleOAuthService | None = None


def get_google_oauth_service() -> GoogleOAuthService:
    global _instance
    if _instance is None:
        _instance = GoogleOAuthService()
    return _instance
