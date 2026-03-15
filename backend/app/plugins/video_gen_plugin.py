"""Video & Image Generation Plugin — Vertex AI Veo 2 + Imagen 3.

Provides two tools:
  - generate_video  : text-to-video via Veo 2 (muted, MP4, saved to GCS)
  - generate_image  : text-to-image via Imagen 3 (PNG, saved to GCS)

Both operations are fully async — heavy SDK/API work is offloaded to a
thread pool via ``asyncio.to_thread`` so the event loop stays free during
the 1-3 minute generation window.

Output files land in ``gs://{GCS_BUCKET_NAME}/generated/`` and are returned
as signed HTTPS URLs valid for 1 hour.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import uuid

from google.adk.tools import FunctionTool

from app.config import get_settings
from app.models.plugin import (
    PluginCategory,
    PluginKind,
    PluginManifest,
    ToolSummary,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

MANIFEST = PluginManifest(
    id="video-gen",
    name="Video & Image Generation",
    description=(
        "Generate videos with Google Veo 2 and high-quality images with "
        "Imagen 3 using Vertex AI. Videos are saved to GCS and returned as "
        "signed download URLs."
    ),
    version="0.1.0",
    author="Omni Hub",
    category=PluginCategory.CREATIVE,
    kind=PluginKind.NATIVE,
    icon="film",
    module="app.plugins.video_gen_plugin",
    factory="get_tools",
    tools_summary=[
        ToolSummary(
            name="generate_video",
            description="Generate a short video from a text prompt using Vertex AI Veo 2",
        ),
        ToolSummary(
            name="generate_image",
            description="Generate high-quality images from a text prompt using Vertex AI Imagen 3",
        ),
    ],
)


# ---------------------------------------------------------------------------
# Helpers — run in thread pool so they don't block the async event loop
# ---------------------------------------------------------------------------


def _sign_gcs_url(gcs_uri: str, expiry_minutes: int = 60) -> str:
    """Return a signed HTTPS URL for a GCS object."""
    from google.cloud import storage

    # Parse  gs://bucket/object
    without_prefix = gcs_uri.removeprefix("gs://")
    bucket_name, _, blob_path = without_prefix.partition("/")

    client = storage.Client(project=settings.GOOGLE_CLOUD_PROJECT)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    return blob.generate_signed_url(
        expiration=datetime.timedelta(minutes=expiry_minutes),
        method="GET",
        version="v4",
    )


def _run_video_generation(
    prompt: str,
    aspect_ratio: str,
    duration_seconds: int,
    sample_count: int,
    output_gcs_prefix: str,
) -> dict:
    """Blocking helper — submit Veo 2 job, poll until done, return result.

    Called via asyncio.to_thread so the event loop is not blocked.
    """
    import time

    from google import genai
    from google.genai import types

    client = genai.Client(
        vertexai=True,
        project=settings.GOOGLE_CLOUD_PROJECT,
        location=settings.GOOGLE_CLOUD_LOCATION,
    )

    operation = client.models.generate_videos(
        model="veo-002",
        prompt=prompt,
        config=types.GenerateVideosConfig(
            aspect_ratio=aspect_ratio,
            number_of_videos=sample_count,
            duration_seconds=duration_seconds,
            output_gcs_uri=output_gcs_prefix,
            generate_audio=False,  # muted by default; audio costs extra quota
        ),
    )

    # Poll every 15 s — Veo typically finishes in 60-180 s
    max_wait_seconds = 300
    waited = 0
    while not operation.done:
        if waited >= max_wait_seconds:
            return {
                "status": "timeout",
                "message": (
                    f"Video generation exceeded {max_wait_seconds}s. "
                    "The job is still running on Vertex AI. "
                    f"Operation name: {getattr(operation, 'name', 'unknown')}"
                ),
            }
        time.sleep(15)
        waited += 15
        operation = client.operations.get(operation)

    videos = operation.result.generated_videos
    if not videos:
        return {"status": "error", "message": "No videos were generated."}

    results = []
    for video in videos:
        gcs_uri = video.video.uri
        try:
            signed_url = _sign_gcs_url(gcs_uri)
        except Exception as exc:
            logger.warning("Could not sign GCS URL %s: %s", gcs_uri, exc)
            signed_url = gcs_uri  # Fall back to gs:// URI

        results.append({"gcs_uri": gcs_uri, "download_url": signed_url})

    return {"status": "success", "videos": results, "count": len(results)}


def _run_image_generation(
    prompt: str,
    negative_prompt: str,
    number_of_images: int,
    aspect_ratio: str,
    output_gcs_prefix: str,
) -> dict:
    """Blocking helper — generate images with Imagen 3, return GCS URLs."""
    import vertexai
    from vertexai.preview.vision_models import ImageGenerationModel

    vertexai.init(
        project=settings.GOOGLE_CLOUD_PROJECT,
        location=settings.GOOGLE_CLOUD_LOCATION,
    )

    model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")
    response = model.generate_images(
        prompt=prompt,
        negative_prompt=negative_prompt or None,
        number_of_images=number_of_images,
        aspect_ratio=aspect_ratio,
        output_gcs_uri=output_gcs_prefix,
        add_watermark=False,
    )

    results = []
    for img in response.images:
        gcs_uri = img._gcs_uri  # noqa: SLF001
        if not gcs_uri:
            # Save locally and upload if GCS URI not set
            import io

            from google.cloud import storage as gcs_lib

            filename = f"{uuid.uuid4().hex}.png"
            dest = output_gcs_prefix.rstrip("/") + f"/{filename}"
            without_prefix = dest.removeprefix("gs://")
            bucket_name, _, blob_path = without_prefix.partition("/")
            client = gcs_lib.Client(project=settings.GOOGLE_CLOUD_PROJECT)
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_path)
            buf = io.BytesIO()
            img._pil_image.save(buf, format="PNG")  # noqa: SLF001
            buf.seek(0)
            blob.upload_from_file(buf, content_type="image/png")
            gcs_uri = dest

        try:
            signed_url = _sign_gcs_url(gcs_uri)
        except Exception as exc:
            logger.warning("Could not sign GCS URL %s: %s", gcs_uri, exc)
            signed_url = gcs_uri

        results.append({"gcs_uri": gcs_uri, "download_url": signed_url})

    return {"status": "success", "images": results, "count": len(results)}


# ---------------------------------------------------------------------------
# Tool functions — async wrappers around the blocking helpers
# ---------------------------------------------------------------------------


async def generate_video(
    prompt: str,
    aspect_ratio: str = "16:9",
    duration_seconds: int = 5,
    sample_count: int = 1,
) -> dict:
    """Generate a short video from a text prompt using Vertex AI Veo 2.

    This is a long-running operation (typically 1-3 minutes). The agent will
    wait asynchronously and return the result when complete.

    Args:
        prompt: Detailed description of the video to generate. Be specific
                about scene, action, style, lighting, and camera movement.
        aspect_ratio: Video aspect ratio — "16:9" (landscape, default),
                      "9:16" (portrait/mobile), or "1:1" (square).
        duration_seconds: Length of the video in seconds (4-8, default 5).
        sample_count: Number of video variants to generate (1-4, default 1).

    Returns:
        A dict with status, and on success a list of videos each containing
        ``gcs_uri`` (gs:// path) and ``download_url`` (signed HTTPS URL).
    """
    run_id = uuid.uuid4().hex[:8]
    output_prefix = (
        f"gs://{settings.GCS_BUCKET_NAME}/generated/videos/{run_id}/"
    )

    # Clamp inputs
    duration_seconds = max(4, min(8, duration_seconds))
    sample_count = max(1, min(4, sample_count))

    logger.info(
        "Starting Veo 2 video generation: run_id=%s prompt=%.80s", run_id, prompt
    )

    try:
        result = await asyncio.to_thread(
            _run_video_generation,
            prompt,
            aspect_ratio,
            duration_seconds,
            sample_count,
            output_prefix,
        )
    except Exception as exc:
        logger.exception("Video generation failed: %s", exc)
        return {"status": "error", "message": str(exc)}

    logger.info("Veo 2 generation complete: run_id=%s status=%s", run_id, result.get("status"))
    return result


async def generate_image(
    prompt: str,
    negative_prompt: str = "",
    number_of_images: int = 1,
    aspect_ratio: str = "1:1",
) -> dict:
    """Generate high-quality images from a text prompt using Vertex AI Imagen 3.

    Args:
        prompt: Detailed description of the image. Include style, subject,
                lighting, and composition for best results.
        negative_prompt: Elements to exclude from the image (e.g. "blurry,
                         low resolution, watermark").
        number_of_images: How many image variants to generate (1-4, default 1).
        aspect_ratio: Image aspect ratio — "1:1" (square), "16:9" (landscape),
                      "9:16" (portrait), "4:3", or "3:4".

    Returns:
        A dict with status, and on success a list of images each containing
        ``gcs_uri`` (gs:// path) and ``download_url`` (signed HTTPS URL).
    """
    run_id = uuid.uuid4().hex[:8]
    output_prefix = (
        f"gs://{settings.GCS_BUCKET_NAME}/generated/images/{run_id}/"
    )

    number_of_images = max(1, min(4, number_of_images))

    logger.info(
        "Starting Imagen 3 generation: run_id=%s prompt=%.80s", run_id, prompt
    )

    try:
        result = await asyncio.to_thread(
            _run_image_generation,
            prompt,
            negative_prompt,
            number_of_images,
            aspect_ratio,
            output_prefix,
        )
    except Exception as exc:
        logger.exception("Image generation failed: %s", exc)
        return {"status": "error", "message": str(exc)}

    logger.info(
        "Imagen 3 generation complete: run_id=%s status=%s", run_id, result.get("status")
    )
    return result


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_tools() -> list[FunctionTool]:
    """Return all tools provided by this plugin."""
    return [
        FunctionTool(generate_video),
        FunctionTool(generate_image),
    ]
