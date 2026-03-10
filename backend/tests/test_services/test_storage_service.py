"""Tests for GCS storage service (Task 14)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.storage_service import StorageService, get_storage_service

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset storage service singleton between tests."""
    import app.services.storage_service as mod

    old = mod._service
    mod._service = None
    yield
    mod._service = old


@pytest.fixture()
def mock_bucket():
    """Return a mock GCS bucket with blob support."""
    bucket = MagicMock()
    blob = MagicMock()
    blob.download_as_bytes.return_value = b"file-content"
    blob.generate_signed_url.return_value = "https://storage.example.com/signed"
    bucket.blob.return_value = blob
    return bucket


@pytest.fixture()
def mock_client(mock_bucket):
    """Return a mock storage.Client."""
    client = MagicMock()
    client.bucket.return_value = mock_bucket
    blob_a = MagicMock()
    blob_a.name = "images/a.png"
    blob_b = MagicMock()
    blob_b.name = "images/b.png"
    client.list_blobs.return_value = [blob_a, blob_b]
    return client


@pytest.fixture()
def svc(mock_client):
    """Return a StorageService with mocked GCS client."""
    with patch("app.services.storage_service.storage.Client", return_value=mock_client):
        return StorageService()


# ── Upload tests ─────────────────────────────────────────────────────


class TestUploadBytes:
    def test_returns_gs_uri(self, svc):
        uri = svc.upload_bytes(b"data", "test/file.txt", "text/plain")
        assert uri.startswith("gs://")
        assert "test/file.txt" in uri

    def test_calls_upload_from_string(self, svc, mock_bucket):
        svc.upload_bytes(b"hello", "path/f.txt")
        mock_bucket.blob.assert_called_with("path/f.txt")
        mock_bucket.blob().upload_from_string.assert_called_once()


class TestUploadImage:
    def test_returns_gs_uri(self, svc):
        uri = svc.upload_image(b"\x89PNG", content_type="image/png")
        assert uri.startswith("gs://")
        assert "images/" in uri

    def test_uses_provided_filename(self, svc):
        uri = svc.upload_image(b"\x89PNG", filename="test.png")
        assert "test.png" in uri

    def test_generates_uuid_filename(self, svc):
        uri = svc.upload_image(b"\x89PNG")
        # UUID hex is 32 chars
        parts = uri.split("/")
        filename = parts[-1]
        assert len(filename) > 30  # uuid hex + .png


class TestUploadArtifact:
    def test_returns_gs_uri_with_session(self, svc):
        uri = svc.upload_artifact(b"data", "sess123", "output.csv")
        assert "artifacts/sess123/output.csv" in uri


# ── Download tests ───────────────────────────────────────────────────


class TestDownloadBytes:
    def test_returns_bytes(self, svc):
        data = svc.download_bytes("test/file.txt")
        assert data == b"file-content"

    def test_calls_download(self, svc, mock_bucket):
        svc.download_bytes("path/f.bin")
        mock_bucket.blob.assert_called_with("path/f.bin")
        mock_bucket.blob().download_as_bytes.assert_called_once()


# ── Signed URL tests ────────────────────────────────────────────────


class TestGenerateSignedUrl:
    def test_returns_url(self, svc):
        url = svc.generate_signed_url("images/pic.png")
        assert url == "https://storage.example.com/signed"

    def test_passes_expiry(self, svc, mock_bucket):
        svc.generate_signed_url("f.txt", expiry_minutes=30)
        call_kwargs = mock_bucket.blob().generate_signed_url.call_args[1]
        assert call_kwargs["method"] == "GET"


# ── List files tests ────────────────────────────────────────────────


class TestListFiles:
    def test_returns_file_names(self, svc):
        files = svc.list_files("images/")
        assert len(files) == 2
        assert "images/a.png" in files

    def test_calls_list_blobs(self, svc, mock_client):
        svc.list_files("prefix/")
        mock_client.list_blobs.assert_called_once()


# ── Singleton ────────────────────────────────────────────────────────


class TestSingleton:
    def test_returns_same_instance(self):
        with patch("app.services.storage_service.storage.Client"):
            svc1 = get_storage_service()
            svc2 = get_storage_service()
        assert svc1 is svc2
