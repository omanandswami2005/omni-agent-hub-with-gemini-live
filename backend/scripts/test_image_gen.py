#!/usr/bin/env python3
"""Test image generation & interleaved output — direct tool invocation.

Imports and calls the *production* ``generate_image`` (Imagen 4) and
``generate_rich_image`` (Gemini interleaved) functions directly, bypassing
the agent routing layer.  A lightweight mock ``ToolContext`` provides the
user_id so images are queued through the real ``_pending_images`` pipeline
and can be drained + saved.

Usage
-----
    cd backend && python scripts/test_image_gen.py

    # Custom prompts:
    python scripts/test_image_gen.py \\
        --imagen-prompt "A futuristic city at sunset" \\
        --interleaved-prompt "Show me step-by-step how to draw a cat"

    # Skip one test:
    python scripts/test_image_gen.py --skip-interleaved
    python scripts/test_image_gen.py --skip-imagen

Requires: google-genai, google-cloud-storage, python-dotenv
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Load .env so app.config.get_settings() can find GCP project, location, etc.
try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / ".env")
except ImportError:
    pass

OUTPUT_DIR = BACKEND_DIR / "test_output"
TEST_USER_ID = "test-image-gen-user"


# ---------------------------------------------------------------------------
# Minimal mock ToolContext — only needs .user_id for the pending-image queue
# ---------------------------------------------------------------------------
class _MockToolContext:
    """Stand-in for google.adk.tools.ToolContext with only user_id."""
    def __init__(self, user_id: str = TEST_USER_ID):
        self.user_id = user_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save_image(data_b64: str, mime_type: str, prefix: str) -> Path:
    """Decode base64 image and save to OUTPUT_DIR."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ext = (mime_type or "image/png").split("/")[-1]
    filename = f"{prefix}_{int(time.time())}.{ext}"
    filepath = OUTPUT_DIR / filename
    filepath.write_bytes(base64.b64decode(data_b64))
    return filepath


def _print_payload(payload: dict, label: str) -> None:
    """Pretty-print an image payload from the pending queue."""
    tool = payload.get("tool_name", "?")
    print(f"\n  🖼️  [{label}] tool={tool}")

    # Single image (generate_image / Imagen)
    if payload.get("image_base64"):
        path = _save_image(
            payload["image_base64"],
            payload.get("mime_type", "image/png"),
            f"imagen_{tool}",
        )
        print(f"       Saved: {path}  ({path.stat().st_size / 1024:.0f} KB)")
        if payload.get("description"):
            print(f"       Desc:  {payload['description'][:120]}")
        if payload.get("image_url"):
            print(f"       GCS:   {payload['image_url']}")

    # Interleaved parts (generate_rich_image)
    parts = payload.get("parts", [])
    if parts:
        print(f"       Interleaved parts ({len(parts)}):")
        img_idx = 0
        for i, part in enumerate(parts):
            if part.get("type") == "text":
                print(f"         [{i}] TEXT: {part.get('content', '')[:150]}")
            elif part.get("type") == "image":
                img_idx += 1
                path = _save_image(
                    part["base64"],
                    part.get("mime_type", "image/png"),
                    f"interleaved_{img_idx}",
                )
                print(f"         [{i}] IMAGE: saved → {path}  ({path.stat().st_size / 1024:.0f} KB)")

    # Standalone images list
    images = payload.get("images", [])
    if images and not parts:
        print(f"       Images ({len(images)}):")
        for j, img in enumerate(images):
            path = _save_image(img["base64"], img.get("mime_type", "image/png"), f"rich_{j}")
            print(f"         [{j}] saved → {path}  gcs={img.get('gcs_uri', '?')}")

    if payload.get("text"):
        print(f"       Summary: {payload['text'][:200]}")


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

async def run_test(args):
    """Import production tools and run them directly."""
    # Late imports so .env is loaded first
    from app.tools.image_gen import (
        generate_image,
        generate_rich_image,
        drain_pending_images,
        IMAGEN_MODEL,
        GEMINI_IMAGE_MODEL_V2,
    )

    print(f"\n{'='*60}")
    print(f"  Image Generation Test — Direct Tool Invocation")
    print(f"{'='*60}")
    print(f"  Imagen model:       {IMAGEN_MODEL}")
    print(f"  Interleaved model:  {GEMINI_IMAGE_MODEL_V2}")
    print(f"  Output dir:         {OUTPUT_DIR}")
    print()

    ctx = _MockToolContext()
    results: dict[str, dict] = {}

    # ── Test 1: Imagen 4 (generate_image) ──
    if not args.skip_imagen:
        print(f"[1/3] Testing Imagen 4 (generate_image)...")
        print(f"       Prompt: {args.imagen_prompt[:100]}")
        t0 = time.monotonic()
        try:
            summary = await generate_image(
                prompt=args.imagen_prompt,
                aspect_ratio="1:1",
                tool_context=ctx,
            )
            elapsed = time.monotonic() - t0
            print(f"\n  📝 Agent summary: {summary}")

            queued = drain_pending_images(TEST_USER_ID)
            print(f"  📦 Queued payloads: {len(queued)}")
            for payload in queued:
                _print_payload(payload, "IMAGEN")

            results["imagen"] = {
                "status": "PASS" if queued else "WARN (no images queued)",
                "elapsed": elapsed,
                "images": len(queued),
                "summary": summary[:120],
            }
        except Exception as e:
            elapsed = time.monotonic() - t0
            print(f"\n  ❌ ERROR: {type(e).__name__}: {e}")
            results["imagen"] = {"status": f"FAIL: {e}", "elapsed": elapsed, "images": 0}
            # Drain any partial state
            drain_pending_images(TEST_USER_ID)

        print(f"  ⏱️  {elapsed:.1f}s\n")
    else:
        print("[1/3] Skipping Imagen test (--skip-imagen)\n")

    # ── Test 2: Gemini Interleaved (generate_rich_image) ──
    if not args.skip_interleaved:
        print(f"[2/3] Testing Gemini Interleaved (generate_rich_image)...")
        print(f"       Prompt: {args.interleaved_prompt[:100]}")
        t0 = time.monotonic()
        try:
            summary = await generate_rich_image(
                prompt=args.interleaved_prompt,
                tool_context=ctx,
            )
            elapsed = time.monotonic() - t0
            print(f"\n  📝 Agent summary: {summary[:300]}")

            queued = drain_pending_images(TEST_USER_ID)
            print(f"  📦 Queued payloads: {len(queued)}")
            for payload in queued:
                _print_payload(payload, "INTERLEAVED")

            total_imgs = sum(len(p.get("images", [])) for p in queued)
            total_parts = sum(len(p.get("parts", [])) for p in queued)
            results["interleaved"] = {
                "status": "PASS" if queued else "WARN (no images queued)",
                "elapsed": elapsed,
                "images": total_imgs,
                "parts": total_parts,
                "summary": summary[:120],
            }
        except Exception as e:
            elapsed = time.monotonic() - t0
            print(f"\n  ❌ ERROR: {type(e).__name__}: {e}")
            results["interleaved"] = {"status": f"FAIL: {e}", "elapsed": elapsed, "images": 0}
            drain_pending_images(TEST_USER_ID)

        print(f"  ⏱️  {elapsed:.1f}s\n")
    else:
        print("[2/3] Skipping interleaved test (--skip-interleaved)\n")

    # ── Summary ──
    print(f"[3/3] Summary")
    print(f"{'='*60}")
    for name, res in results.items():
        status = res.get("status", "?")
        icon = "✅" if status == "PASS" else ("⚠️ " if "WARN" in status else "❌")
        print(f"  {icon} {name:>15}: {status}")
        if "elapsed" in res:
            print(f"                    Time: {res['elapsed']:.1f}s  Images: {res.get('images', 0)}")
        if res.get("parts"):
            print(f"                    Interleaved parts: {res['parts']}")

    output_files = list(OUTPUT_DIR.glob("*")) if OUTPUT_DIR.exists() else []
    if output_files:
        print(f"\n  📁 Saved {len(output_files)} file(s) to {OUTPUT_DIR}/")
        for f in sorted(output_files)[-10:]:
            size_kb = f.stat().st_size / 1024
            print(f"       {f.name}  ({size_kb:.0f} KB)")

    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Test image generation & interleaved output — direct tool invocation",
    )
    parser.add_argument(
        "--imagen-prompt",
        default="A majestic mountain landscape at golden hour with dramatic clouds and a reflective lake",
        help="Prompt for Imagen 4 test",
    )
    parser.add_argument(
        "--interleaved-prompt",
        default="Create an illustrated step-by-step guide showing how to make an origami crane, with images for each step",
        help="Prompt for Gemini interleaved output test",
    )
    parser.add_argument("--skip-imagen", action="store_true", help="Skip Imagen 4 test")
    parser.add_argument("--skip-interleaved", action="store_true", help="Skip interleaved test")
    args = parser.parse_args()

    asyncio.run(run_test(args))


if __name__ == "__main__":
    main()
