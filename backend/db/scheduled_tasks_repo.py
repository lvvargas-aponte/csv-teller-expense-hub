"""Repository for the ``scheduled_tasks`` table — recurring data-sync jobs.

Same sync-engine pattern as the other repos. The scheduler loop and
Fin's scheduling tools are the only callers.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text

from db.base import sync_engine

VALID_TASK_TYPES = ("sync_transactions", "refresh_balances", "sync_investments")

_SELECT_COLS = (
    "id, task_type, interval_days, next_run_at, last_run_at, "
    "last_status, last_result, enabled, created_at"
)


def _row_to_dict(row) -> Dict[str, Any]:
    return {
        "id": int(row[0]),
        "task_type": row[1],
        "interval_days": int(row[2]),
        "next_run_at": row[3].isoformat() if row[3] else None,
        "last_run_at": row[4].isoformat() if row[4] else None,
        "last_status": row[5],
        "last_result": row[6],
        "enabled": bool(row[7]),
        "created_at": row[8].isoformat() if row[8] else None,
    }


def list_tasks(enabled_only: bool = False) -> List[Dict[str, Any]]:
    sql = f"SELECT {_SELECT_COLS} FROM scheduled_tasks"
    if enabled_only:
        sql += " WHERE enabled"
    sql += " ORDER BY next_run_at ASC"
    with sync_engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_task(task_id: int) -> Optional[Dict[str, Any]]:
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {_SELECT_COLS} FROM scheduled_tasks WHERE id = :id"),
            {"id": task_id},
        ).fetchone()
    return _row_to_dict(row) if row else None


def find_by_type(task_type: str) -> Optional[Dict[str, Any]]:
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(
                f"SELECT {_SELECT_COLS} FROM scheduled_tasks "
                "WHERE task_type = :t AND enabled LIMIT 1"
            ),
            {"t": task_type},
        ).fetchone()
    return _row_to_dict(row) if row else None


def create_task(task_type: str, interval_days: int = 7) -> Dict[str, Any]:
    if task_type not in VALID_TASK_TYPES:
        raise ValueError(f"task_type must be one of {VALID_TASK_TYPES}")
    with sync_engine.begin() as conn:
        row = conn.execute(
            text(
                "INSERT INTO scheduled_tasks (task_type, interval_days, next_run_at) "
                "VALUES (:t, :d, NOW() + make_interval(days => :d)) "
                f"RETURNING {_SELECT_COLS}"
            ),
            {"t": task_type, "d": interval_days},
        ).fetchone()
    return _row_to_dict(row)


def due_tasks() -> List[Dict[str, Any]]:
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT {_SELECT_COLS} FROM scheduled_tasks "
                "WHERE enabled AND next_run_at <= NOW() "
                "ORDER BY next_run_at ASC"
            )
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def record_run(task_id: int, status: str, result: Optional[str]) -> None:
    """Mark a run and roll next_run_at forward by the task's interval."""
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE scheduled_tasks SET "
                "  last_run_at = NOW(), "
                "  last_status = :status, "
                "  last_result = CAST(:result AS JSONB), "
                "  next_run_at = NOW() + make_interval(days => interval_days) "
                "WHERE id = :id"
            ),
            {"id": task_id, "status": status, "result": result},
        )


def delete_task(task_id: int) -> bool:
    with sync_engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM scheduled_tasks WHERE id = :id"),
            {"id": task_id},
        )
    return result.rowcount > 0
