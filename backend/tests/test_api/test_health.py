"""Tests for GET /health endpoint."""


def test_root_health_returns_200(client):
    """Root /health endpoint responds with correct schema."""
    resp = client.get("/health")
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "omni-agent-hub"
    assert "version" in data
    assert "environment" in data
    assert "uptime_seconds" in data
    assert isinstance(data["uptime_seconds"], (int, float))


def test_api_v1_health_returns_200(client):
    """/api/v1/health endpoint also responds healthy."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_health_contains_version(client):
    """Health response includes the app version."""
    resp = client.get("/health")
    data = resp.json()
    assert data["version"] == "0.1.0"


def test_nonexistent_route_returns_404(client):
    """Unknown route returns 404."""
    resp = client.get("/api/v1/nonexistent")
    assert resp.status_code == 404
