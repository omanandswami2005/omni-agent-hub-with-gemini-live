"""Tests for TaskArchitect — dynamic pipeline orchestrator (Task 15)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.task_architect import (
    COMPLEXITY_THRESHOLD,
    PipelineBlueprint,
    StageType,
    SubTask,
    TaskArchitect,
    TaskStage,
)

# ── Data model tests ─────────────────────────────────────────────────


class TestSubTask:
    def test_to_dict(self):
        t = SubTask(id="t1", description="research topic", persona_id="researcher")
        d = t.to_dict()
        assert d["id"] == "t1"
        assert d["persona_id"] == "researcher"

    def test_defaults(self):
        t = SubTask(id="t1", description="do stuff")
        assert t.persona_id == "assistant"
        assert t.instruction == ""


class TestTaskStage:
    def test_to_dict(self):
        stage = TaskStage(
            name="gather",
            stage_type=StageType.PARALLEL,
            tasks=[SubTask(id="t1", description="a"), SubTask(id="t2", description="b")],
        )
        d = stage.to_dict()
        assert d["stage_type"] == "parallel"
        assert len(d["tasks"]) == 2
        assert d["max_iterations"] == 3

    def test_loop_stage(self):
        stage = TaskStage(
            name="refine",
            stage_type=StageType.LOOP,
            tasks=[SubTask(id="t1", description="iterate")],
            max_iterations=5,
        )
        assert stage.max_iterations == 5


class TestPipelineBlueprint:
    def test_total_agents(self):
        bp = PipelineBlueprint(
            task_description="test",
            stages=[
                TaskStage(
                    name="s1",
                    stage_type=StageType.PARALLEL,
                    tasks=[SubTask(id="t1", description="a"), SubTask(id="t2", description="b")],
                ),
                TaskStage(
                    name="s2",
                    stage_type=StageType.SINGLE,
                    tasks=[SubTask(id="t3", description="c")],
                ),
            ],
        )
        assert bp.total_agents == 3

    def test_to_dict(self):
        bp = PipelineBlueprint(task_description="plan a trip", stages=[])
        d = bp.to_dict()
        assert d["task_description"] == "plan a trip"
        assert "pipeline_id" in d
        assert d["total_agents"] == 0

    def test_from_analysis(self):
        analysis = {
            "stages": [
                {
                    "name": "research",
                    "type": "parallel",
                    "tasks": [
                        {
                            "id": "t1",
                            "description": "flights",
                            "persona_id": "researcher",
                            "instruction": "Find flights",
                        },
                        {
                            "id": "t2",
                            "description": "hotels",
                            "persona_id": "researcher",
                            "instruction": "Find hotels",
                        },
                    ],
                },
                {
                    "name": "plan",
                    "type": "sequential",
                    "tasks": [
                        {
                            "id": "t3",
                            "description": "itinerary",
                            "persona_id": "assistant",
                            "instruction": "Build itinerary",
                        },
                    ],
                },
            ]
        }
        bp = PipelineBlueprint.from_analysis(analysis, "plan trip")
        assert len(bp.stages) == 2
        assert bp.stages[0].stage_type == StageType.PARALLEL
        assert bp.stages[1].stage_type == StageType.SEQUENTIAL
        assert bp.total_agents == 3

    def test_from_analysis_defaults(self):
        analysis = {"stages": [{"tasks": [{"id": "t1", "description": "do it"}]}]}
        bp = PipelineBlueprint.from_analysis(analysis, "task")
        assert bp.stages[0].stage_type == StageType.SEQUENTIAL
        assert bp.stages[0].tasks[0].persona_id == "assistant"


class TestStageType:
    def test_values(self):
        assert StageType.PARALLEL.value == "parallel"
        assert StageType.SEQUENTIAL.value == "sequential"
        assert StageType.LOOP.value == "loop"
        assert StageType.SINGLE.value == "single"


# ── TaskArchitect ────────────────────────────────────────────────────


class TestTaskArchitectAnalyse:
    @pytest.mark.asyncio
    async def test_analyse_returns_blueprint(self):
        mock_response = MagicMock()
        mock_response.text = json.dumps(
            {
                "stages": [
                    {
                        "name": "research",
                        "type": "parallel",
                        "tasks": [
                            {
                                "id": "t1",
                                "description": "find data",
                                "persona_id": "researcher",
                                "instruction": "search",
                            },
                            {
                                "id": "t2",
                                "description": "get news",
                                "persona_id": "researcher",
                                "instruction": "news",
                            },
                        ],
                    },
                    {
                        "name": "synthesis",
                        "type": "single",
                        "tasks": [
                            {
                                "id": "t3",
                                "description": "summarise",
                                "persona_id": "analyst",
                                "instruction": "summarise",
                            },
                        ],
                    },
                ]
            }
        )
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        architect = TaskArchitect(user_id="u1")
        with patch("google.genai.Client", return_value=mock_client):
            bp = await architect.analyse_task("analyse Tesla stock")

        assert isinstance(bp, PipelineBlueprint)
        assert len(bp.stages) == 2
        assert bp.total_agents == 3

    @pytest.mark.asyncio
    async def test_analyse_fallback_on_bad_json(self):
        mock_response = MagicMock()
        mock_response.text = "NOT JSON AT ALL"
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        architect = TaskArchitect(user_id="u1")
        with patch("google.genai.Client", return_value=mock_client):
            bp = await architect.analyse_task("do something complex")

        # Should fallback to single-stage
        assert len(bp.stages) == 1
        assert bp.stages[0].tasks[0].persona_id == "assistant"

    @pytest.mark.asyncio
    async def test_analyse_strips_code_fences(self):
        raw = json.dumps(
            {
                "stages": [
                    {
                        "name": "s1",
                        "type": "single",
                        "tasks": [
                            {
                                "id": "t1",
                                "description": "x",
                                "persona_id": "coder",
                                "instruction": "x",
                            }
                        ],
                    }
                ]
            }
        )
        mock_response = MagicMock()
        mock_response.text = f"```json\n{raw}\n```"
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        architect = TaskArchitect(user_id="u1")
        with patch("google.genai.Client", return_value=mock_client):
            bp = await architect.analyse_task("write code")

        assert bp.stages[0].tasks[0].persona_id == "coder"


class TestTaskArchitectBuild:
    def test_builds_parallel_pipeline(self):
        bp = PipelineBlueprint(
            task_description="test",
            stages=[
                TaskStage(
                    name="gather",
                    stage_type=StageType.PARALLEL,
                    tasks=[
                        SubTask(id="t1", description="a", persona_id="researcher"),
                        SubTask(id="t2", description="b", persona_id="analyst"),
                    ],
                ),
            ],
        )
        architect = TaskArchitect(user_id="u1")
        pipeline = architect.build_pipeline(bp)
        from google.adk.agents import ParallelAgent

        assert isinstance(pipeline, ParallelAgent)
        assert len(pipeline.sub_agents) == 2

    def test_builds_sequential_pipeline(self):
        bp = PipelineBlueprint(
            task_description="test",
            stages=[
                TaskStage(
                    name="s1",
                    stage_type=StageType.SEQUENTIAL,
                    tasks=[SubTask(id="t1", description="a"), SubTask(id="t2", description="b")],
                ),
            ],
        )
        architect = TaskArchitect(user_id="u1")
        pipeline = architect.build_pipeline(bp)
        from google.adk.agents import SequentialAgent

        assert isinstance(pipeline, SequentialAgent)

    def test_builds_loop_pipeline(self):
        bp = PipelineBlueprint(
            task_description="test",
            stages=[
                TaskStage(
                    name="refine",
                    stage_type=StageType.LOOP,
                    tasks=[SubTask(id="t1", description="iterate")],
                    max_iterations=4,
                ),
            ],
        )
        architect = TaskArchitect(user_id="u1")
        pipeline = architect.build_pipeline(bp)
        from google.adk.agents import LoopAgent

        assert isinstance(pipeline, LoopAgent)
        assert pipeline.max_iterations == 4

    def test_builds_hybrid_pipeline(self):
        bp = PipelineBlueprint(
            task_description="test",
            stages=[
                TaskStage(
                    name="gather",
                    stage_type=StageType.PARALLEL,
                    tasks=[SubTask(id="t1", description="a"), SubTask(id="t2", description="b")],
                ),
                TaskStage(
                    name="analyse",
                    stage_type=StageType.SINGLE,
                    tasks=[SubTask(id="t3", description="c")],
                ),
                TaskStage(
                    name="refine",
                    stage_type=StageType.LOOP,
                    tasks=[SubTask(id="t4", description="d")],
                    max_iterations=3,
                ),
            ],
        )
        architect = TaskArchitect(user_id="u1")
        pipeline = architect.build_pipeline(bp)
        from google.adk.agents import SequentialAgent

        # Hybrid pipeline is wrapped in a SequentialAgent
        assert isinstance(pipeline, SequentialAgent)
        assert len(pipeline.sub_agents) == 3

    def test_single_task_returns_unwrapped_agent(self):
        bp = PipelineBlueprint(
            task_description="test",
            stages=[
                TaskStage(
                    name="execute",
                    stage_type=StageType.SINGLE,
                    tasks=[SubTask(id="t1", description="just do it")],
                ),
            ],
        )
        architect = TaskArchitect(user_id="u1")
        pipeline = architect.build_pipeline(bp)
        from google.adk.agents import Agent

        assert isinstance(pipeline, Agent)
        assert pipeline.name == "t1"


class TestTaskArchitectEvents:
    @pytest.mark.asyncio
    async def test_publish_blueprint(self):
        bp = PipelineBlueprint(task_description="test", stages=[])
        architect = TaskArchitect(user_id="u1")
        architect._event_bus = MagicMock()
        architect._event_bus.publish = AsyncMock()

        await architect.publish_blueprint(bp)
        architect._event_bus.publish.assert_awaited_once()
        call_args = architect._event_bus.publish.call_args
        assert call_args[0][0] == "u1"
        event = json.loads(call_args[0][1])
        assert event["type"] == "pipeline_created"

    @pytest.mark.asyncio
    async def test_publish_stage_update(self):
        architect = TaskArchitect(user_id="u1")
        architect._event_bus = MagicMock()
        architect._event_bus.publish = AsyncMock()

        await architect.publish_stage_update("pid1", "gather", "running", 0.5)
        event = json.loads(architect._event_bus.publish.call_args[0][1])
        assert event["type"] == "pipeline_progress"
        assert event["pipeline_id"] == "pid1"
        assert event["progress"] == 0.5


class TestComplexityThreshold:
    def test_threshold_value(self):
        assert COMPLEXITY_THRESHOLD == 2
