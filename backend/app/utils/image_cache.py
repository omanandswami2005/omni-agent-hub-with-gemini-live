"""Lightweight per-user image cache for forwarding uploads through AgentTool.

When users send images via chat/voice, they land in the root agent's live
stream but are lost when AgentTool delegates to a sub-agent (it only
forwards the text ``request`` parameter).  This module stores the most
recent image per user so that ``MultimodalAgentTool`` can inject it into
the sub-agent's Content.

Usage
-----
- **ws_live.py** calls ``cache_user_image(user_id, blob)`` on each upload.
- ``MultimodalAgentTool.run_async`` calls ``pop_user_image(user_id)`` to
  retrieve (and clear) the cached image when building the request Content.
"""

from __future__ import annotations

from google.genai import types

# {user_id: types.Blob}  — only the most recent image is kept.
_image_cache: dict[str, types.Blob] = {}


def cache_user_image(user_id: str, blob: types.Blob) -> None:
    """Store the latest user-uploaded image (replaces any previous one)."""
    _image_cache[user_id] = blob


def pop_user_image(user_id: str) -> types.Blob | None:
    """Return and remove the cached image for *user_id*, or ``None``."""
    return _image_cache.pop(user_id, None)
