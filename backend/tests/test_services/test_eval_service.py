"""Tests for Eval Service (Task 16)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.services.eval_service import (
    PERSONA_EVAL_PROMPTS,
    EvalResult,
    EvalService,
    get_eval_service,
)

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_singleton():
    import app.services.eval_service as mod

    old = mod._service
    mod._service = None
    yield
    mod._service = old


@pytest.fixture()
def mock_client():
    return MagicMock()


@pytest.fixture()
def svc(mock_client):
    service = EvalService()
    service._client = mock_client
    return service


# ── Eval prompts ─────────────────────────────────────────────────────


class TestEvalPrompts:
    def test_all_personas_have_prompts(self):
        for pid in ("assistant", "coder", "researcher", "analyst", "creative"):
            assert pid in PERSONA_EVAL_PROMPTS
            assert len(PERSONA_EVAL_PROMPTS[pid]) >= 3

    def test_get_eval_prompts(self):
        svc = EvalService()
        prompts = svc.get_eval_prompts("coder")
        assert len(prompts) >= 3
        assert any("Python" in p or "code" in p.lower() for p in prompts)

    def test_unknown_persona_falls_back_to_assistant(self):
        svc = EvalService()
        prompts = svc.get_eval_prompts("nonexistent")
        assert prompts == PERSONA_EVAL_PROMPTS["assistant"]


# ── EvalResult ───────────────────────────────────────────────────────


class TestEvalResult:
    def test_to_dict(self):
        r = EvalResult(
            persona_id="coder",
            prompt="write code",
            response="def foo(): pass",
            rubrics=[{"criterion": "valid syntax", "passed": True}],
            pass_rate=1.0,
            summary="Good",
        )
        d = r.to_dict()
        assert d["persona_id"] == "coder"
        assert d["pass_rate"] == 1.0
        assert len(d["rubrics"]) == 1

    def test_response_truncated_in_dict(self):
        r = EvalResult(
            persona_id="assistant",
            prompt="p",
            response="x" * 500,
            rubrics=[],
            pass_rate=0.0,
            summary="",
        )
        d = r.to_dict()
        assert len(d["response"]) == 200


# ── run_inference ────────────────────────────────────────────────────


class TestRunInference:
    @pytest.mark.asyncio
    async def test_returns_model_response(self, svc, mock_client):
        mock_client.models.generate_content.return_value = MagicMock(text="Here is the answer.")
        result = await svc.run_inference("coder", "write hello world")
        assert result == "Here is the answer."
        mock_client.models.generate_content.assert_called_once()


# ── evaluate_response ────────────────────────────────────────────────


class TestEvaluateResponse:
    @pytest.mark.asyncio
    async def test_returns_eval_result(self, svc, mock_client):
        mock_client.models.generate_content.return_value = MagicMock(
            text=json.dumps(
                {
                    "rubrics": [
                        {"criterion": "addresses the question", "passed": True},
                        {"criterion": "well-structured", "passed": True},
                        {"criterion": "accurate", "passed": False},
                    ],
                    "pass_rate": 0.67,
                    "summary": "Mostly good, but inaccurate info.",
                }
            )
        )
        result = await svc.evaluate_response("analyst", "analyse inflation", "Inflation is 3%.")
        assert isinstance(result, EvalResult)
        assert result.pass_rate == 0.67
        assert len(result.rubrics) == 3

    @pytest.mark.asyncio
    async def test_handles_bad_json(self, svc, mock_client):
        mock_client.models.generate_content.return_value = MagicMock(text="NOT JSON")
        result = await svc.evaluate_response("assistant", "prompt", "response")
        assert result.pass_rate == 0.0
        assert "failed" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_strips_code_fences(self, svc, mock_client):
        raw = json.dumps(
            {
                "rubrics": [{"criterion": "ok", "passed": True}],
                "pass_rate": 1.0,
                "summary": "Perfect.",
            }
        )
        mock_client.models.generate_content.return_value = MagicMock(text=f"```json\n{raw}\n```")
        result = await svc.evaluate_response("coder", "p", "r")
        assert result.pass_rate == 1.0


# ── evaluate_persona ─────────────────────────────────────────────────


class TestEvaluatePersona:
    @pytest.mark.asyncio
    async def test_evaluates_all_prompts(self, svc, mock_client):
        # Inference calls
        mock_client.models.generate_content.return_value = MagicMock(
            text=json.dumps(
                {
                    "rubrics": [{"criterion": "good", "passed": True}],
                    "pass_rate": 0.9,
                    "summary": "Good.",
                }
            )
        )
        results = await svc.evaluate_persona("coder")
        assert len(results) == len(PERSONA_EVAL_PROMPTS["coder"])
        # Each prompt triggers 2 calls: inference + evaluation
        assert mock_client.models.generate_content.call_count == len(results) * 2


# ── Singleton ────────────────────────────────────────────────────────


class TestSingleton:
    def test_returns_same_instance(self):
        svc1 = get_eval_service()
        svc2 = get_eval_service()
        assert svc1 is svc2
