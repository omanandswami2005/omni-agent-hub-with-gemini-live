"""Image generation ADK tools — Imagen 4 primary, Gemini interleaved fallback.

``generate_image`` calls Imagen 4 via Vertex AI, saves the result to GCS,
pushes it to the user's dashboard via WebSocket, and returns a text
summary to the live agent (which speaks it to the user).

``generate_rich_image`` uses Gemini's interleaved output model for
text+image responses when richer context is needed.
"""

from __future__ import annotations

import base64
import uuid

from google import genai
from google.adk.tools import FunctionTool
from google.genai import types

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

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
) -> dict:
    """Generate an image from a text prompt using Imagen 4.

    The generated image is saved to Cloud Storage and its details are
    returned so the dashboard can display it.

    Args:
        prompt: Text description of the desired image.
        aspect_ratio: Aspect ratio (e.g. ``1:1``, ``16:9``, ``9:16``).
        style: Optional style modifier appended to prompt.

    Returns:
        A dict with ``image_url``, ``mime_type``, ``description``, and
        ``image_base64`` (for dashboard rendering).
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
        return {"error": "No images generated — prompt may have been filtered."}

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

    return {
        "image_url": gcs_uri,
        "mime_type": mime_type,
        "description": full_prompt,
        "image_base64": image_b64,
    }


# ---------------------------------------------------------------------------
# Tool: generate_rich_image (Gemini interleaved output)
# ---------------------------------------------------------------------------


async def generate_rich_image(
    prompt: str,
) -> dict:
    """Generate an image with text context using Gemini's interleaved output.

    Unlike Imagen 4 (image-only), this can return mixed text + image
    content — useful for illustrated explanations, step-by-step visuals,
    etc.

    Args:
        prompt: Text description of the desired visual content.

    Returns:
        A dict with ``text``, ``images`` (list of base64), and ``image_count``.
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

    if response.candidates and response.candidates[0].content:
        for part in response.candidates[0].content.parts:
            if part.text:
                text_parts.append(part.text)
            elif part.inline_data:
                img_b64 = base64.b64encode(part.inline_data.data).decode()
                images.append({
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

    return {
        "text": summary,
        "images": images,
        "image_count": len(images),
    }


# ---------------------------------------------------------------------------
# Pre-built FunctionTool instances
# ---------------------------------------------------------------------------

generate_image_tool = FunctionTool(generate_image)
generate_rich_image_tool = FunctionTool(generate_rich_image)


def get_image_gen_tools() -> list[FunctionTool]:
    """Return image generation tools."""
    return [generate_image_tool, generate_rich_image_tool]
