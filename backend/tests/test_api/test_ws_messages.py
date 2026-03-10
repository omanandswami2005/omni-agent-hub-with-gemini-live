"""Tests for WebSocket message schemas — serialization, deserialization,
and discriminated-union parsing.
"""

import json

import pytest
from pydantic import TypeAdapter

from app.models.ws_messages import (
    AgentResponse,
    AgentState,
    AuthMessage,
    AuthResponse,
    ClientMessage,
    ConnectedMessage,
    ContentType,
    ControlMessage,
    CrossClientMessage,
    ErrorMessage,
    ImageMessage,
    MCPToggleMessage,
    PersonaChangedMessage,
    PersonaSwitchMessage,
    ServerMessage,
    StatusMessage,
    TextMessage,
    ToolCallMessage,
    ToolResponseMessage,
    ToolStatus,
    TranscriptionDirection,
    TranscriptionMessage,
    WSMessage,
)

# ── Adapters for discriminated unions ────────────────────────────────

_client_adapter = TypeAdapter(ClientMessage)
_server_adapter = TypeAdapter(ServerMessage)
_ws_adapter = TypeAdapter(WSMessage)


# ── Client → Server round-trips ─────────────────────────────────────


class TestClientMessages:
    def test_auth_message(self):
        msg = AuthMessage(token="abc123")
        data = json.loads(msg.model_dump_json())
        assert data["type"] == "auth"
        assert data["token"] == "abc123"
        parsed = _client_adapter.validate_python(data)
        assert isinstance(parsed, AuthMessage)

    def test_text_message(self):
        msg = TextMessage(content="hello world")
        data = json.loads(msg.model_dump_json())
        assert data["type"] == "text"
        parsed = _client_adapter.validate_python(data)
        assert isinstance(parsed, TextMessage)
        assert parsed.content == "hello world"

    def test_image_message(self):
        msg = ImageMessage(data_base64="AAAA", mime_type="image/png")
        data = json.loads(msg.model_dump_json())
        assert data["type"] == "image"
        assert data["data_base64"] == "AAAA"
        parsed = _client_adapter.validate_python(data)
        assert isinstance(parsed, ImageMessage)

    def test_persona_switch(self):
        msg = PersonaSwitchMessage(persona_id="nova-1")
        data = json.loads(msg.model_dump_json())
        assert data["type"] == "persona_switch"
        parsed = _client_adapter.validate_python(data)
        assert isinstance(parsed, PersonaSwitchMessage)
        assert parsed.persona_id == "nova-1"

    def test_mcp_toggle(self):
        msg = MCPToggleMessage(mcp_id="brave", enabled=True)
        data = json.loads(msg.model_dump_json())
        assert data["type"] == "mcp_toggle"
        parsed = _client_adapter.validate_python(data)
        assert isinstance(parsed, MCPToggleMessage)
        assert parsed.enabled is True

    def test_control_message(self):
        msg = ControlMessage(action="start_voice")
        data = json.loads(msg.model_dump_json())
        assert data["type"] == "control"
        parsed = _client_adapter.validate_python(data)
        assert isinstance(parsed, ControlMessage)


# ── Server → Client round-trips ─────────────────────────────────────


class TestServerMessages:
    def test_auth_response_ok(self):
        msg = AuthResponse(status="ok", user_id="u1", session_id="s1")
        data = json.loads(msg.model_dump_json())
        assert data["type"] == "auth_response"
        parsed = _server_adapter.validate_python(data)
        assert isinstance(parsed, AuthResponse)
        assert parsed.user_id == "u1"

    def test_agent_response_text(self):
        msg = AgentResponse(content_type=ContentType.TEXT, data="Hi there")
        data = json.loads(msg.model_dump_json())
        assert data["type"] == "response"
        assert data["content_type"] == "text"
        parsed = _server_adapter.validate_python(data)
        assert isinstance(parsed, AgentResponse)
        assert parsed.data == "Hi there"

    def test_agent_response_genui(self):
        genui = {"type": "chart", "chartType": "line", "title": "TSLA"}
        msg = AgentResponse(content_type=ContentType.GENUI, genui=genui)
        data = json.loads(msg.model_dump_json())
        parsed = _server_adapter.validate_python(data)
        assert parsed.genui["chartType"] == "line"

    def test_transcription_input(self):
        msg = TranscriptionMessage(
            direction=TranscriptionDirection.INPUT,
            text="What's on my schedule?",
            finished=True,
        )
        data = json.loads(msg.model_dump_json())
        assert data["direction"] == "input"
        parsed = _server_adapter.validate_python(data)
        assert isinstance(parsed, TranscriptionMessage)
        assert parsed.finished is True

    def test_transcription_output(self):
        msg = TranscriptionMessage(
            direction=TranscriptionDirection.OUTPUT,
            text="You have 3 meetings",
            finished=True,
        )
        parsed = _server_adapter.validate_python(json.loads(msg.model_dump_json()))
        assert parsed.direction == TranscriptionDirection.OUTPUT

    def test_tool_call(self):
        msg = ToolCallMessage(
            tool_name="brave_search",
            arguments={"query": "TSLA"},
            status=ToolStatus.STARTED,
        )
        data = json.loads(msg.model_dump_json())
        assert data["type"] == "tool_call"
        parsed = _server_adapter.validate_python(data)
        assert isinstance(parsed, ToolCallMessage)
        assert parsed.status == ToolStatus.STARTED

    def test_tool_response(self):
        msg = ToolResponseMessage(tool_name="brave_search", result="stock data")
        data = json.loads(msg.model_dump_json())
        parsed = _server_adapter.validate_python(data)
        assert isinstance(parsed, ToolResponseMessage)
        assert parsed.success is True

    def test_error_message(self):
        msg = ErrorMessage(code="RATE_LIMITED", description="Too many requests")
        data = json.loads(msg.model_dump_json())
        assert data["type"] == "error"
        parsed = _server_adapter.validate_python(data)
        assert isinstance(parsed, ErrorMessage)
        assert parsed.code == "RATE_LIMITED"

    def test_status_idle(self):
        msg = StatusMessage(state=AgentState.IDLE)
        data = json.loads(msg.model_dump_json())
        parsed = _server_adapter.validate_python(data)
        assert isinstance(parsed, StatusMessage)

    def test_status_processing_with_detail(self):
        msg = StatusMessage(state=AgentState.PROCESSING, detail="Calling Brave Search...")
        parsed = _server_adapter.validate_python(json.loads(msg.model_dump_json()))
        assert parsed.detail == "Calling Brave Search..."

    def test_persona_changed(self):
        msg = PersonaChangedMessage(persona_id="nova-1", persona_name="Nova", voice="Charon")
        data = json.loads(msg.model_dump_json())
        assert data["type"] == "persona_changed"
        parsed = _server_adapter.validate_python(data)
        assert isinstance(parsed, PersonaChangedMessage)

    def test_connected_message(self):
        msg = ConnectedMessage(session_id="s1", resumed_from="s0")
        data = json.loads(msg.model_dump_json())
        assert data["type"] == "connected"
        parsed = _server_adapter.validate_python(data)
        assert parsed.resumed_from == "s0"

    def test_cross_client_message(self):
        msg = CrossClientMessage(action="note_saved", target="web", data={"id": "n1"})
        data = json.loads(msg.model_dump_json())
        parsed = _server_adapter.validate_python(data)
        assert isinstance(parsed, CrossClientMessage)
        assert parsed.data["id"] == "n1"


# ── WSMessage (full union) ───────────────────────────────────────────


class TestWSMessageUnion:
    """Ensure the universal ``WSMessage`` union parses any frame."""

    @pytest.mark.parametrize(
        "raw",
        [
            '{"type":"auth","token":"tok"}',
            '{"type":"text","content":"hi"}',
            '{"type":"image","data_base64":"x","mime_type":"image/jpeg"}',
            '{"type":"persona_switch","persona_id":"p1"}',
            '{"type":"mcp_toggle","mcp_id":"m1","enabled":true}',
            '{"type":"control","action":"start_voice"}',
            '{"type":"auth_response","status":"ok"}',
            '{"type":"response","data":"hello"}',
            '{"type":"transcription","direction":"input","text":"hi","finished":false}',
            '{"type":"tool_call","tool_name":"t","arguments":{}}',
            '{"type":"tool_response","tool_name":"t","result":"ok"}',
            '{"type":"error","code":"E1"}',
            '{"type":"status","state":"idle"}',
            '{"type":"persona_changed","persona_id":"p1"}',
            '{"type":"connected","session_id":"s1"}',
            '{"type":"cross_client","action":"ping"}',
        ],
    )
    def test_all_types_parse(self, raw: str):
        parsed = _ws_adapter.validate_json(raw)
        assert parsed.type == json.loads(raw)["type"]
