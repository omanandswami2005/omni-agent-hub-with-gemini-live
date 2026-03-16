"""Memory Bank — long-term memory across sessions.

Stores key facts extracted from conversations and retrieves relevant
memories when a new session starts.  Inspired by Vertex AI Agent Engine
Memory Bank (GA), implemented with Firestore + Gemini for fact
extraction so it works on any deployment target.

Architecture
------------
* After each session, ``extract_and_store`` passes the conversation text
  to Gemini which distills it into a list of concise facts.
* Facts are stored in Firestore under ``memories/{user_id}/facts/{id}``.
* On new session start, ``recall_memories`` finds relevant facts using
  Gemini semantic matching and injects them into the system prompt.
"""

from __future__ import annotations

import json
import time
import uuid

from app.config import get_settings
from app.services.agent_engine_service import get_agent_engine_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "MemoryService",
    "get_memory_service",
]

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_EXTRACT_PROMPT = """\
Extract key facts, preferences, and important information from this
conversation that should be remembered for future sessions.

Return **only** valid JSON (no markdown fences):
{{
  "facts": [
    "User prefers dark mode",
    "User works in finance at Goldman Sachs",
    "User asked about Tesla stock on 2026-03-10"
  ]
}}

If there are no notable facts, return {{"facts": []}}.

CONVERSATION:
{conversation}
"""

_RECALL_PROMPT = """\
Given the user's previous facts/memories and the current context, select
the most relevant memories that should be injected into the agent's
context for this new session.

Return **only** valid JSON:
{{
  "relevant": [
    "User prefers dark mode",
    "User works in finance"
  ]
}}

If none are relevant, return {{"relevant": []}}.

USER MEMORIES:
{memories}

CURRENT CONTEXT:
{context}
"""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class MemoryService:
    """Manages long-term user memory via Firestore + Gemini extraction."""

    MODEL = "gemini-2.5-flash-lite"

    def __init__(self) -> None:
        self._firestore = None
        self._genai_client = None
        self._agent_engine = get_agent_engine_service()

    @property
    def _use_agent_engine_memory(self) -> bool:
        settings_enabled = get_settings().USE_AGENT_ENGINE_MEMORY_BANK
        return settings_enabled and self._agent_engine.enabled

    def _get_db(self):
        if self._firestore is None:
            from google.cloud import firestore

            self._firestore = firestore.AsyncClient()
        return self._firestore

    def _get_client(self):
        if self._genai_client is None:
            from google.genai import Client

            self._genai_client = Client(vertexai=True)
        return self._genai_client

    # -- Storage -----------------------------------------------------------

    async def store_facts(self, user_id: str, facts: list[str]) -> int:
        """Store extracted facts for a user. Returns number stored."""
        if not facts:
            return 0

        if self._use_agent_engine_memory:
            stored = 0
            for fact in facts:
                await self._agent_engine.create_memory_fact(user_id=user_id, fact=fact)
                stored += 1
            logger.info("memories_stored_agent_engine", user_id=user_id, count=stored)
            return stored

        db = self._get_db()
        batch = db.batch()
        col = db.collection("memories").document(user_id).collection("facts")

        for fact in facts:
            doc_ref = col.document(uuid.uuid4().hex[:12])
            batch.set(
                doc_ref,
                {
                    "text": fact,
                    "created_at": time.time(),
                },
            )

        await batch.commit()
        logger.info("memories_stored", user_id=user_id, count=len(facts))
        return len(facts)

    async def get_all_facts(self, user_id: str) -> list[str]:
        """Return all stored facts for a user."""
        if self._use_agent_engine_memory:
            return await self._agent_engine.retrieve_memories(user_id=user_id)

        db = self._get_db()
        col = db.collection("memories").document(user_id).collection("facts")
        docs = col.order_by("created_at").stream()
        facts = []
        async for doc in docs:
            data = doc.to_dict()
            if data and "text" in data:
                facts.append(data["text"])
        return facts

    async def clear_facts(self, user_id: str) -> int:
        """Delete all facts for a user. Returns count deleted."""
        if self._use_agent_engine_memory:
            return await self._agent_engine.purge_user_memories(user_id=user_id)

        db = self._get_db()
        col = db.collection("memories").document(user_id).collection("facts")
        deleted = 0
        async for doc in col.stream():
            await doc.reference.delete()
            deleted += 1
        return deleted

    # -- Extraction --------------------------------------------------------

    async def extract_and_store(self, user_id: str, conversation_text: str) -> list[str]:
        """Extract facts from conversation text and persist them.

        Returns the list of extracted facts.
        """
        client = self._get_client()
        prompt = _EXTRACT_PROMPT.format(conversation=conversation_text)
        response = client.models.generate_content(
            model=self.MODEL,
            contents=[prompt],
        )

        raw = response.text or ""
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

        try:
            data = json.loads(raw)
            facts = data.get("facts", [])
        except json.JSONDecodeError:
            logger.warning("memory_extraction_bad_json", raw=raw[:200])
            facts = []

        if facts:
            await self.store_facts(user_id, facts)
        return facts

    # -- Recall ------------------------------------------------------------

    async def recall_memories(self, user_id: str, context: str = "") -> list[str]:
        """Retrieve the most relevant memories for a session start.

        If *context* is provided, uses Gemini to filter for relevance.
        Otherwise returns all stored facts (up to 50).
        """
        if self._use_agent_engine_memory:
            query = context.strip() or None
            return await self._agent_engine.retrieve_memories(
                user_id=user_id,
                query=query,
            )

        all_facts = await self.get_all_facts(user_id)
        if not all_facts:
            return []

        # If no context, return raw (up to 50)
        if not context:
            return all_facts[:50]

        client = self._get_client()
        prompt = _RECALL_PROMPT.format(
            memories=json.dumps(all_facts),
            context=context,
        )
        response = client.models.generate_content(
            model=self.MODEL,
            contents=[prompt],
        )

        raw = response.text or ""
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

        try:
            data = json.loads(raw)
            return data.get("relevant", all_facts[:50])
        except json.JSONDecodeError:
            return all_facts[:50]

    def build_memory_preamble(self, memories: list[str]) -> str:
        """Format recalled memories as a system prompt preamble."""
        if not memories:
            return ""
        lines = "\n".join(f"- {m}" for m in memories)
        return (
            f"You remember the following about this user from past sessions:\n{lines}\n\n"
            "Use this context when relevant, but do not repeat it verbatim."
        )

    async def sync_from_session(self, user_id: str, session_id: str) -> None:
        """Generate memories from an Agent Engine session when enabled."""
        if not self._use_agent_engine_memory:
            return
        session_name = self._agent_engine.build_session_resource_name(session_id)
        await self._agent_engine.generate_memories_from_session(
            session_name=session_name,
            user_id=user_id,
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_service: MemoryService | None = None


def get_memory_service() -> MemoryService:
    global _service
    if _service is None:
        _service = MemoryService()
    return _service
