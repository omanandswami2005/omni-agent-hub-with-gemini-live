"""GCS storage service — upload/download files, generate signed URLs.

All operations target the bucket configured in ``settings.GCS_BUCKET_NAME``.
"""

from __future__ import annotations

import datetime
import uuid

import google.auth
from google.auth.transport import requests as google_auth_requests
from google.cloud import storage

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class StorageService:
    """Thin wrapper around ``google.cloud.storage`` for the project bucket."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = storage.Client(project=settings.GOOGLE_CLOUD_PROJECT)
        self._bucket_name = settings.GCS_BUCKET_NAME
        self._bucket = self._client.bucket(self._bucket_name)

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def upload_bytes(
        self,
        data: bytes,
        destination: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload *data* to *destination* path and return the ``gs://`` URI."""
        blob = self._bucket.blob(destination)
        blob.upload_from_string(data, content_type=content_type)
        uri = f"gs://{self._bucket_name}/{destination}"
        logger.info("file_uploaded", destination=destination, size=len(data))
        return uri

    def upload_image(
        self,
        image_bytes: bytes,
        *,
        user_id: str,
        folder: str = "images",
        filename: str | None = None,
        content_type: str = "image/png",
    ) -> str:
        """Upload an image and return its ``gs://`` URI.

        Images are stored under ``<folder>/<user_id>/<filename>`` so each
        user's media is isolated.  If *filename* is not provided a UUID is
        generated.
        """
        if filename is None:
            ext = content_type.split("/")[-1]
            filename = f"{uuid.uuid4().hex}.{ext}"
        destination = f"{folder}/{user_id}/{filename}"
        return self.upload_bytes(image_bytes, destination, content_type)

    def upload_artifact(
        self,
        data: bytes,
        session_id: str,
        filename: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload a session artifact to ``artifacts/<session_id>/``."""
        destination = f"artifacts/{session_id}/{filename}"
        return self.upload_bytes(data, destination, content_type)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download_bytes(self, path: str) -> bytes:
        """Download a blob by its path (relative to bucket root)."""
        blob = self._bucket.blob(path)
        return blob.download_as_bytes()

    # ------------------------------------------------------------------
    # Signed URLs
    # ------------------------------------------------------------------

    def generate_signed_url(
        self,
        path: str,
        *,
        expiry_minutes: int = 60,
    ) -> str:
        """Generate a temporary signed URL for *path*.

        On Cloud Run (Workload Identity / ADC), private-key signing is not
        available so we pass the refreshed access token + service account email
        to the v4 signing call, which uses the IAM ``signBlob`` API instead.
        """
        blob = self._bucket.blob(path)
        expiration = datetime.timedelta(minutes=expiry_minutes)

        # First try: plain v4 (works when running with an explicit SA key file)
        try:
            return blob.generate_signed_url(
                version="v4",
                expiration=expiration,
                method="GET",
            )
        except Exception:
            pass

        # Second try: IAM-based signing (works on Cloud Run / GCE / GKE)
        try:
            credentials, _ = google.auth.default()
            request = google_auth_requests.Request()
            credentials.refresh(request)
            return blob.generate_signed_url(
                version="v4",
                expiration=expiration,
                method="GET",
                service_account_email=credentials.service_account_email,
                access_token=credentials.token,
            )
        except Exception:
            raise  # let gallery.py handle the fallback

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_files(self, prefix: str = "") -> list[str]:
        """List blob names under *prefix*."""
        blobs = self._client.list_blobs(self._bucket_name, prefix=prefix)
        return [b.name for b in blobs]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_service: StorageService | None = None


def get_storage_service() -> StorageService:
    """Return the global storage service instance."""
    global _service
    if _service is None:
        _service = StorageService()
    return _service
