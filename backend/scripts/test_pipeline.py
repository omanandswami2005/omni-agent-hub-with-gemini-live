"""Test TaskArchitect pipeline — chained tool calling E2E.

Exercises the full TaskArchitect flow with a realistic multi-step
scenario:  "make a grocery list, email it to me, and save it on my
desktop".

The script:
    1. Calls ``TaskArchitect.analyse_task()`` → LLM decomposes the task
    2. Builds the ADK pipeline (Sequential/Parallel agents)
    3. Executes the pipeline, printing live stage progress from EventBus
    4. Collects and displays results

Usage
-----
    cd backend && python scripts/test_pipeline.py

    # Custom task:
    python scripts/test_pipeline.py --task "research Python best practices, \
        write a summary document, and save it on my desktop"

    # Skip execution (decompose only):
    python scripts/test_pipeline.py --decompose-only

Requires: google-genai, google-adk, python-dotenv
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# ── Ensure backend/ is on sys.path ──
BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Load .env before any app imports
from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env")


DEFAULT_TASK = (
    "Make a grocery list for a healthy week of meals, "
    "email it to me at user@example.com, "
    "and save it as a text file on my desktop."
)

TEST_USER_ID = "pipeline-test-user"


async def _event_listener(user_id: str, stop_event: asyncio.Event) -> list[dict]:
    """Subscribe to EventBus and collect pipeline events."""
    from app.services.event_bus import get_event_bus

    bus = get_event_bus()
    queue = bus.create_queue()
    bus.subscribe(user_id, queue)

    events: list[dict] = []
    try:
        while not stop_event.is_set():
            try:
                raw = await asyncio.wait_for(queue.get(), timeout=0.5)
                event = json.loads(raw)
                events.append(event)
                _print_event(event)
            except TimeoutError:
                continue
    finally:
        bus.unsubscribe(user_id, queue)
    return events


def _print_event(event: dict) -> None:
    """Pretty-print a pipeline event."""
    etype = event.get("type", "?")
    if etype == "pipeline_created":
        pipeline = event["pipeline"]
        print(f"\n  {'='*50}")
        print(f"  Pipeline created: {pipeline['pipeline_id']}")
        print(f"  Task: {pipeline['task_description'][:80]}")
        print(f"  Stages: {len(pipeline['stages'])}  |  Total agents: {pipeline['total_agents']}")
        for stage in pipeline["stages"]:
            task_ids = [t["persona_id"] for t in stage["tasks"]]
            print(f"    [{stage['stage_type']}] {stage['name']} -> {', '.join(task_ids)}")
        print(f"  {'='*50}\n")
    elif etype == "pipeline_progress":
        status = event.get("status", "?")
        stage = event.get("stage", "?")
        progress = event.get("progress", 0)
        icons = {"pending": "⏳", "running": "🔄", "completed": "✅", "failed": "❌"}
        icon = icons.get(status, "❓")
        bar = f"[{'█' * int(progress * 10)}{'░' * (10 - int(progress * 10))}]"
        print(f"  {icon} {stage:>20}  {status:<10}  {bar}  {progress:.0%}")
    else:
        print(f"  📋 {etype}: {json.dumps(event)[:100]}")


async def run_decompose(task: str) -> None:
    """Decompose a task and print the blueprint (no execution)."""
    from app.agents.task_architect import TaskArchitect

    print(f"\n{'='*60}")
    print("  TaskArchitect — Decompose Only")
    print(f"{'='*60}")
    print(f"  Task: {task[:100]}")
    print()

    t0 = time.monotonic()
    architect = TaskArchitect(user_id=TEST_USER_ID)
    blueprint = await architect.analyse_task(task)
    elapsed = time.monotonic() - t0

    print(f"  Pipeline ID: {blueprint.pipeline_id}")
    print(f"  Stages: {len(blueprint.stages)}")
    print(f"  Total agents: {blueprint.total_agents}")
    print(f"  Decomposition time: {elapsed:.1f}s")
    print()
    print("  Blueprint JSON:")
    print(json.dumps(blueprint.to_dict(), indent=2))
    print(f"\n{'='*60}\n")


async def run_full_pipeline(task: str) -> None:
    """Decompose, build, and execute a pipeline with live events."""
    from app.agents.task_architect import TaskArchitect

    print(f"\n{'='*60}")
    print("  TaskArchitect — Full Pipeline Execution")
    print(f"{'='*60}")
    print(f"  Task: {task[:100]}")
    print(f"  User: {TEST_USER_ID}")
    print()

    # Start event listener in background
    stop_event = asyncio.Event()
    listener_task = asyncio.create_task(
        _event_listener(TEST_USER_ID, stop_event)
    )

    t0 = time.monotonic()

    # Phase 1: Decompose
    print("  [1/3] Decomposing task...")
    architect = TaskArchitect(user_id=TEST_USER_ID)
    blueprint = await architect.analyse_task(task)
    t_decompose = time.monotonic() - t0
    print(f"         Done ({t_decompose:.1f}s) — {len(blueprint.stages)} stages, {blueprint.total_agents} agents\n")

    # Publish blueprint (this triggers pipeline_created event)
    await architect.publish_blueprint(blueprint)
    # Give event listener time to process
    await asyncio.sleep(0.2)

    # Phase 2: Build pipeline
    print("  [2/3] Building ADK agent pipeline...")
    pipeline = architect.build_pipeline(blueprint)
    print(f"         Pipeline agent: {pipeline.name}\n")

    # Phase 3: Execute
    print("  [3/3] Executing pipeline (watch live progress below)...\n")
    t_exec_start = time.monotonic()
    summary = await architect.execute_pipeline(blueprint, pipeline)
    t_exec = time.monotonic() - t_exec_start

    # Stop listener and collect events
    stop_event.set()
    await asyncio.sleep(0.3)
    events = listener_task.result() if listener_task.done() else []

    # Print results
    print(f"\n  {'='*50}")
    print("  EXECUTION RESULTS")
    print(f"  {'='*50}")
    print(f"  Decomposition time: {t_decompose:.1f}s")
    print(f"  Execution time:     {t_exec:.1f}s")
    print(f"  Total time:         {time.monotonic() - t0:.1f}s")
    print(f"  Events captured:    {len(events)}")
    print("\n  --- Summary (first 2000 chars) ---")
    print(f"  {summary[:2000]}")
    print(f"\n  {'='*50}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Test TaskArchitect pipeline — chained tool calling E2E",
    )
    parser.add_argument(
        "--task",
        default=DEFAULT_TASK,
        help="The complex multi-step task to decompose and execute",
    )
    parser.add_argument(
        "--decompose-only",
        action="store_true",
        help="Only decompose (don't execute the pipeline)",
    )
    args = parser.parse_args()

    if args.decompose_only:
        asyncio.run(run_decompose(args.task))
    else:
        asyncio.run(run_full_pipeline(args.task))


if __name__ == "__main__":
    main()
