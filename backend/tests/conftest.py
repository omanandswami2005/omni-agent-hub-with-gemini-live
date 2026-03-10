"""Pytest fixtures — FastAPI test client, mock Firebase, mock ADK."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Synchronous test client for FastAPI."""
    with TestClient(app) as c:
        yield c
