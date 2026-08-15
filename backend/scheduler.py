"""In-process scheduler for recurring data-sync jobs.

An asyncio loop started from the FastAPI lifespan checks ``scheduled_tasks``
every ``SCHEDULER_POLL_SEC`` and runs due jobs. Jobs reuse the exact same
coroutines the REST endpoints and Fin's action tools call — one sync
implementation everywhere. Job failures are recorded on the row
(``last_status``/``last_result``) and never kill the loop.

Single-process by design: the dev/prod compose runs one uvicorn worker.
If that ever changes, move to a DB advisory lock around ``run_due_tasks``.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict

from fastapi import HTTPException

from db import scheduled_tasks_repo

logger = logging.getLogger(__name__)

SCHEDULER_POLL_SEC = 60


async def _run_sync_transactions() -> Dict[str, Any]:
    from models import SimplefinSyncRequest
    from routers.simplefin import sync_simplefin_transactions

    out = await sync_simplefin_transactions(SimplefinSyncRequest())
    return {"total_fetched": out["total_fetched"], "total_new": out["total_new"]}


async def _run_refresh_balances() -> Dict[str, Any]:
    from routers.balances import get_balances_summary

    summary = await get_balances_summary(force=True)
    return {"net_worth": summary.net_worth, "account_count": len(summary.accounts)}


async def _run_sync_investments() -> Dict[str, Any]:
    from routers.snaptrade import sync_snaptrade

    out = await sync_snaptrade()
    return {"accounts": out["accounts"]}


JOBS = {
    "sync_transactions": _run_sync_transactions,
    "refresh_balances": _run_refresh_balances,
    "sync_investments": _run_sync_investments,
}


async def run_due_tasks() -> int:
    """Run every due task once. Returns the number of tasks executed."""
    ran = 0
    for task in scheduled_tasks_repo.due_tasks():
        job = JOBS.get(task["task_type"])
        if job is None:
            scheduled_tasks_repo.record_run(
                task["id"], "error", json.dumps({"note": "unknown task_type"})
            )
            continue
        try:
            result = await job()
            scheduled_tasks_repo.record_run(task["id"], "ok", json.dumps(result, default=str))
            logger.info(f"[scheduler] {task['task_type']} #{task['id']} ok: {result}")
        except HTTPException as e:
            scheduled_tasks_repo.record_run(
                task["id"], "error", json.dumps({"note": str(e.detail)})
            )
            logger.warning(f"[scheduler] {task['task_type']} #{task['id']} failed: {e.detail}")
        except Exception as e:
            scheduled_tasks_repo.record_run(
                task["id"], "error", json.dumps({"note": str(e)})
            )
            logger.warning(f"[scheduler] {task['task_type']} #{task['id']} failed: {e}")
        ran += 1
    return ran


async def scheduler_loop() -> None:
    logger.info(f"[scheduler] started (poll every {SCHEDULER_POLL_SEC}s)")
    while True:
        try:
            await run_due_tasks()
        except Exception as e:
            logger.warning(f"[scheduler] due-task sweep failed: {e}")
        await asyncio.sleep(SCHEDULER_POLL_SEC)


def start_scheduler() -> asyncio.Task:
    return asyncio.create_task(scheduler_loop(), name="scheduled-tasks-loop")
