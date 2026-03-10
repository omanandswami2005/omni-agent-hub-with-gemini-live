"""Tests for Image Generation tools (Task 13)."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest

from app.tools.image_gen import (
    GEMINI_IMAGE_MODEL,
    IMAGEN_MODEL,
    generate_image,
    generate_image_tool,
    generate_rich_image,
    generate_rich_image_tool,
    get_image_gen_tools,
)

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_client():
    """Reset the lazy genai client singleton."""
    import app.tools.image_gen as mod

    old = mod._genai_client
    mod._genai_client = None
    yield
    mod._genai_client = old


@pytest.fixture()
def mock_storage():
    """Mock storage service that returns a GCS URI."""
    svc = MagicMock()
    svc.upload_image.return_value = "gs://bucket/images/test.png"
    return svc


@pytest.fixture()
def fake_image_bytes():
    return b"\x89PNG\r\n\x1a\nfake-image-data"


@pytest.fixture()
def mock_imagen_client(fake_image_bytes):
    """Mock genai client for Imagen 4 generate_images."""
    client = MagicMock()
    generated_image = MagicMock()
    generated_image.image.image_bytes = fake_image_bytes
    generated_image.image.mime_type = "image/png"
    response = MagicMock()
    response.generated_images = [generated_image]
    client.models.generate_images.return_value = response
    return client


@pytest.fixture()
def mock_gemini_image_client(fake_image_bytes):
    """Mock genai client for Gemini interleaved output."""
    client = MagicMock()

    text_part = MagicMock()
    text_part.text = "Here is the chart:"
    text_part.inline_data = None

    image_part = MagicMock()
    image_part.text = None
    image_part.inline_data = MagicMock()
    image_part.inline_data.data = fake_image_bytes
    image_part.inline_data.mime_type = "image/png"

    candidate = MagicMock()
    candidate.content.parts = [text_part, image_part]
    response = MagicMock()
    response.candidates = [candidate]
    client.models.generate_content.return_value = response
    return client


# ── generate_image (Imagen 4) ───────────────────────────────────────


class TestGenerateImage:
    @pytest.mark.asyncio
    async def test_returns_image_data(self, mock_imagen_client, mock_storage):
        with (
            patch("app.tools.image_gen._get_client", return_value=mock_imagen_client),
            patch(
                "app.services.storage_service.get_storage_service", return_value=mock_storage
            ),
        ):
            result = await generate_image("a cat on a mountain")
        assert "image_url" in result
        assert result["image_url"].startswith("gs://")
        assert result["mime_type"] == "image/png"
        assert result["image_base64"]  # non-empty

    @pytest.mark.asyncio
    async def test_passes_prompt_to_model(self, mock_imagen_client, mock_storage):
        with (
            patch("app.tools.image_gen._get_client", return_value=mock_imagen_client),
            patch(
                "app.services.storage_service.get_storage_service", return_value=mock_storage
            ),
        ):
            await generate_image("sunset over ocean")
        call_kwargs = mock_imagen_client.models.generate_images.call_args
        assert call_kwargs[1]["prompt"] == "sunset over ocean"
        assert call_kwargs[1]["model"] == IMAGEN_MODEL

    @pytest.mark.asyncio
    async def test_appends_style_to_prompt(self, mock_imagen_client, mock_storage):
        with (
            patch("app.tools.image_gen._get_client", return_value=mock_imagen_client),
            patch(
                "app.services.storage_service.get_storage_service", return_value=mock_storage
            ),
        ):
            await generate_image("a dog", style="watercolor")
        call_kwargs = mock_imagen_client.models.generate_images.call_args
        assert "watercolor" in call_kwargs[1]["prompt"]

    @pytest.mark.asyncio
    async def test_handles_empty_response(self, mock_storage):
        client = MagicMock()
        response = MagicMock()
        response.generated_images = []
        client.models.generate_images.return_value = response
        with (
            patch("app.tools.image_gen._get_client", return_value=client),
            patch(
                "app.services.storage_service.get_storage_service", return_value=mock_storage
            ),
        ):
            result = await generate_image("bad prompt")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_passes_aspect_ratio(self, mock_imagen_client, mock_storage):
        with (
            patch("app.tools.image_gen._get_client", return_value=mock_imagen_client),
            patch(
                "app.services.storage_service.get_storage_service", return_value=mock_storage
            ),
        ):
            await generate_image("banner", aspect_ratio="16:9")
        config = mock_imagen_client.models.generate_images.call_args[1]["config"]
        assert config.aspect_ratio == "16:9"

    @pytest.mark.asyncio
    async def test_uploads_to_gcs(self, mock_imagen_client, mock_storage):
        with (
            patch("app.tools.image_gen._get_client", return_value=mock_imagen_client),
            patch(
                "app.services.storage_service.get_storage_service", return_value=mock_storage
            ),
        ):
            await generate_image("test")
        mock_storage.upload_image.assert_called_once()

    @pytest.mark.asyncio
    async def test_image_base64_is_valid(
        self, mock_imagen_client, mock_storage, fake_image_bytes
    ):
        with (
            patch("app.tools.image_gen._get_client", return_value=mock_imagen_client),
            patch(
                "app.services.storage_service.get_storage_service", return_value=mock_storage
            ),
        ):
            result = await generate_image("test")
        decoded = base64.b64decode(result["image_base64"])
        assert decoded == fake_image_bytes


# ── generate_rich_image (Gemini interleaved) ─────────────────────────


class TestGenerateRichImage:
    @pytest.mark.asyncio
    async def test_returns_text_and_images(
        self, mock_gemini_image_client, mock_storage
    ):
        with (
            patch(
                "app.tools.image_gen._get_client",
                return_value=mock_gemini_image_client,
            ),
            patch(
                "app.services.storage_service.get_storage_service", return_value=mock_storage
            ),
        ):
            result = await generate_rich_image("chart of sales data")
        assert "Here is the chart:" in result["text"]
        assert result["image_count"] == 1
        assert len(result["images"]) == 1

    @pytest.mark.asyncio
    async def test_images_have_base64_and_mime(
        self, mock_gemini_image_client, mock_storage
    ):
        with (
            patch(
                "app.tools.image_gen._get_client",
                return_value=mock_gemini_image_client,
            ),
            patch(
                "app.services.storage_service.get_storage_service", return_value=mock_storage
            ),
        ):
            result = await generate_rich_image("diagram")
        img = result["images"][0]
        assert "base64" in img
        assert img["mime_type"] == "image/png"

    @pytest.mark.asyncio
    async def test_uses_correct_model(self, mock_gemini_image_client, mock_storage):
        with (
            patch(
                "app.tools.image_gen._get_client",
                return_value=mock_gemini_image_client,
            ),
            patch(
                "app.services.storage_service.get_storage_service", return_value=mock_storage
            ),
        ):
            await generate_rich_image("test")
        call_kwargs = mock_gemini_image_client.models.generate_content.call_args
        assert call_kwargs[1]["model"] == GEMINI_IMAGE_MODEL

    @pytest.mark.asyncio
    async def test_uploads_images_to_gcs(
        self, mock_gemini_image_client, mock_storage
    ):
        with (
            patch(
                "app.tools.image_gen._get_client",
                return_value=mock_gemini_image_client,
            ),
            patch(
                "app.services.storage_service.get_storage_service", return_value=mock_storage
            ),
        ):
            result = await generate_rich_image("test")
        mock_storage.upload_image.assert_called_once()
        assert "gcs_uri" in result["images"][0]


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
    def test_creative_gets_image_gen(self):
        from app.agents.agent_factory import _IMAGE_GEN_PERSONA_IDS

        assert "creative" in _IMAGE_GEN_PERSONA_IDS

    def test_assistant_gets_image_gen(self):
        from app.agents.agent_factory import _IMAGE_GEN_PERSONA_IDS

        assert "assistant" in _IMAGE_GEN_PERSONA_IDS

    def test_coder_no_image_gen(self):
        from app.agents.agent_factory import _IMAGE_GEN_PERSONA_IDS

        assert "coder" not in _IMAGE_GEN_PERSONA_IDS

    def test_creative_tools_include_generate_image(self):
        from app.agents.agent_factory import _default_tools_for_persona

        tools = _default_tools_for_persona("creative")
        names = {t.name for t in tools}
        assert "generate_image" in names
        assert "generate_rich_image" in names
