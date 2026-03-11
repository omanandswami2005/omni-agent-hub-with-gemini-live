"""Tests for the /ws/live WebSocket endpoint.

Tests mock Firebase auth, ADK Runner, and InMemorySessionService so the
endpoint logic (auth, framing, bidirectional relay) is exercised without
hitting real backends.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from google.adk.events import Event
from google.genai import types

from app.api.ws_live import (
    _authenticate_ws,
    _build_run_config,
    _process_event,
    _send_auth_error,
    router,
)
from app.models.ws_messages import AgentState, ContentType, TranscriptionDirection

# ── Helper: minimal FastAPI app with our WS router ────────────────────


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/ws")
    return app


# ── _build_run_config ─────────────────────────────────────────────────


class TestBuildRunConfig:
    def test_default_voice(self):
        cfg = _build_run_config()
        voice = cfg.speech_config.voice_config.prebuilt_voice_config.voice_name
        assert voice == "Aoede"

    def test_custom_voice(self):
        cfg = _build_run_config(voice="Kore")
        voice = cfg.speech_config.voice_config.prebuilt_voice_config.voice_name
        assert voice == "Kore"

    def test_streaming_mode_bidi(self):
        from google.adk.agents.run_config import StreamingMode

        cfg = _build_run_config()
        assert cfg.streaming_mode == StreamingMode.BIDI

    def test_response_modalities(self):
        cfg = _build_run_config()
        assert cfg.response_modalities == ["AUDIO"]

    def test_audio_transcription_enabled(self):
        cfg = _build_run_config()
        assert cfg.input_audio_transcription is not None
        assert cfg.output_audio_transcription is not None

    def test_proactivity_enabled(self):
        cfg = _build_run_config()
        assert cfg.proactivity.proactive_audio is True

    def test_affective_dialog_enabled(self):
        cfg = _build_run_config()
        assert cfg.enable_affective_dialog is True


# ── _process_event ────────────────────────────────────────────────────


class TestProcessEvent:
    @pytest.fixture
    def ws(self) -> AsyncMock:
        ws = AsyncMock(spec=WebSocket)
        ws.send_bytes = AsyncMock()
        ws.send_text = AsyncMock()
        return ws

    async def test_audio_part_sends_binary(self, ws):
        audio_data = b"\x00\x01" * 100
        event = Event(
            author="agent",
            content=types.Content(
                parts=[types.Part(inline_data=types.Blob(mime_type="audio/pcm;rate=24000", data=audio_data))],
            ),
        )
        await _process_event(ws, event)
        ws.send_bytes.assert_awaited_once_with(audio_data)

    async def test_text_part_sends_agent_response(self, ws):
        event = Event(
            author="agent",
            content=types.Content(
                parts=[types.Part(text="Hello world")],
            ),
        )
        await _process_event(ws, event)
        ws.send_text.assert_awaited_once()
        data = json.loads(ws.send_text.call_args[0][0])
        assert data["type"] == "response"
        assert data["content_type"] == ContentType.TEXT
        assert data["data"] == "Hello world"

    async def test_input_transcription(self, ws):
        event = Event(
            author="agent",
            input_transcription=types.Transcription(text="test input", finished=True),
        )
        await _process_event(ws, event)
        ws.send_text.assert_awaited_once()
        data = json.loads(ws.send_text.call_args[0][0])
        assert data["type"] == "transcription"
        assert data["direction"] == TranscriptionDirection.INPUT
        assert data["text"] == "test input"
        assert data["finished"] is True

    async def test_output_transcription(self, ws):
        event = Event(
            author="agent",
            output_transcription=types.Transcription(text="agent says", finished=False),
        )
        await _process_event(ws, event)
        ws.send_text.assert_awaited_once()
        data = json.loads(ws.send_text.call_args[0][0])
        assert data["type"] == "transcription"
        assert data["direction"] == TranscriptionDirection.OUTPUT
        assert data["text"] == "agent says"
        assert data["finished"] is False

    async def test_turn_complete_sends_idle_status(self, ws):
        event = Event(author="agent", turn_complete=True)
        await _process_event(ws, event)
        ws.send_text.assert_awaited_once()
        data = json.loads(ws.send_text.call_args[0][0])
        assert data["type"] == "status"
        assert data["state"] == AgentState.IDLE

    async def test_interrupted_sends_listening_status(self, ws):
        event = Event(author="agent", interrupted=True)
        await _process_event(ws, event)
        ws.send_text.assert_awaited_once()
        data = json.loads(ws.send_text.call_args[0][0])
        assert data["type"] == "status"
        assert data["state"] == AgentState.LISTENING

    async def test_empty_event_sends_nothing(self, ws):
        event = Event(author="agent")
        await _process_event(ws, event)
        ws.send_bytes.assert_not_awaited()
        ws.send_text.assert_not_awaited()


# ── _authenticate_ws ──────────────────────────────────────────────────

_FAKE_DECODED = {"uid": "u1", "email": "a@b.com", "name": "Test"}


class TestAuthenticateWs:
    async def test_successful_auth(self):
        ws = AsyncMock(spec=WebSocket)
        ws.receive_text = AsyncMock(return_value=json.dumps({"type": "auth", "token": "tok"}))
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()

        with (
            patch("app.api.ws_live._get_firebase_app"),
            patch("firebase_admin.auth.verify_id_token", return_value=_FAKE_DECODED),
        ):
            result = await _authenticate_ws(ws)

        assert result is not None
        user, client_type = result
        assert user.uid == "u1"

    async def test_invalid_json_returns_none(self):
        ws = AsyncMock(spec=WebSocket)
        ws.receive_text = AsyncMock(return_value="not json")
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()

        user = await _authenticate_ws(ws)
        assert user is None
        ws.close.assert_awaited_once()

    async def test_missing_token_returns_none(self):
        ws = AsyncMock(spec=WebSocket)
        ws.receive_text = AsyncMock(return_value=json.dumps({"type": "auth"}))
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()

        user = await _authenticate_ws(ws)
        assert user is None
        ws.close.assert_awaited_once()

    async def test_wrong_type_returns_none(self):
        ws = AsyncMock(spec=WebSocket)
        ws.receive_text = AsyncMock(return_value=json.dumps({"type": "text", "content": "hi"}))
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()

        user = await _authenticate_ws(ws)
        assert user is None

    async def test_invalid_token_returns_none(self):
        ws = AsyncMock(spec=WebSocket)
        ws.receive_text = AsyncMock(return_value=json.dumps({"type": "auth", "token": "bad"}))
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()

        with (
            patch("app.api.ws_live._get_firebase_app"),
            patch("firebase_admin.auth.verify_id_token", side_effect=ValueError("bad token")),
        ):
            user = await _authenticate_ws(ws)

        assert user is None
        ws.close.assert_awaited_once()

    async def test_timeout_returns_none(self):
        ws = AsyncMock(spec=WebSocket)
        ws.receive_text = AsyncMock(side_effect=asyncio.TimeoutError)
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()

        user = await _authenticate_ws(ws)
        assert user is None


# ── _send_auth_error ──────────────────────────────────────────────────


class TestSendAuthError:
    async def test_sends_error_and_closes(self):
        ws = AsyncMock(spec=WebSocket)
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()

        await _send_auth_error(ws, "bad thing")
        ws.send_text.assert_awaited_once()
        data = json.loads(ws.send_text.call_args[0][0])
        assert data["status"] == "error"
        assert data["error"] == "bad thing"
        ws.close.assert_awaited_once_with(code=4003, reason="bad thing")


# ── Full WebSocket lifecycle (integration-style) ──────────────────────


class TestWsLiveEndpoint:
    """Test the ws_live endpoint with mocked ADK and Firebase."""

    def _patch_all(self):
        """Return a context manager that patches Firebase + ADK."""

        class PatchContext:
            def __init__(self):
                self.patches = []
                self.mock_runner_instance = MagicMock()

            def __enter__(self):
                # Firebase auth
                p1 = patch("app.api.ws_live._get_firebase_app")
                p2 = patch(
                    "firebase_admin.auth.verify_id_token",
                    return_value=_FAKE_DECODED,
                )

                # ADK session service
                mock_session_svc = AsyncMock()
                mock_session_svc.get_session = AsyncMock(return_value=None)
                mock_session_svc.create_session = AsyncMock()
                p3 = patch("app.api.ws_live._adk_session_service", mock_session_svc)

                # ADK runner: run_live yields empty immediately
                async def empty_gen(*args, **kwargs):
                    return
                    yield  # makes this an async generator

                self.mock_runner_instance.run_live = MagicMock(side_effect=empty_gen)
                p4 = patch("app.api.ws_live._get_runner", return_value=self.mock_runner_instance)

                # Connection manager
                mock_mgr = AsyncMock()
                mock_mgr.connect = AsyncMock()
                mock_mgr.disconnect = AsyncMock()
                p5 = patch("app.api.ws_live.get_connection_manager", return_value=mock_mgr)

                self.patches = [p1, p2, p3, p4, p5]
                self.mocks = [p.start() for p in self.patches]
                self.mock_mgr = mock_mgr
                return self

            def __exit__(self, *args):
                for p in self.patches:
                    p.stop()

        return PatchContext()

    def test_auth_success_and_connected(self):
        app = _make_app()
        with self._patch_all(), TestClient(app) as tc, tc.websocket_connect("/ws/live") as ws:
            # Send auth
            ws.send_text(json.dumps({"type": "auth", "token": "valid"}))
            # Receive auth_response
            data1 = json.loads(ws.receive_text())
            assert data1["type"] == "auth_response"
            assert data1["status"] == "ok"
            assert data1["user_id"] == "u1"
            # Receive connected
            data2 = json.loads(ws.receive_text())
            assert data2["type"] == "connected"
            assert data2["session_id"] == "u1_live"

    def test_auth_failure_closes_socket(self):
        app = _make_app()
        with (
            patch("app.api.ws_live._get_firebase_app"),
            patch("firebase_admin.auth.verify_id_token", side_effect=ValueError("nope")),
            TestClient(app) as tc,
            tc.websocket_connect("/ws/live") as ws,
        ):
            ws.send_text(json.dumps({"type": "auth", "token": "bad"}))
            # Should receive auth error then close
            data = json.loads(ws.receive_text())
            assert data["type"] == "auth_response"
            assert data["status"] == "error"
