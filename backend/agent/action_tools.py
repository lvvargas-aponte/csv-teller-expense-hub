"""Action tools — Fin-triggered data refreshes.

Thin wrappers over the same coroutines the REST endpoints use
(``routers.teller`` / ``routers.balances`` / ``routers.snaptrade``), so
there is exactly one sync implementation. These are Fin's only
state-mutating tools; all three are idempotent syncs. Config problems
(no Teller tokens, SnapTrade not connected) come back as structured
``synced: false`` payloads instead of tool errors so the model can tell
the user what to connect.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import HTTPException

from agent.schemas import (
    CancelScheduledTaskArgs,
    ListScheduledTasksArgs,
    RefreshBalancesArgs,
    ScheduleSyncArgs,
    SyncInvestmentsArgs,
    SyncTransactionsArgs,
)


async def _sync_transactions(args: SyncTransactionsArgs) -> Dict[str, Any]:
    from models import TellerSyncRequest
    from routers.teller import sync_teller_transactions

    try:
        out = await sync_teller_transactions(
            TellerSyncRequest(from_date=args.from_date, to_date=args.to_date)
        )
    except HTTPException as e:
        return {"synced": False, "note": str(e.detail)}
    account_errors = [d for d in out["details"] if d.get("error")]
    return {
        "synced": True,
        "from_date": out["from_date"],
        "to_date": out["to_date"],
        "total_fetched": out["total_fetched"],
        "total_new": out["total_new"],
        "account_errors": account_errors,
    }


async def _refresh_balances(args: RefreshBalancesArgs) -> Dict[str, Any]:
    from routers.balances import get_balances_summary

    try:
        summary = await get_balances_summary(force=True)
    except HTTPException as e:
        return {"refreshed": False, "note": str(e.detail)}
    return {
        "refreshed": True,
        "net_worth": summary.net_worth,
        "total_cash": summary.total_cash,
        "total_credit_debt": summary.total_credit_debt,
        "total_investments": summary.total_investments,
        "account_count": len(summary.accounts),
    }


async def _sync_investments(args: SyncInvestmentsArgs) -> Dict[str, Any]:
    from routers.snaptrade import sync_snaptrade

    try:
        out = await sync_snaptrade()
    except HTTPException as e:
        return {"synced": False, "note": str(e.detail)}
    return {
        "synced": True,
        "accounts": out["accounts"],
        "details": out["details"],
    }


async def _schedule_sync(args: ScheduleSyncArgs) -> Dict[str, Any]:
    from db import scheduled_tasks_repo

    existing = scheduled_tasks_repo.find_by_type(args.task_type)
    if existing:
        return {
            "created": False,
            "task": existing,
            "note": (
                "A schedule for this sync already exists. Cancel it first "
                "with cancel_scheduled_task if the user wants a different cadence."
            ),
        }
    task = scheduled_tasks_repo.create_task(args.task_type, args.interval_days)
    return {"created": True, "task": task}


async def _list_scheduled_tasks(args: ListScheduledTasksArgs) -> Dict[str, Any]:
    from db import scheduled_tasks_repo

    tasks = scheduled_tasks_repo.list_tasks()
    return {"count": len(tasks), "tasks": tasks}


async def _cancel_scheduled_task(args: CancelScheduledTaskArgs) -> Dict[str, Any]:
    from db import scheduled_tasks_repo

    deleted = scheduled_tasks_repo.delete_task(args.task_id)
    return {
        "cancelled": deleted,
        "note": None if deleted else "No scheduled task with that id.",
    }


def build_action_tools() -> list:
    from agent.tools import Tool

    return [
        Tool(
            name="sync_transactions",
            description=(
                "Pull the latest transactions from the user's connected bank "
                "accounts (Teller). SLOW (10-30s) — only when freshness "
                "matters: the user asks about today/this week, says data "
                "looks stale, or explicitly asks to refresh. Defaults to the "
                "previous-month date range; pass from_date/to_date (ISO) to "
                "cover recent days. After syncing, use the normal query "
                "tools to answer."
            ),
            args_model=SyncTransactionsArgs,
            handler=_sync_transactions,
        ),
        Tool(
            name="refresh_balances",
            description=(
                "Refresh live account balances from the bank (bypasses the "
                "cache) and return the new totals. Use when the user asks "
                "for 'current' or 'right now' balances, or after a big "
                "purchase/payment they just made."
            ),
            args_model=RefreshBalancesArgs,
            handler=_refresh_balances,
        ),
        Tool(
            name="sync_investments",
            description=(
                "Re-pull the user's brokerage holdings from SnapTrade so "
                "get_investments reflects current positions and values. Use "
                "before portfolio advice when holdings may be stale, or when "
                "the user asks to refresh their investments."
            ),
            args_model=SyncInvestmentsArgs,
            handler=_sync_investments,
        ),
        Tool(
            name="schedule_sync",
            description=(
                "Set up a recurring background sync ('sync my transactions "
                "every week'). task_type is one of sync_transactions / "
                "refresh_balances / sync_investments; interval_days defaults "
                "to 7 (weekly). One schedule per sync type — check "
                "list_scheduled_tasks if unsure. Confirm to the user what "
                "was scheduled and when it first runs."
            ),
            args_model=ScheduleSyncArgs,
            handler=_schedule_sync,
        ),
        Tool(
            name="list_scheduled_tasks",
            description=(
                "List the recurring background syncs: cadence, next run, "
                "last run and its outcome. Use when the user asks what's "
                "scheduled or whether a sync ran."
            ),
            args_model=ListScheduledTasksArgs,
            handler=_list_scheduled_tasks,
        ),
        Tool(
            name="cancel_scheduled_task",
            description=(
                "Cancel a recurring background sync by id (from "
                "list_scheduled_tasks). Confirm with the user before "
                "cancelling unless they explicitly asked."
            ),
            args_model=CancelScheduledTaskArgs,
            handler=_cancel_scheduled_task,
        ),
    ]
