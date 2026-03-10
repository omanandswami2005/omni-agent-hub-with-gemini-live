"""Tests for Firebase auth middleware and /api/v1/auth endpoints."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth_middleware import AuthenticatedUser, get_current_user

# ── Helpers ───────────────────────────────────────────────────────────

FAKE_DECODED_TOKEN = {
    "uid": "user_abc123",
    "email": "test@example.com",
    "name": "Test User",
    "picture": "https://example.com/photo.jpg",
}


def _fake_user() -> AuthenticatedUser:
    return AuthenticatedUser(FAKE_DECODED_TOKEN)


@pytest.fixture
def authed_client():
    """Test client with Firebase auth dependency overridden."""

    async def _override():
        return _fake_user()

    app.dependency_overrides[get_current_user] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    """Test client with NO auth override (real dependency)."""
    with TestClient(app) as c:
        yield c


# ── POST /api/v1/auth/verify ─────────────────────────────────────────


def test_verify_returns_user_profile(authed_client):
    resp = authed_client.post("/api/v1/auth/verify")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "user_abc123"
    assert data["email"] == "test@example.com"
    assert data["name"] == "Test User"
    assert data["picture"] == "https://example.com/photo.jpg"


def test_verify_without_token_returns_401(client):
    resp = client.post("/api/v1/auth/verify")
    assert resp.status_code == 401


# ── GET /api/v1/auth/me ──────────────────────────────────────────────


def test_me_returns_user_profile(authed_client):
    resp = authed_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "user_abc123"
    assert data["email"] == "test@example.com"


def test_me_without_token_returns_401(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


# ── Token edge cases (mocking Firebase Admin SDK) ─────────────────────


def test_expired_token_returns_401(client):
    from firebase_admin import auth as fb_auth

    with patch.object(
        fb_auth,
        "verify_id_token",
        side_effect=fb_auth.ExpiredIdTokenError("expired", cause=None),
    ):
        resp = client.post(
            "/api/v1/auth/verify",
            headers={"Authorization": "Bearer expired_token"},
        )
    assert resp.status_code == 401
    assert "expired" in resp.json()["message"].lower()


def test_invalid_token_returns_401(client):
    from firebase_admin import auth as fb_auth

    with patch.object(fb_auth, "verify_id_token", side_effect=fb_auth.InvalidIdTokenError("bad")):
        resp = client.post(
            "/api/v1/auth/verify",
            headers={"Authorization": "Bearer bad_token"},
        )
    assert resp.status_code == 401
    assert "invalid" in resp.json()["message"].lower()


def test_valid_token_returns_user(client):
    from firebase_admin import auth as fb_auth

    with patch.object(fb_auth, "verify_id_token", return_value=FAKE_DECODED_TOKEN):
        resp = client.post(
            "/api/v1/auth/verify",
            headers={"Authorization": "Bearer valid_token"},
        )
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "user_abc123"
