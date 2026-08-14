"""Scheduler + scheduled_tasks repo — real test DB, mocked sync jobs."""
import asyncio
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy import text

import scheduler
from db import scheduled_tasks_repo
from db.base import sync_engine


def _run(coro):
    return asyncio.run(coro)


def _make_due(task_id: int) -> None:
    with sync_engine.begin() as conn:
        conn.execute(
            text("UPDATE scheduled_tasks SET next_run_at = NOW() - INTERVAL '1 minute' WHERE id = :id"),
            {"id": task_id},
        )


class TestRepo:
    def test_create_and_list(self):
        task = scheduled_tasks_repo.create_task("sync_transactions", interval_days=7)
        assert task["task_type"] == "sync_transactions"
        assert task["interval_days"] == 7
        assert task["enabled"] is True
        assert task["next_run_at"] is not None
        assert scheduled_tasks_repo.list_tasks()[0]["id"] == task["id"]

    def test_find_by_type(self):
        scheduled_tasks_repo.create_task("sync_investments")
        assert scheduled_tasks_repo.find_by_type("sync_investments") is not None
        assert scheduled_tasks_repo.find_by_type("sync_transactions") is None

    def test_new_task_is_not_immediately_due(self):
        scheduled_tasks_repo.create_task("sync_transactions")
        assert scheduled_tasks_repo.due_tasks() == []

    def test_delete(self):
        task = scheduled_tasks_repo.create_task("refresh_balances")
        assert scheduled_tasks_repo.delete_task(task["id"]) is True
        assert scheduled_tasks_repo.delete_task(task["id"]) is False


class TestRunDueTasks:
    def test_due_task_runs_and_rolls_forward(self):
        task = scheduled_tasks_repo.create_task("sync_transactions", interval_days=7)
        _make_due(task["id"])

        fake = AsyncMock(return_value={"total_fetched": 5, "total_new": 2})
        with patch.dict(scheduler.JOBS, {"sync_transactions": fake}):
            ran = _run(scheduler.run_due_tasks())

        assert ran == 1
        fake.assert_awaited_once()
        after = scheduled_tasks_repo.get_task(task["id"])
        assert after["last_status"] == "ok"
        assert after["last_result"]["total_new"] == 2
        assert after["last_run_at"] is not None
        # next_run_at rolled ~7 days forward — no longer due.
        assert scheduled_tasks_repo.due_tasks() == []

    def test_job_failure_recorded_and_rescheduled(self):
        task = scheduled_tasks_repo.create_task("sync_investments")
        _make_due(task["id"])

        fake = AsyncMock(side_effect=HTTPException(409, "Connect a brokerage first."))
        with patch.dict(scheduler.JOBS, {"sync_investments": fake}):
            ran = _run(scheduler.run_due_tasks())

        assert ran == 1
        after = scheduled_tasks_repo.get_task(task["id"])
        assert after["last_status"] == "error"
        assert "brokerage" in after["last_result"]["note"]
        assert scheduled_tasks_repo.due_tasks() == []

    def test_not_due_tasks_untouched(self):
        scheduled_tasks_repo.create_task("sync_transactions")
        fake = AsyncMock()
        with patch.dict(scheduler.JOBS, {"sync_transactions": fake}):
            ran = _run(scheduler.run_due_tasks())
        assert ran == 0
        fake.assert_not_awaited()


class TestScheduleTools:
    def test_schedule_sync_creates_once(self):
        from agent.action_tools import _schedule_sync
        from agent.schemas import ScheduleSyncArgs

        out = _run(_schedule_sync(ScheduleSyncArgs(task_type="sync_transactions")))
        assert out["created"] is True
        assert out["task"]["interval_days"] == 7

        again = _run(_schedule_sync(ScheduleSyncArgs(task_type="sync_transactions")))
        assert again["created"] is False
        assert "already exists" in again["note"]

    def test_list_and_cancel(self):
        from agent.action_tools import (
            _cancel_scheduled_task,
            _list_scheduled_tasks,
            _schedule_sync,
        )
        from agent.schemas import (
            CancelScheduledTaskArgs,
            ListScheduledTasksArgs,
            ScheduleSyncArgs,
        )

        created = _run(_schedule_sync(ScheduleSyncArgs(task_type="sync_investments", interval_days=14)))
        listed = _run(_list_scheduled_tasks(ListScheduledTasksArgs()))
        assert listed["count"] == 1
        assert listed["tasks"][0]["interval_days"] == 14

        out = _run(_cancel_scheduled_task(CancelScheduledTaskArgs(task_id=created["task"]["id"])))
        assert out["cancelled"] is True
        assert _run(_list_scheduled_tasks(ListScheduledTasksArgs()))["count"] == 0
