"""Tests for Memory Service (Task 16)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.memory_service import MemoryService, get_memory_service

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_singleton():
    import app.services.memory_service as mod

    old = mod._service
    mod._service = None
    yield
    mod._service = old


@pytest.fixture()
def mock_genai_client():
    client = MagicMock()
    return client


@pytest.fixture()
def mock_firestore():
    db = MagicMock()
    batch = MagicMock()
    batch.commit = AsyncMock()
    db.batch.return_value = batch

    # Mock collection chain
    col = MagicMock()
    db.collection.return_value.document.return_value.collection.return_value = col
    return db


@pytest.fixture()
def svc(mock_firestore, mock_genai_client):
    service = MemoryService()
    service._firestore = mock_firestore
    service._genai_client = mock_genai_client
    service._agent_engine = MagicMock(enabled=False)
    return service


# ── store_facts ──────────────────────────────────────────────────────


class TestStoreFacts:
    @pytest.mark.asyncio
    async def test_stores_facts_to_firestore(self, svc, mock_firestore):
        count = await svc.store_facts("u1", ["User likes coffee", "User lives in NYC"])
        assert count == 2
        mock_firestore.batch().commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_zero_for_empty(self, svc):
        count = await svc.store_facts("u1", [])
        assert count == 0


# ── get_all_facts ────────────────────────────────────────────────────


class TestGetAllFacts:
    @pytest.mark.asyncio
    async def test_returns_facts(self, svc, mock_firestore):
        # Mock async iterator for stream
        doc1 = MagicMock()
        doc1.to_dict.return_value = {"text": "fact 1", "created_at": 1.0}
        doc2 = MagicMock()
        doc2.to_dict.return_value = {"text": "fact 2", "created_at": 2.0}

        async def fake_stream():
            for d in [doc1, doc2]:
                yield d

        col = mock_firestore.collection.return_value.document.return_value.collection.return_value
        col.order_by.return_value.stream.return_value = fake_stream()

        facts = await svc.get_all_facts("u1")
        assert facts == ["fact 1", "fact 2"]


# ── extract_and_store ────────────────────────────────────────────────


class TestExtractAndStore:
    @pytest.mark.asyncio
    async def test_extracts_and_stores(self, svc, mock_genai_client, mock_firestore):
        mock_genai_client.models.generate_content.return_value = MagicMock(
            text=json.dumps({"facts": ["User prefers dark mode", "User works in finance"]})
        )
        facts = await svc.extract_and_store("u1", "User: I work in finance. Turn on dark mode.")
        assert len(facts) == 2
        assert "User prefers dark mode" in facts

    @pytest.mark.asyncio
    async def test_handles_bad_json(self, svc, mock_genai_client):
        mock_genai_client.models.generate_content.return_value = MagicMock(
            text="NOT VALID JSON"
        )
        facts = await svc.extract_and_store("u1", "some conversation")
        assert facts == []

    @pytest.mark.asyncio
    async def test_strips_code_fences(self, svc, mock_genai_client, mock_firestore):
        raw = json.dumps({"facts": ["fact1"]})
        mock_genai_client.models.generate_content.return_value = MagicMock(
            text=f"```json\n{raw}\n```"
        )
        facts = await svc.extract_and_store("u1", "conv")
        assert facts == ["fact1"]


# ── recall_memories ──────────────────────────────────────────────────


class TestRecallMemories:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_facts(self, svc, mock_firestore):
        async def empty_stream():
            return
            yield  # pragma: no cover

        col = mock_firestore.collection.return_value.document.return_value.collection.return_value
        col.order_by.return_value.stream.return_value = empty_stream()

        result = await svc.recall_memories("u1")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_all_facts_without_context(self, svc, mock_firestore):
        doc1 = MagicMock()
        doc1.to_dict.return_value = {"text": "fact1", "created_at": 1.0}

        async def fake_stream():
            yield doc1

        col = mock_firestore.collection.return_value.document.return_value.collection.return_value
        col.order_by.return_value.stream.return_value = fake_stream()

        result = await svc.recall_memories("u1")
        assert result == ["fact1"]

    @pytest.mark.asyncio
    async def test_filters_with_context(self, svc, mock_firestore, mock_genai_client):
        doc1 = MagicMock()
        doc1.to_dict.return_value = {"text": "likes coffee", "created_at": 1.0}
        doc2 = MagicMock()
        doc2.to_dict.return_value = {"text": "works in finance", "created_at": 2.0}

        async def fake_stream():
            for d in [doc1, doc2]:
                yield d

        col = mock_firestore.collection.return_value.document.return_value.collection.return_value
        col.order_by.return_value.stream.return_value = fake_stream()

        mock_genai_client.models.generate_content.return_value = MagicMock(
            text=json.dumps({"relevant": ["works in finance"]})
        )

        result = await svc.recall_memories("u1", context="analyse stock data")
        assert result == ["works in finance"]


# ── build_memory_preamble ────────────────────────────────────────────


class TestBuildMemoryPreamble:
    def test_empty_memories(self):
        svc = MemoryService()
        assert svc.build_memory_preamble([]) == ""

    def test_formats_memories(self):
        svc = MemoryService()
        result = svc.build_memory_preamble(["likes coffee", "works in finance"])
        assert "- likes coffee" in result
        assert "- works in finance" in result
        assert "remember" in result.lower()


# ── Singleton ────────────────────────────────────────────────────────


class TestSingleton:
    def test_returns_same_instance(self):
        svc1 = get_memory_service()
        svc2 = get_memory_service()
        assert svc1 is svc2
