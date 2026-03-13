"""Tests for Image Generation tools — Gemini interleaved output (nano banana)."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.image_gen import (
    GEMINI_IMAGE_MODEL,
    drain_pending_images,
    generate_image,
    generate_image_tool,
    generate_rich_image,
    generate_rich_image_tool,
    get_image_gen_tools,
)

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_client():
    """Reset the lazy genai client singleton and pending images."""
    import app.tools.image_gen as mod

    old = mod._genai_client
    mod._genai_client = None
    mod._pending_images.clear()
    yield
    mod._genai_client = old
    mod._pending_images.clear()


@pytest.fixture()
def mock_storage():
    """Mock storage service that returns a GCS URI."""
    svc = MagicMock()
    svc.upload_image.return_value = "gs://bucket/images/test.png"
    return svc


@pytest.fixture()
def fake_image_bytes():
    return b"\x89PNG\r\n\x1a\nfake-image-data"


def _make_generate_content_response(text_parts=None, image_parts=None):
    """Build a mock generate_content response with text and image parts."""
    parts = []
    if text_parts:
        for t in text_parts:
            part = MagicMock()
            part.text = t
            part.inline_data = None
            parts.append(part)
    if image_parts:
        for img_bytes, mime in image_parts:
            part = MagicMock()
            part.text = None
            part.inline_data = MagicMock()
            part.inline_data.data = img_bytes
            part.inline_data.mime_type = mime
            parts.append(part)

    candidate = MagicMock()
    candidate.content.parts = parts
    response = MagicMock()
    response.candidates = [candidate]
    return response


@pytest.fixture()
def mock_genai_client(fake_image_bytes):
    """Mock genai client for Gemini interleaved output."""
    client = MagicMock()
    response = _make_generate_content_response(
        text_parts=["A beautiful mountain landscape"],
        image_parts=[(fake_image_bytes, "image/png")],
    )
    client.aio.models.generate_content = AsyncMock(return_value=response)
    return client


@pytest.fixture()
def mock_gemini_rich_client(fake_image_bytes):
    """Mock genai client for rich interleaved (multi-part) output."""
    client = MagicMock()
    response = _make_generate_content_response(
        text_parts=["Here is the chart:"],
        image_parts=[(fake_image_bytes, "image/png")],
    )
    client.aio.models.generate_content = AsyncMock(return_value=response)
    return client


@pytest.fixture()
def mock_tool_context():
    """Mock ToolContext with a user_id."""
    ctx = MagicMock()
    ctx.user_id = "test-user-123"
    return ctx


# ── generate_image (single image via nano banana) ────────────────────


class TestGenerateImage:
    @pytest.mark.asyncio
    async def test_returns_text_summary(self, mock_genai_client, mock_storage):
        with (
            patch("app.tools.image_gen._get_client", return_value=mock_genai_client),
            patch("app.services.storage_service.get_storage_service", return_value=mock_storage),
        ):
            result = await generate_image("a cat on a mountain")
        assert isinstance(result, str)
        assert "Successfully generated" in result

    @pytest.mark.asyncio
    async def test_queues_image_for_ws_delivery(self, mock_genai_client, mock_storage, mock_tool_context):
        with (
            patch("app.tools.image_gen._get_client", return_value=mock_genai_client),
            patch("app.services.storage_service.get_storage_service", return_value=mock_storage),
        ):
            await generate_image("a cat", tool_context=mock_tool_context)
        images = drain_pending_images("test-user-123")
        assert len(images) == 1
        assert images[0]["tool_name"] == "generate_image"
        assert images[0]["image_base64"]
        assert images[0]["image_url"].startswith("gs://")
        assert images[0]["mime_type"] == "image/png"

    @pytest.mark.asyncio
    async def test_passes_prompt_to_model(self, mock_genai_client, mock_storage):
        with (
            patch("app.tools.image_gen._get_client", return_value=mock_genai_client),
            patch("app.services.storage_service.get_storage_service", return_value=mock_storage),
        ):
            await generate_image("sunset over ocean")
        call_kwargs = mock_genai_client.aio.models.generate_content.call_args
        assert "sunset over ocean" in call_kwargs[1]["contents"][0]
        assert call_kwargs[1]["model"] == GEMINI_IMAGE_MODEL

    @pytest.mark.asyncio
    async def test_appends_style_to_prompt(self, mock_genai_client, mock_storage):
        with (
            patch("app.tools.image_gen._get_client", return_value=mock_genai_client),
            patch("app.services.storage_service.get_storage_service", return_value=mock_storage),
        ):
            await generate_image("a dog", style="watercolor")
        call_kwargs = mock_genai_client.aio.models.generate_content.call_args
        prompt_sent = call_kwargs[1]["contents"][0]
        assert "watercolor" in prompt_sent

    @pytest.mark.asyncio
    async def test_handles_empty_response(self, mock_storage):
        client = MagicMock()
        empty_response = MagicMock()
        empty_response.candidates = []
        client.aio.models.generate_content = AsyncMock(return_value=empty_response)
        with (
            patch("app.tools.image_gen._get_client", return_value=client),
            patch("app.services.storage_service.get_storage_service", return_value=mock_storage),
        ):
            result = await generate_image("bad prompt")
        assert "No images were generated" in result

    @pytest.mark.asyncio
    async def test_includes_aspect_ratio_in_prompt(self, mock_genai_client, mock_storage):
        with (
            patch("app.tools.image_gen._get_client", return_value=mock_genai_client),
            patch("app.services.storage_service.get_storage_service", return_value=mock_storage),
        ):
            await generate_image("banner", aspect_ratio="16:9")
        call_kwargs = mock_genai_client.aio.models.generate_content.call_args
        assert "16:9" in call_kwargs[1]["contents"][0]

    @pytest.mark.asyncio
    async def test_uploads_to_gcs(self, mock_genai_client, mock_storage, mock_tool_context):
        with (
            patch("app.tools.image_gen._get_client", return_value=mock_genai_client),
            patch("app.services.storage_service.get_storage_service", return_value=mock_storage),
        ):
            await generate_image("test", tool_context=mock_tool_context)
        mock_storage.upload_image.assert_called_once()
        call_kwargs = mock_storage.upload_image.call_args
        assert call_kwargs[1]["user_id"] == "test-user-123"

    @pytest.mark.asyncio
    async def test_image_base64_is_valid(self, mock_genai_client, mock_storage, mock_tool_context, fake_image_bytes):
        with (
            patch("app.tools.image_gen._get_client", return_value=mock_genai_client),
            patch("app.services.storage_service.get_storage_service", return_value=mock_storage),
        ):
            await generate_image("test", tool_context=mock_tool_context)
        images = drain_pending_images("test-user-123")
        decoded = base64.b64decode(images[0]["image_base64"])
        assert decoded == fake_image_bytes


# ── generate_rich_image (interleaved text + images) ──────────────────


class TestGenerateRichImage:
    @pytest.mark.asyncio
    async def test_returns_text_summary(self, mock_gemini_rich_client, mock_storage):
        with (
            patch("app.tools.image_gen._get_client", return_value=mock_gemini_rich_client),
            patch("app.services.storage_service.get_storage_service", return_value=mock_storage),
        ):
            result = await generate_rich_image("chart of sales data")
        assert isinstance(result, str)
        assert "Here is the chart:" in result
        assert "Generated 1 image" in result

    @pytest.mark.asyncio
    async def test_queues_interleaved_parts(self, mock_gemini_rich_client, mock_storage, mock_tool_context):
        with (
            patch("app.tools.image_gen._get_client", return_value=mock_gemini_rich_client),
            patch("app.services.storage_service.get_storage_service", return_value=mock_storage),
        ):
            await generate_rich_image("diagram", tool_context=mock_tool_context)
        images = drain_pending_images("test-user-123")
        assert len(images) == 1
        payload = images[0]
        assert payload["tool_name"] == "generate_rich_image"
        assert "Here is the chart:" in payload["text"]
        assert len(payload["images"]) == 1
        assert len(payload["parts"]) == 2  # 1 text + 1 image
        assert payload["parts"][0]["type"] == "text"
        assert payload["parts"][1]["type"] == "image"

    @pytest.mark.asyncio
    async def test_images_have_base64_and_mime(self, mock_gemini_rich_client, mock_storage, mock_tool_context):
        with (
            patch("app.tools.image_gen._get_client", return_value=mock_gemini_rich_client),
            patch("app.services.storage_service.get_storage_service", return_value=mock_storage),
        ):
            await generate_rich_image("diagram", tool_context=mock_tool_context)
        images = drain_pending_images("test-user-123")
        img = images[0]["images"][0]
        assert "base64" in img
        assert img["mime_type"] == "image/png"

    @pytest.mark.asyncio
    async def test_uses_correct_model(self, mock_gemini_rich_client, mock_storage):
        with (
            patch("app.tools.image_gen._get_client", return_value=mock_gemini_rich_client),
            patch("app.services.storage_service.get_storage_service", return_value=mock_storage),
        ):
            await generate_rich_image("test")
        call_kwargs = mock_gemini_rich_client.aio.models.generate_content.call_args
        assert call_kwargs[1]["model"] == GEMINI_IMAGE_MODEL

    @pytest.mark.asyncio
    async def test_uploads_images_to_gcs(self, mock_gemini_rich_client, mock_storage, mock_tool_context):
        with (
            patch("app.tools.image_gen._get_client", return_value=mock_gemini_rich_client),
            patch("app.services.storage_service.get_storage_service", return_value=mock_storage),
        ):
            await generate_rich_image("test", tool_context=mock_tool_context)
        mock_storage.upload_image.assert_called_once()
        call_kwargs = mock_storage.upload_image.call_args
        assert call_kwargs[1]["user_id"] == "test-user-123"
        images = drain_pending_images("test-user-123")
        assert "gcs_uri" in images[0]["images"][0]


# ── FunctionTool instances ───────────────────────────────────────────


class TestFunctionToolInstances:
    def test_generate_image_tool(self):
        assert generate_image_tool.name == "generate_image"

    def test_generate_rich_image_tool(self):
        assert generate_rich_image_tool.name == "generate_rich_image"

    def test_get_image_gen_tools(self):
        tools = get_image_gen_tools()
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert "generate_image" in names
        assert "generate_rich_image" in names


# ── Agent factory integration ────────────────────────────────────────


class TestAgentFactoryIntegration:
    def test_media_capability_provides_image_tools(self):
        """Personas with 'media' capability get image gen tools."""
        from app.agents.agent_factory import get_tools_for_capabilities

        tools = get_tools_for_capabilities(["media"])
        names = {t.name for t in tools}
        assert "generate_image" in names
        assert "generate_rich_image" in names

    def test_non_media_capability_no_image_tools(self):
        """Personas without 'media' capability don't get image gen tools."""
        from app.agents.agent_factory import get_tools_for_capabilities

        tools = get_tools_for_capabilities(["search", "code_execution"])
        names = {t.name for t in tools}
        assert "generate_image" not in names
        assert "generate_rich_image" not in names
