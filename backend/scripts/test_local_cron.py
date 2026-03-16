"""Test script for local dev cron runner.

Creates a scheduled task with a 'every minute' cron and a fast poll interval,
then watches for it to execute within ~20 seconds.

Usage:
    cd backend
    uv run python scripts/test_local_cron.py
"""

import asyncio
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load .env before importing app modules
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.config import settings  # noqa: E402


async def main():
    from app.services.scheduler_service import get_scheduler_service

    svc = get_scheduler_service()
    user_id = "test_cron_user"

    print(f"[1/5] Creating scheduled task (every minute cron)...")
    task = await svc.create_task(
        user_id=user_id,
        description="Test cron job — echo hello",
        action="run_agent_query",
        schedule="* * * * *",  # every minute
        schedule_type="cron",
        action_params={"query": "Say 'Hello from cron!' and nothing else."},
    )
    print(f"       Task ID: {task.id}")
    print(f"       Schedule: {task.schedule}")
    print(f"       Status: {task.status}")

    print(f"\n[2/5] Starting local cron runner (poll every 5s)...")
    await svc.start_local_cron(poll_interval=5.0)

    print(f"\n[3/5] Waiting up to 70s for cron to fire...")
    max_wait = 70
    for i in range(max_wait):
        await asyncio.sleep(1)
        # Reload task from Firestore
        updated = await svc.get_task(user_id=user_id, task_id=task.id)
        if updated and updated.run_count > 0:
            print(f"\n[4/5] CRON FIRED after ~{i+1}s!")
            print(f"       Run count: {updated.run_count}")
            print(f"       Last run: {updated.last_run_at}")
            print(f"       Result: {updated.last_result[:200]}")
            break
        if i % 10 == 0 and i > 0:
            print(f"       ... still waiting ({i}s elapsed)")
    else:
        print(f"\n[4/5] TIMEOUT — Task did not fire within {max_wait}s")

    print(f"\n[5/5] Cleaning up...")
    await svc.stop_local_cron()
    await svc.delete_task(user_id=user_id, task_id=task.id)
    print("       Done! Task deleted.")


if __name__ == "__main__":
    asyncio.run(main())
