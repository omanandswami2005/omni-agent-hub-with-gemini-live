"""Gallery API — list generated images from GCS."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.middleware.auth_middleware import get_current_user
from app.services.storage_service import get_storage_service
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/")
async def list_images(
    user=Depends(get_current_user),  # noqa: B008
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    """Return paginated signed URLs for all generated images in GCS.

    Images are stored under the ``images/`` prefix by the image generation
    tools.  We list blobs, generate short-lived signed URLs, and return
    them newest-first.
    """
    svc = get_storage_service()
    all_files = svc.list_files(prefix=f"images/{user.uid}/")

    # Filter to actual image files only
    image_exts = (".png", ".jpg", ".jpeg", ".webp", ".gif")
    image_files = [f for f in all_files if f.lower().endswith(image_exts)]

    # Newest first (UUID-based names are random, but GCS lists chronologically)
    image_files.reverse()

    total = len(image_files)
    start = (page - 1) * limit
    page_files = image_files[start : start + limit]

    items = []
    for path in page_files:
        try:
            url = svc.generate_signed_url(path, expiry_minutes=60)
            filename = path.split("/")[-1] if "/" in path else path
            items.append({
                "url": url,
                "filename": filename,
                "gcs_path": path,
            })
        except Exception:
            logger.warning("gallery_signed_url_failed", path=path, exc_info=True)

    return {
        "images": items,
        "total": total,
        "page": page,
        "limit": limit,
        "has_more": start + limit < total,
    }
