"""Gen AI Evaluation Service — automated agent quality testing.

Uses Gemini to generate adaptive rubric-style tests per persona and
evaluate agent responses.  Results can be included in the blog post
and demo to prove production-quality mindset.

Design mirrors the Vertex AI Gen AI Evaluation Service pattern:
  1. Create evaluation dataset (prompts per persona)
  2. Run inference (get model responses)
  3. Evaluate responses with adaptive rubrics
"""

from __future__ import annotations

import json

from app.utils.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "EvalResult",
    "EvalService",
    "get_eval_service",
]

# ---------------------------------------------------------------------------
# Persona evaluation datasets
# ---------------------------------------------------------------------------

PERSONA_EVAL_PROMPTS: dict[str, list[str]] = {
    "assistant": [
        "What time is it in Tokyo right now?",
        "Draft a polite email declining a meeting invitation.",
        "Summarise the key points of time management.",
    ],
    "coder": [
        "Write a Python function to check if a string is a palindrome.",
        "Explain the difference between a stack and a queue.",
        "Debug: why does `[1,2,3].append([4])` give `[1,2,3,[4]]`?",
    ],
    "researcher": [
        "What are the latest developments in quantum computing in 2026?",
        "Compare the renewable energy policies of Germany and Japan.",
        "Find three credible sources about the impact of AI on healthcare.",
    ],
    "analyst": [
        "Analyse the trend in US inflation over the past 5 years.",
        "What financial metrics matter most for evaluating a SaaS startup?",
        "Compare Bitcoin and Ethereum as investments in 2026.",
    ],
    "creative": [
        "Write a short poem about a robot learning to love.",
        "Brainstorm five unique names for a coffee shop in Paris.",
        "Create a one-paragraph plot summary for a sci-fi short story.",
    ],
}

# ---------------------------------------------------------------------------
# Evaluation rubric prompt
# ---------------------------------------------------------------------------

_RUBRIC_PROMPT = """\
You are an evaluation engine.  Score the following agent response on
quality using adaptive rubrics.

For the given prompt, generate 3-5 pass/fail rubric items and evaluate
whether the response passes each.

Return **only** valid JSON (no markdown fences):
{{
  "rubrics": [
    {{"criterion": "Response addresses the question directly", "passed": true}},
    {{"criterion": "Response is factually accurate", "passed": true}},
    {{"criterion": "Response is well-structured", "passed": false}}
  ],
  "pass_rate": 0.67,
  "summary": "Brief overall assessment"
}}

PERSONA: {persona_id}
PROMPT: {prompt}
RESPONSE: {response}
"""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class EvalResult:
    """Result of a single prompt evaluation."""

    __slots__ = ("pass_rate", "persona_id", "prompt", "response", "rubrics", "summary")

    def __init__(
        self,
        persona_id: str,
        prompt: str,
        response: str,
        rubrics: list[dict],
        pass_rate: float,
        summary: str,
    ) -> None:
        self.persona_id = persona_id
        self.prompt = prompt
        self.response = response
        self.rubrics = rubrics
        self.pass_rate = pass_rate
        self.summary = summary

    def to_dict(self) -> dict:
        return {
            "persona_id": self.persona_id,
            "prompt": self.prompt,
            "response": self.response[:200],
            "rubrics": self.rubrics,
            "pass_rate": self.pass_rate,
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class EvalService:
    """Runs adaptive-rubric evaluations against persona agents."""

    INFERENCE_MODEL = "gemini-2.5-flash"
    EVAL_MODEL = "gemini-2.5-flash"

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google.genai import Client

            self._client = Client(vertexai=True)
        return self._client

    def get_eval_prompts(self, persona_id: str) -> list[str]:
        """Return evaluation prompts for a persona."""
        return PERSONA_EVAL_PROMPTS.get(persona_id, PERSONA_EVAL_PROMPTS["assistant"])

    async def run_inference(self, persona_id: str, prompt: str) -> str:
        """Get a model response for a prompt (simulating persona agent)."""
        client = self._get_client()
        response = client.models.generate_content(
            model=self.INFERENCE_MODEL,
            contents=[f"[Persona: {persona_id}] {prompt}"],
        )
        return response.text or ""

    async def evaluate_response(
        self, persona_id: str, prompt: str, response: str
    ) -> EvalResult:
        """Score a response using adaptive rubrics via Gemini."""
        client = self._get_client()
        eval_prompt = _RUBRIC_PROMPT.format(
            persona_id=persona_id,
            prompt=prompt,
            response=response,
        )
        eval_response = client.models.generate_content(
            model=self.EVAL_MODEL,
            contents=[eval_prompt],
        )

        raw = eval_response.text or ""
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("eval_bad_json", raw=raw[:200])
            data = {
                "rubrics": [{"criterion": "parseable result", "passed": False}],
                "pass_rate": 0.0,
                "summary": "Evaluation failed — unparseable output",
            }

        return EvalResult(
            persona_id=persona_id,
            prompt=prompt,
            response=response,
            rubrics=data.get("rubrics", []),
            pass_rate=data.get("pass_rate", 0.0),
            summary=data.get("summary", ""),
        )

    async def evaluate_persona(self, persona_id: str) -> list[EvalResult]:
        """Run full evaluation suite for a persona.

        Generates responses for each prompt, then evaluates each one.
        Returns list of :class:`EvalResult`.
        """
        prompts = self.get_eval_prompts(persona_id)
        results: list[EvalResult] = []

        for prompt in prompts:
            response = await self.run_inference(persona_id, prompt)
            result = await self.evaluate_response(persona_id, prompt, response)
            results.append(result)
            logger.info(
                "eval_completed",
                persona_id=persona_id,
                prompt=prompt[:60],
                pass_rate=result.pass_rate,
            )

        avg_pass = (
            sum(r.pass_rate for r in results) / len(results) if results else 0.0
        )
        logger.info(
            "persona_eval_done",
            persona_id=persona_id,
            prompts=len(results),
            avg_pass_rate=round(avg_pass, 2),
        )
        return results


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_service: EvalService | None = None


def get_eval_service() -> EvalService:
    global _service
    if _service is None:
        _service = EvalService()
    return _service
