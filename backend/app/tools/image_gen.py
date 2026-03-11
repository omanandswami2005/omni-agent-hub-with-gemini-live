"""Image generation ADK tools — Imagen 4 primary, Gemini interleaved fallback.

Architecture (from RESEARCH_AND_PLAN §3 "Interleaved Output"):
    1. Tool calls Imagen 4 / Gemini interleaved API **separately** from the
       Live API session (the Live API is single-modality output).
    2. Saves generated images to GCS.
    3. Queues image data for delivery to the user's dashboard via WebSocket.
    4. Returns **text only** to the live agent → agent speaks the description.
       (Returning base64 would waste 100K+ tokens in Gemini's context window.)

The ``_pending_images`` queue is drained by ``_process_event()`` in
``ws_live.py`` when it sees the corresponding ``function_response`` event.
"""

from __future__ import annotations

import base64
import uuid
from typing import TYPE_CHECKING

from google import genai
from google.adk.tools import FunctionTool
from google.genai import types

from app.config import get_settings
from app.utils.logging import get_logger

if TYPE_CHECKING:
    from google.adk.tools.tool_context import ToolContext

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Pending-image queue (drained by ws_live._process_event)
# ---------------------------------------------------------------------------
# { user_id: [image_payload_dict, ...] }
_pending_images: dict[str, list[dict]] = {}

IMAGE_TOOL_NAMES = frozenset({"generate_image", "generate_rich_image"})


def _queue_image(user_id: str, payload: dict) -> None:
    """Enqueue an image for WebSocket delivery to *user_id*."""
    _pending_images.setdefault(user_id, []).append(payload)


def drain_pending_images(user_id: str) -> list[dict]:
    """Pop and return all pending images for *user_id*."""
    return _pending_images.pop(user_id, [])


# ---------------------------------------------------------------------------
# Clients (lazy)
# ---------------------------------------------------------------------------

_genai_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _genai_client
    if _genai_client is None:
        settings = get_settings()
        _genai_client = genai.Client(
            vertexai=settings.GOOGLE_GENAI_USE_VERTEXAI,
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        )
    return _genai_client


# ---------------------------------------------------------------------------
# Tool: generate_image (Imagen 4)
# ---------------------------------------------------------------------------

IMAGEN_MODEL = "imagen-4.0-generate-001"
GEMINI_IMAGE_MODEL = "gemini-2.0-flash-preview-image-generation"


async def generate_image(
    prompt: str,
    aspect_ratio: str = "1:1",
    style: str | None = None,
    tool_context: ToolContext | None = None,
) -> str:
    """Generate an image from a text prompt using Imagen 4.

    The generated image is saved to Cloud Storage and pushed to the
    user's dashboard. The live agent receives only a text summary
    so it can speak the result without bloating the context window.

    Args:
        prompt: Text description of the desired image.
        aspect_ratio: Aspect ratio (e.g. ``1:1``, ``16:9``, ``9:16``).
        style: Optional style modifier appended to prompt.

    Returns:
        A text summary describing what was generated (spoken by the agent).
    """
    full_prompt = f"{prompt}, {style}" if style else prompt

    client = _get_client()
    response = client.models.generate_images(
        model=IMAGEN_MODEL,
        prompt=full_prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio=aspect_ratio,
            safety_filter_level=types.SafetyFilterLevel.BLOCK_MEDIUM_AND_ABOVE,
        ),
    )

    if not response.generated_images:
        logger.warning("image_generation_empty", prompt=prompt)
        return "No images were generated — the prompt may have been filtered by safety settings."

    generated = response.generated_images[0]
    image_bytes = generated.image.image_bytes
    mime_type = generated.image.mime_type or "image/png"

    # Upload to GCS
    from app.services.storage_service import get_storage_service

    ext = mime_type.split("/")[-1]
    filename = f"{uuid.uuid4().hex}.{ext}"
    svc = get_storage_service()
    gcs_uri = svc.upload_image(image_bytes, filename=filename, content_type=mime_type)

    image_b64 = base64.b64encode(image_bytes).decode()

    logger.info(
        "image_generated",
        model=IMAGEN_MODEL,
        prompt=prompt[:80],
        gcs_uri=gcs_uri,
    )

    # Queue image for WebSocket delivery (NOT returned to Gemini)
    user_id = tool_context.user_id if tool_context else ""
    if user_id:
        _queue_image(user_id, {
            "tool_name": "generate_image",
            "image_base64": image_b64,
            "mime_type": mime_type,
            "image_url": gcs_uri,
            "description": full_prompt,
        })

    return (
        f"Successfully generated an image of: {full_prompt}. "
        "The image has been sent to the user's dashboard."
    )


# ---------------------------------------------------------------------------
# Tool: generate_rich_image (Gemini interleaved output)
# ---------------------------------------------------------------------------


async def generate_rich_image(
    prompt: str,
    tool_context: ToolContext | None = None,
) -> str:
    """Generate images with text context using Gemini's interleaved output.

    Unlike Imagen 4 (image-only), this can return mixed text + image
    content — useful for illustrated explanations, step-by-step visuals,
    etc.  Images are pushed to the dashboard; only a text summary is
    returned to the live agent.

    Args:
        prompt: Text description of the desired visual content.

    Returns:
        A text summary describing the generated content (spoken by the agent).
    """
    client = _get_client()
    response = client.models.generate_content(
        model=GEMINI_IMAGE_MODEL,
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
        ),
    )

    text_parts: list[str] = []
    images: list[dict] = []
    # Preserve interleaved order for dashboard rendering
    ordered_parts: list[dict] = []

    if response.candidates and response.candidates[0].content:
        for part in response.candidates[0].content.parts:
            if part.text:
                text_parts.append(part.text)
                ordered_parts.append({"type": "text", "content": part.text})
            elif part.inline_data:
                img_b64 = base64.b64encode(part.inline_data.data).decode()
                img_entry = {
                    "base64": img_b64,
                    "mime_type": part.inline_data.mime_type,
                }
                images.append(img_entry)
                ordered_parts.append({
                    "type": "image",
                    "base64": img_b64,
                    "mime_type": part.inline_data.mime_type,
                })

    # Persist images to GCS
    from app.services.storage_service import get_storage_service

    svc = get_storage_service()
    for img in images:
        ext = (img["mime_type"] or "image/png").split("/")[-1]
        filename = f"{uuid.uuid4().hex}.{ext}"
        raw = base64.b64decode(img["base64"])
        gcs_uri = svc.upload_image(raw, filename=filename, content_type=img["mime_type"])
        img["gcs_uri"] = gcs_uri

    summary = "\n".join(text_parts) or f"Generated {len(images)} image(s)."

    logger.info(
        "rich_image_generated",
        model=GEMINI_IMAGE_MODEL,
        prompt=prompt[:80],
        image_count=len(images),
    )

    # Queue images for WebSocket delivery (NOT returned to Gemini)
    user_id = tool_context.user_id if tool_context else ""
    if user_id:
        _queue_image(user_id, {
            "tool_name": "generate_rich_image",
            "text": summary,
            "images": images,
            "parts": ordered_parts,
        })

    img_count = len(images)
    return (
        f"{summary}\n\n"
        f"Generated {img_count} image{'s' if img_count != 1 else ''} "
        "and sent them to the user's dashboard."
    )


# ---------------------------------------------------------------------------
# Pre-built FunctionTool instances
# ---------------------------------------------------------------------------

generate_image_tool = FunctionTool(generate_image)
generate_rich_image_tool = FunctionTool(generate_rich_image)


def get_image_gen_tools() -> list[FunctionTool]:
    """Return image generation tools."""
    return [generate_image_tool, generate_rich_image_tool]
