"""GCP Secret Manager service for secure user secret storage.

Stores user-provided API keys/tokens in GCP Secret Manager instead
of in-memory dicts, so secrets persist across restarts and are properly
encrypted at rest by Google Cloud.

Secret naming convention:
    omni_plugin_{user_id_hash}_{plugin_id}

Each secret's payload is a JSON blob: {"KEY1": "val1", "KEY2": "val2"}.
"""

from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache

from app.utils.logging import get_logger

logger = get_logger(__name__)

_PREFIX = "omni-plugin"


def _user_hash(user_id: str) -> str:
    """Short deterministic hash of user_id for secret naming."""
    return hashlib.sha256(user_id.encode()).hexdigest()[:12]


def _secret_id(user_id: str, plugin_id: str) -> str:
    """Build a GCP-safe secret ID: lowercase alphanumeric + hyphens."""
    return f"{_PREFIX}-{_user_hash(user_id)}-{plugin_id}"


@lru_cache(maxsize=1)
def _get_client():
    """Lazy-init Secret Manager client."""
    from google.cloud import secretmanager

    return secretmanager.SecretManagerServiceClient()


def _project_id() -> str:
    return os.environ.get("GOOGLE_CLOUD_PROJECT", "")


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def store_secrets(user_id: str, plugin_id: str, secrets: dict[str, str]) -> None:
    """Store (or update) secrets for a user+plugin in Secret Manager."""
    client = _get_client()
    project = _project_id()
    sid = _secret_id(user_id, plugin_id)
    parent = f"projects/{project}"
    secret_path = f"{parent}/secrets/{sid}"

    payload = json.dumps(secrets).encode("utf-8")

    # Create the secret resource if it doesn't exist
    try:
        client.get_secret(request={"name": secret_path})
    except Exception:
        # Secret doesn't exist — create it
        client.create_secret(
            request={
                "parent": parent,
                "secret_id": sid,
                "secret": {"replication": {"automatic": {}}},
            },
        )
        logger.info("secret_created", secret_id=sid)

    # Add a new version with the latest payload
    client.add_secret_version(
        request={
            "parent": secret_path,
            "payload": {"data": payload},
        },
    )
    logger.info("secret_version_added", secret_id=sid, plugin_id=plugin_id)


def load_secrets(user_id: str, plugin_id: str) -> dict[str, str]:
    """Load the latest secrets for a user+plugin. Returns {} if not found."""
    client = _get_client()
    project = _project_id()
    sid = _secret_id(user_id, plugin_id)
    version_path = f"projects/{project}/secrets/{sid}/versions/latest"

    try:
        response = client.access_secret_version(request={"name": version_path})
        return json.loads(response.payload.data.decode("utf-8"))
    except Exception:
        return {}


def delete_secrets(user_id: str, plugin_id: str) -> bool:
    """Delete all secret versions for a user+plugin. Returns True if deleted."""
    client = _get_client()
    project = _project_id()
    sid = _secret_id(user_id, plugin_id)
    secret_path = f"projects/{project}/secrets/{sid}"

    try:
        client.delete_secret(request={"name": secret_path})
        logger.info("secret_deleted", secret_id=sid)
        return True
    except Exception:
        return False
