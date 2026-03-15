"""OAuth 2.0 service for MCP_OAUTH plugins.

Implements the standard MCP authorization flow:
  1. RFC 9470 — Protected Resource Metadata discovery
  2. RFC 8414 — Authorization Server Metadata discovery
  3. RFC 7591 — Dynamic Client Registration
  4. RFC 7636 — PKCE (Proof Key for Code Exchange)
  5. OAuth 2.0 Authorization Code → Token Exchange → Refresh

Scalable across all MCP servers that follow the spec (Notion, Slack, etc.).
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from base64 import urlsafe_b64encode
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services import secret_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ── Token data ──────────────────────────────────────────────────────────


@dataclass
class OAuthTokens:
    """Stored OAuth 2.0 tokens for a user+plugin pair."""

    access_token: str
    token_type: str = "Bearer"
    refresh_token: str | None = None
    expires_at: float = 0.0  # monotonic timestamp
    scope: str = ""


@dataclass
class OAuthMetadata:
    """Discovered OAuth server metadata."""

    issuer: str = ""
    authorization_endpoint: str = ""
    token_endpoint: str = ""
    registration_endpoint: str = ""
    code_challenge_methods_supported: list[str] = field(default_factory=list)


@dataclass
class ClientCredentials:
    """Dynamically registered client credentials."""

    client_id: str = ""
    client_secret: str | None = None


@dataclass
class PendingOAuthFlow:
    """Temporary state for an in-progress OAuth authorization."""

    plugin_id: str
    user_id: str
    code_verifier: str
    state: str
    redirect_uri: str
    metadata: OAuthMetadata
    client_creds: ClientCredentials


# ── PKCE helpers ────────────────────────────────────────────────────────


def _generate_code_verifier() -> str:
    """Generate a high-entropy PKCE code verifier (43-128 chars, URL-safe)."""
    return urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()


def _generate_code_challenge(verifier: str) -> str:
    """S256 code challenge from verifier."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return urlsafe_b64encode(digest).rstrip(b"=").decode()


# ── Service ─────────────────────────────────────────────────────────────


class OAuthService:
    """Manages OAuth flows and token storage for MCP_OAUTH plugins."""

    def __init__(self) -> None:
        # Pending flows: { state_token: PendingOAuthFlow }
        self._pending: dict[str, PendingOAuthFlow] = {}
        # Stored tokens: { (user_id, plugin_id): OAuthTokens }
        self._tokens: dict[tuple[str, str], OAuthTokens] = {}
        # Cached metadata: { mcp_server_url: OAuthMetadata }
        self._metadata_cache: dict[str, OAuthMetadata] = {}
        # Cached client creds: { (mcp_server_url, client_name): ClientCredentials }
        self._client_cache: dict[tuple[str, str], ClientCredentials] = {}

    # ── Secret Manager helpers ──────────────────────────────────

    def _save_to_secret_manager(
        self,
        user_id: str,
        plugin_id: str,
        tokens: OAuthTokens,
        client_creds: ClientCredentials | None = None,
        token_endpoint: str = "",
        issuer: str = "",
    ) -> None:
        """Persist OAuth tokens + client credentials to GCP Secret Manager."""
        # Convert monotonic expires_at → wall-clock unix time for portability
        if tokens.expires_at > 0:
            expires_at_unix = time.time() + max(0.0, tokens.expires_at - time.monotonic())
        else:
            expires_at_unix = 0.0

        data: dict[str, str] = {
            "access_token": tokens.access_token,
            "token_type": tokens.token_type,
            "expires_at_unix": str(expires_at_unix),
            "scope": tokens.scope,
        }
        if tokens.refresh_token:
            data["refresh_token"] = tokens.refresh_token
        if client_creds:
            data["client_id"] = client_creds.client_id
            if client_creds.client_secret:
                data["client_secret"] = client_creds.client_secret
        if token_endpoint:
            data["token_endpoint"] = token_endpoint
        if issuer:
            data["issuer"] = issuer

        try:
            secret_service.store_secrets(user_id, f"{plugin_id}-mcp-oauth", data)
            logger.info("mcp_oauth_persisted", user_id=user_id, plugin_id=plugin_id)
        except Exception:
            logger.warning(
                "mcp_oauth_persist_failed",
                user_id=user_id,
                plugin_id=plugin_id,
                exc_info=True,
            )

    def _load_from_secret_manager(
        self, user_id: str, plugin_id: str
    ) -> tuple[OAuthTokens, ClientCredentials | None, str, str] | None:
        """Load OAuth tokens + client credentials from GCP Secret Manager.

        Returns (tokens, client_creds, token_endpoint, issuer) or None if not found.
        """
        try:
            data = secret_service.load_secrets(user_id, f"{plugin_id}-mcp-oauth")
            if not data.get("access_token") and not data.get("refresh_token"):
                return None

            # Convert wall-clock unix time back to monotonic for in-process use
            expires_at_unix = float(data.get("expires_at_unix", "0"))
            if expires_at_unix > 0:
                expires_at = time.monotonic() + max(0.0, expires_at_unix - time.time())
            else:
                expires_at = 0.0

            tokens = OAuthTokens(
                access_token=data.get("access_token", ""),
                token_type=data.get("token_type", "Bearer"),
                refresh_token=data.get("refresh_token") or None,
                expires_at=expires_at,
                scope=data.get("scope", ""),
            )
            client_creds: ClientCredentials | None = None
            if data.get("client_id"):
                client_creds = ClientCredentials(
                    client_id=data["client_id"],
                    client_secret=data.get("client_secret") or None,
                )
            token_endpoint = data.get("token_endpoint", "")
            issuer = data.get("issuer", "")
            logger.info("mcp_oauth_loaded_from_sm", user_id=user_id, plugin_id=plugin_id)
            return tokens, client_creds, token_endpoint, issuer
        except Exception:
            return None

    # ── Discovery ───────────────────────────────────────────────────

    async def discover_oauth_metadata(self, mcp_server_url: str) -> OAuthMetadata:
        """RFC 9470 + RFC 8414 discovery: find auth endpoints for an MCP server."""
        cached = self._metadata_cache.get(mcp_server_url)
        if cached:
            return cached

        parsed = urlparse(mcp_server_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # Candidate URLs for RFC 9470 Protected Resource Metadata:
        # 1. Path-specific (e.g. https://host/mcp/.well-known/oauth-protected-resource)
        # 2. Base origin  (e.g. https://host/.well-known/oauth-protected-resource)
        pr_candidates = [
            mcp_server_url.rstrip("/") + "/.well-known/oauth-protected-resource",
            base_url.rstrip("/") + "/.well-known/oauth-protected-resource",
        ]

        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            # Step 1: RFC 9470 — Protected Resource Metadata
            pr_data: dict[str, Any] | None = None
            for pr_url in pr_candidates:
                resp = await client.get(pr_url)
                if resp.status_code == 200:
                    pr_data = resp.json()
                    break

            if pr_data is None:
                raise RuntimeError(
                    f"Failed to fetch protected resource metadata for {mcp_server_url}"
                )
            auth_servers = pr_data.get("authorization_servers", [])
            if not auth_servers:
                raise RuntimeError("No authorization_servers in protected resource metadata")
            auth_server_url = auth_servers[0]

            # Step 2: RFC 8414 — Authorization Server Metadata
            as_url = auth_server_url.rstrip("/") + "/.well-known/oauth-authorization-server"
            resp = await client.get(as_url)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Failed to fetch auth server metadata from {as_url}: {resp.status_code}"
                )
            as_data = resp.json()

        metadata = OAuthMetadata(
            issuer=as_data.get("issuer", auth_server_url),
            authorization_endpoint=as_data.get("authorization_endpoint", ""),
            token_endpoint=as_data.get("token_endpoint", ""),
            registration_endpoint=as_data.get("registration_endpoint", ""),
            code_challenge_methods_supported=as_data.get("code_challenge_methods_supported", []),
        )
        if not metadata.authorization_endpoint or not metadata.token_endpoint:
            raise RuntimeError("Missing required OAuth endpoints in server metadata")

        self._metadata_cache[mcp_server_url] = metadata
        logger.info("oauth_metadata_discovered", mcp_url=mcp_server_url, issuer=metadata.issuer)
        return metadata

    # ── Dynamic Client Registration ──────────────────────────────

    async def register_client(
        self,
        metadata: OAuthMetadata,
        client_name: str,
        redirect_uri: str,
    ) -> ClientCredentials:
        """RFC 7591 — Register this application with the OAuth server."""
        cache_key = (metadata.issuer, client_name)
        cached = self._client_cache.get(cache_key)
        if cached:
            return cached

        if not metadata.registration_endpoint:
            raise RuntimeError("Server does not support dynamic client registration")

        payload = {
            "client_name": client_name,
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }

        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.post(
                metadata.registration_endpoint,
                json=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Client registration failed: {resp.status_code} — {resp.text}")
            data = resp.json()

        creds = ClientCredentials(
            client_id=data["client_id"],
            client_secret=data.get("client_secret"),
        )
        self._client_cache[cache_key] = creds
        logger.info("oauth_client_registered", issuer=metadata.issuer, client_id=creds.client_id)
        return creds

    # ── Start OAuth Flow ────────────────────────────────────────

    async def start_oauth_flow(
        self,
        plugin_id: str,
        user_id: str,
        mcp_server_url: str,
        client_name: str = "Omni Hub",
        scopes: list[str] | None = None,
        redirect_uri: str = "",
    ) -> str:
        """Begin OAuth authorization. Returns the authorization URL to redirect the user to."""
        if not redirect_uri:
            backend_base = os.environ.get("BACKEND_URL", "http://localhost:8000")
            redirect_uri = f"{backend_base}/api/v1/plugins/oauth/callback"

        # Discover OAuth endpoints
        metadata = await self.discover_oauth_metadata(mcp_server_url)

        # Register client (or use cached)
        client_creds = await self.register_client(metadata, client_name, redirect_uri)

        # Generate PKCE
        code_verifier = _generate_code_verifier()
        code_challenge = _generate_code_challenge(code_verifier)
        state = secrets.token_urlsafe(32)

        # Build authorization URL
        params = {
            "response_type": "code",
            "client_id": client_creds.client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
        if scopes:
            params["scope"] = " ".join(scopes)

        auth_url = str(httpx.URL(metadata.authorization_endpoint).copy_with(params=params))

        # Store pending flow
        self._pending[state] = PendingOAuthFlow(
            plugin_id=plugin_id,
            user_id=user_id,
            code_verifier=code_verifier,
            state=state,
            redirect_uri=redirect_uri,
            metadata=metadata,
            client_creds=client_creds,
        )

        logger.info("oauth_flow_started", plugin_id=plugin_id, user_id=user_id)
        return auth_url

    # ── Handle Callback ─────────────────────────────────────────

    async def handle_callback(self, code: str, state: str) -> tuple[str, str]:
        """Exchange authorization code for tokens. Returns (user_id, plugin_id)."""
        flow = self._pending.pop(state, None)
        if flow is None:
            raise ValueError("Invalid or expired OAuth state")

        # Exchange code for tokens
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": flow.client_creds.client_id,
            "redirect_uri": flow.redirect_uri,
            "code_verifier": flow.code_verifier,
        }
        if flow.client_creds.client_secret:
            payload["client_secret"] = flow.client_creds.client_secret

        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.post(
                flow.metadata.token_endpoint,
                data=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Token exchange failed: {resp.status_code} — {resp.text}")
            data = resp.json()

        if not data.get("access_token"):
            raise RuntimeError("Missing access_token in token response")

        expires_in = data.get("expires_in", 3600)
        tokens = OAuthTokens(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            refresh_token=data.get("refresh_token"),
            expires_at=time.monotonic() + expires_in - 60,  # 60s safety margin
            scope=data.get("scope", ""),
        )

        key = (flow.user_id, flow.plugin_id)
        self._tokens[key] = tokens

        # Persist to Secret Manager so tokens survive redeployment
        self._save_to_secret_manager(
            flow.user_id,
            flow.plugin_id,
            tokens,
            flow.client_creds,
            flow.metadata.token_endpoint,
            flow.metadata.issuer,
        )

        logger.info("oauth_tokens_received", plugin_id=flow.plugin_id, user_id=flow.user_id)
        return flow.user_id, flow.plugin_id

    # ── Token Access ────────────────────────────────────────────

    def get_access_token(self, user_id: str, plugin_id: str) -> str | None:
        """Return the current access token, or None if not authenticated."""
        key = (user_id, plugin_id)
        tokens = self._tokens.get(key)
        if tokens is None:
            loaded = self._load_from_secret_manager(user_id, plugin_id)
            if loaded:
                tokens, client_creds, _ep, issuer = loaded
                self._tokens[key] = tokens
                if client_creds and issuer:
                    self._client_cache[(issuer, "Omni Hub")] = client_creds
        if tokens is None:
            return None
        return tokens.access_token

    def has_valid_token(self, user_id: str, plugin_id: str) -> bool:
        """Check if we have a non-expired token."""
        key = (user_id, plugin_id)
        tokens = self._tokens.get(key)
        if tokens is None:
            loaded = self._load_from_secret_manager(user_id, plugin_id)
            if loaded:
                tokens, client_creds, _ep, issuer = loaded
                self._tokens[key] = tokens
                if client_creds and issuer:
                    self._client_cache[(issuer, "Omni Hub")] = client_creds
        if tokens is None:
            return False
        return not (tokens.expires_at and time.monotonic() > tokens.expires_at)

    async def refresh_token_if_needed(
        self,
        user_id: str,
        plugin_id: str,
        mcp_server_url: str,
    ) -> str | None:
        """Refresh the access token if expired. Returns the (possibly new) access token."""
        key = (user_id, plugin_id)
        tokens = self._tokens.get(key)

        # Load from Secret Manager if not in memory (e.g. after a redeployment)
        _sm_client_creds: ClientCredentials | None = None
        _sm_token_endpoint: str = ""
        _sm_issuer: str = ""
        if tokens is None:
            loaded = self._load_from_secret_manager(user_id, plugin_id)
            if loaded:
                tokens, _sm_client_creds, _sm_token_endpoint, _sm_issuer = loaded
                self._tokens[key] = tokens
                if _sm_client_creds and _sm_issuer:
                    self._client_cache[(_sm_issuer, "Omni Hub")] = _sm_client_creds

        if tokens is None:
            return None

        # Not expired yet
        if tokens.expires_at and time.monotonic() < tokens.expires_at:
            return tokens.access_token

        # No refresh token — can't refresh
        if not tokens.refresh_token:
            self._tokens.pop(key, None)
            return None

        # Use stored token_endpoint from Secret Manager if available (survives redeployment).
        # Fall back to re-discovery only when Secret Manager data is unavailable.
        token_endpoint = _sm_token_endpoint
        issuer = _sm_issuer
        client_creds: ClientCredentials | None = _sm_client_creds

        if not token_endpoint:
            try:
                metadata = await self.discover_oauth_metadata(mcp_server_url)
                token_endpoint = metadata.token_endpoint
                issuer = metadata.issuer
            except Exception:
                logger.warning(
                    "oauth_discovery_failed_no_stored_endpoint",
                    plugin_id=plugin_id,
                    user_id=user_id,
                )
                self._tokens.pop(key, None)
                return None

        # Find client credentials (in-memory cache first, then Secret Manager fallback)
        if client_creds is None:
            for cache_key, creds in self._client_cache.items():
                if cache_key[0] == issuer:
                    client_creds = creds
                    break
        if client_creds is None:
            self._tokens.pop(key, None)
            return None

        payload: dict[str, Any] = {
            "grant_type": "refresh_token",
            "refresh_token": tokens.refresh_token,
            "client_id": client_creds.client_id,
        }
        if client_creds.client_secret:
            payload["client_secret"] = client_creds.client_secret

        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.post(
                token_endpoint,
                data=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
            )
            if resp.status_code != 200:
                logger.warning("oauth_refresh_failed", status=resp.status_code, body=resp.text)
                self._tokens.pop(key, None)
                return None
            data = resp.json()

        expires_in = data.get("expires_in", 3600)
        new_tokens = OAuthTokens(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            refresh_token=data.get("refresh_token", tokens.refresh_token),
            expires_at=time.monotonic() + expires_in - 60,
            scope=data.get("scope", tokens.scope),
        )
        self._tokens[key] = new_tokens

        # Persist refreshed tokens to Secret Manager
        self._save_to_secret_manager(
            user_id,
            plugin_id,
            new_tokens,
            client_creds,
            token_endpoint,
            issuer,
        )

        logger.info("oauth_token_refreshed", plugin_id=plugin_id, user_id=user_id)
        return new_tokens.access_token

    def revoke_tokens(self, user_id: str, plugin_id: str) -> None:
        """Remove stored tokens for a user+plugin."""
        self._tokens.pop((user_id, plugin_id), None)
        try:
            secret_service.delete_secrets(user_id, f"{plugin_id}-mcp-oauth")
        except Exception:
            logger.warning(
                "mcp_oauth_revoke_sm_failed",
                user_id=user_id,
                plugin_id=plugin_id,
                exc_info=True,
            )


# ── Module-level singleton ──────────────────────────────────────────────

_oauth_service: OAuthService | None = None


def get_oauth_service() -> OAuthService:
    """Return the global OAuth service instance."""
    global _oauth_service
    if _oauth_service is None:
        _oauth_service = OAuthService()
    return _oauth_service
