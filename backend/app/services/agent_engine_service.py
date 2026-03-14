"""Vertex AI Agent Engine integration helpers.

Provides production-grade wrappers for:
- Sessions (create + event append)
- Memory Bank (generate + retrieve + create)
- Code Execution sandboxes

These wrappers are used by ws_live, memory_service, and code_exec tools.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
from contextlib import suppress
from typing import Any

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Sandbox cache entry TTL — sandbox_ttl from settings is in seconds string
# e.g. "86400s".  We cache for 80% of that to avoid using expired sandboxes.
_SANDBOX_CACHE_TTL_RATIO = 0.8


class AgentEngineService:
    """Thin integration layer over Vertex AI Agent Engine SDK APIs."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = None
        self._agent_engine_name: str | None = None
        # { sandbox_key: (resource_name, created_at_monotonic) }
        self._sandbox_by_key: dict[str, tuple[str, float]] = {}

    @property
    def enabled(self) -> bool:
        return bool(
            self._settings.GOOGLE_GENAI_USE_VERTEXAI and self._settings.GOOGLE_CLOUD_PROJECT
        )

    def _get_client(self):
        if self._client is None:
            import vertexai

            self._client = vertexai.Client(
                project=self._settings.GOOGLE_CLOUD_PROJECT,
                location=self._settings.GOOGLE_CLOUD_LOCATION,
            )
        return self._client

    def _resolve_agent_engine_name(self) -> str:
        if self._agent_engine_name:
            return self._agent_engine_name

        configured = self._settings.AGENT_ENGINE_NAME.strip()
        if configured:
            self._agent_engine_name = configured
            return self._agent_engine_name

        client = self._get_client()
        created = client.agent_engines.create()
        name = getattr(getattr(created, "api_resource", None), "name", None)
        if not name:
            name = getattr(created, "name", None)
        if not name:
            raise RuntimeError("Agent Engine create did not return a resource name")

        self._agent_engine_name = name
        logger.info("agent_engine_created", name=name)
        return name

    def _short_reasoning_engine_name(self) -> str:
        full = self._resolve_agent_engine_name()
        if full.startswith("reasoningEngines/"):
            return full
        match = re.search(r"reasoningEngines/([^/]+)$", full)
        if match:
            return f"reasoningEngines/{match.group(1)}"
        return full

    def get_reasoning_engine_id(self) -> str:
        full = self._resolve_agent_engine_name()
        if full.isdigit():
            return full
        match = re.search(r"reasoningEngines/([^/]+)$", full)
        if not match:
            raise ValueError(f"Invalid agent engine resource name: {full}")
        return match.group(1)

    def build_session_resource_name(self, session_id: str) -> str:
        """Return the full Vertex AI resource name for a session.

        The ``memories.generate`` API requires the fully-qualified path:
          projects/{project}/locations/{location}/reasoningEngines/{id}/sessions/{session_id}
        """
        engine_id = self.get_reasoning_engine_id()
        return (
            f"projects/{self._settings.GOOGLE_CLOUD_PROJECT}"
            f"/locations/{self._settings.GOOGLE_CLOUD_LOCATION}"
            f"/reasoningEngines/{engine_id}"
            f"/sessions/{session_id}"
        )

    async def create_session(self, user_id: str) -> str:
        client = self._get_client()
        op = client.agent_engines.sessions.create(
            name=self._short_reasoning_engine_name(),
            user_id=user_id,
            config={
                "wait_for_completion": True,
                "ttl": self._settings.AGENT_ENGINE_SESSION_TTL,
            },
        )
        if not op.response or not op.response.name:
            raise RuntimeError("Failed to create Agent Engine session")
        return op.response.name

    async def append_text_event(
        self,
        *,
        session_name: str,
        author: str,
        text: str,
        invocation_id: str,
        role: str = "user",
    ) -> None:
        client = self._get_client()
        client.agent_engines.sessions.events.append(
            name=session_name,
            author=author,
            invocation_id=invocation_id,
            timestamp=dt.datetime.now(tz=dt.UTC),
            config={
                "content": {
                    "role": role,
                    "parts": [{"text": text}],
                }
            },
        )

    async def generate_memories_from_session(
        self,
        *,
        session_name: str,
        user_id: str,
    ) -> None:
        client = self._get_client()
        client.agent_engines.memories.generate(
            name=self._short_reasoning_engine_name(),
            vertex_session_source={"session": session_name},
            scope={"user_id": user_id},
            config={"wait_for_completion": True},
        )

    async def create_memory_fact(self, *, user_id: str, fact: str) -> None:
        client = self._get_client()
        client.agent_engines.memories.create(
            name=self._short_reasoning_engine_name(),
            fact=fact,
            scope={"user_id": user_id},
            config={"wait_for_completion": True},
        )

    async def retrieve_memories(
        self,
        *,
        user_id: str,
        query: str | None = None,
        top_k: int = 8,
    ) -> list[str]:
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "name": self._short_reasoning_engine_name(),
            "scope": {"user_id": user_id},
        }
        if query:
            kwargs["similarity_search_params"] = {
                "search_query": query,
                "top_k": top_k,
            }
        else:
            kwargs["simple_retrieval_params"] = {"page_size": top_k}

        facts: list[str] = []
        for item in client.agent_engines.memories.retrieve(**kwargs):
            memory = getattr(item, "memory", None)
            fact = getattr(memory, "fact", None) if memory is not None else None
            if fact:
                facts.append(fact)
        return facts

    async def purge_user_memories(self, *, user_id: str) -> int:
        client = self._get_client()
        op = client.agent_engines.memories.purge(
            name=self._short_reasoning_engine_name(),
            filter=f'scope.user_id="{user_id}"',
            force=True,
            config={"wait_for_completion": True},
        )
        if op.response and hasattr(op.response, "purge_count"):
            return int(op.response.purge_count)
        return 0

    def _sandbox_ttl_seconds(self) -> float:
        """Parse AGENT_ENGINE_SANDBOX_TTL (e.g. '86400s') to seconds."""
        raw = self._settings.AGENT_ENGINE_SANDBOX_TTL.rstrip("s")
        try:
            return float(raw) * _SANDBOX_CACHE_TTL_RATIO
        except ValueError:
            return 86400 * _SANDBOX_CACHE_TTL_RATIO

    def _evict_expired_sandboxes(self) -> None:
        """Remove sandbox cache entries older than the TTL."""
        ttl = self._sandbox_ttl_seconds()
        now = time.monotonic()
        expired = [k for k, (_, ts) in self._sandbox_by_key.items() if now - ts > ttl]
        for k in expired:
            self._sandbox_by_key.pop(k, None)
        if expired:
            logger.info("sandbox_cache_evicted", count=len(expired))

    async def _get_or_create_sandbox_name(self, sandbox_key: str) -> str:
        self._evict_expired_sandboxes()

        entry = self._sandbox_by_key.get(sandbox_key)
        if entry is not None:
            return entry[0]

        client = self._get_client()
        op = client.agent_engines.sandboxes.create(
            name=self._short_reasoning_engine_name(),
            spec={"code_execution_environment": {}},
            config={
                "wait_for_completion": True,
                "display_name": f"omni-{sandbox_key[:24]}",
                "ttl": self._settings.AGENT_ENGINE_SANDBOX_TTL,
            },
        )
        if not op.response or not op.response.name:
            raise RuntimeError("Failed to create Agent Engine sandbox")

        self._sandbox_by_key[sandbox_key] = (op.response.name, time.monotonic())
        return op.response.name

    @staticmethod
    def _decode_output_chunk(output: Any) -> dict[str, Any]:
        mime = getattr(output, "mime_type", "") or ""
        data = getattr(output, "data", None)
        payload: dict[str, Any] = {"mime_type": mime}

        if isinstance(data, (bytes, bytearray)):
            if mime.startswith("text/") or mime == "application/json":
                text = data.decode("utf-8", errors="replace")
                payload["text"] = text
                if mime == "application/json":
                    with suppress(json.JSONDecodeError):
                        payload["json"] = json.loads(text)
            else:
                payload["bytes_len"] = len(data)
        return payload

    async def execute_code(self, *, sandbox_key: str, code: str) -> dict[str, Any]:
        client = self._get_client()
        sandbox_name = await self._get_or_create_sandbox_name(sandbox_key)
        response = client.agent_engines.sandboxes.execute_code(
            name=sandbox_name,
            input_data={"code": code},
        )

        outputs = response.outputs or []
        decoded = [self._decode_output_chunk(chunk) for chunk in outputs]

        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        for item in decoded:
            text = item.get("text")
            if not text:
                continue
            # Vertex sandbox may return mixed text chunks; split obvious stderr-like chunks.
            if "traceback" in text.lower() or "error" in text.lower():
                stderr_parts.append(text)
            else:
                stdout_parts.append(text)

        return {
            "stdout": "\n".join(stdout_parts).strip(),
            "stderr": "\n".join(stderr_parts).strip(),
            "error": None,
            "results": decoded,
            "provider": "agent_engine",
            "sandbox_name": sandbox_name,
        }

    async def install_package(self, *, sandbox_key: str, package: str) -> dict[str, Any]:
        code = (
            "import subprocess, sys\n"
            f"proc = subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '{package}'], "
            "capture_output=True, text=True)\n"
            "print(proc.stdout)\n"
            "print(proc.stderr)\n"
            "if proc.returncode != 0:\n"
            "    raise RuntimeError(f'pip install failed: {proc.returncode}')\n"
        )
        return await self.execute_code(sandbox_key=sandbox_key, code=code)


_service: AgentEngineService | None = None


def get_agent_engine_service() -> AgentEngineService:
    global _service
    if _service is None:
        _service = AgentEngineService()
    return _service
