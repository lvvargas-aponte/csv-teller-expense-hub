"""Repository for the sync bookkeeping tables.

Three concerns, one module because they are one subject: what the last cycle
did (``sync_runs``), what it overwrote (``sync_corrections``), and where each
published row stands (``sync_row_state``).

``transactions_updated_at`` reaches into ``json_stores`` on purpose. Transactions
are JSON documents there, and PgStore stamps ``updated_at`` on every write, which
makes that column the only "the user edited this row" signal available — the one
the corrections feed filters on.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from db.base import sync_engine

_CORRECTION_COLS = (
    "id, period, txn_id, column_name, sheet_value, app_value, "
    "detected_at, acknowledged_at"
)
_RUN_COLS = (
    "id, period, started_at, finished_at, direction, status, refusal_reason, "
    "rows_pushed, rows_pulled, rows_deleted, error_detail"
)
_ROW_STATE_COLS = (
    "txn_id, transaction_id, period, sheet_synced_at, "
    "dispute_flag, dispute_by, dispute_note"
)


def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def _correction_to_dict(row) -> Dict[str, Any]:
    return {
        "id": int(row[0]),
        "period": row[1],
        "txn_id": row[2],
        "column_name": row[3],
        "sheet_value": row[4],
        "app_value": row[5],
        "detected_at": _iso(row[6]),
        "acknowledged_at": _iso(row[7]),
    }


def _run_to_dict(row) -> Dict[str, Any]:
    return {
        "id": int(row[0]),
        "period": row[1],
        "started_at": _iso(row[2]),
        "finished_at": _iso(row[3]),
        "direction": row[4],
        "status": row[5],
        "refusal_reason": row[6],
        "rows_pushed": int(row[7]),
        "rows_pulled": int(row[8]),
        "rows_deleted": int(row[9]),
        "error_detail": row[10],
    }


def _row_state_to_dict(row) -> Dict[str, Any]:
    return {
        "txn_id": row[0],
        "transaction_id": row[1],
        "period": row[2],
        "sheet_synced_at": row[3],
        "dispute_flag": row[4],
        "dispute_by": row[5],
        "dispute_note": row[6],
    }


# --------------------------------------------------------------------------
# Corrections feed
# --------------------------------------------------------------------------

def record_corrections(period: str, items: List[Dict[str, Any]]) -> int:
    if not items:
        return 0
    params = [
        {
            "period": period,
            "txn_id": i["txn_id"],
            "column_name": i["column_name"],
            "sheet_value": i.get("sheet_value") or "",
            "app_value": i.get("app_value") or "",
        }
        for i in items
    ]
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sync_corrections "
                "(period, txn_id, column_name, sheet_value, app_value) "
                "VALUES (:period, :txn_id, :column_name, :sheet_value, :app_value)"
            ),
            params,
        )
    return len(items)


def list_unacknowledged(limit: int = 100) -> List[Dict[str, Any]]:
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT {_CORRECTION_COLS} FROM sync_corrections "
                "WHERE acknowledged_at IS NULL "
                "ORDER BY detected_at DESC, id DESC LIMIT :n"
            ),
            {"n": limit},
        ).fetchall()
    return [_correction_to_dict(r) for r in rows]


def acknowledge(correction_id: int) -> bool:
    with sync_engine.begin() as conn:
        result = conn.execute(
            text(
                "UPDATE sync_corrections SET acknowledged_at = NOW() "
                "WHERE id = :id AND acknowledged_at IS NULL"
            ),
            {"id": correction_id},
        )
    return result.rowcount > 0


# --------------------------------------------------------------------------
# Run log
# --------------------------------------------------------------------------

def start_run(period: str, direction: str) -> int:
    with sync_engine.begin() as conn:
        row = conn.execute(
            text(
                "INSERT INTO sync_runs (period, direction) "
                "VALUES (:p, :d) RETURNING id"
            ),
            {"p": period, "d": direction},
        ).fetchone()
    return int(row[0])


def finish_run(
    run_id: int,
    status: str,
    *,
    rows_pushed: int = 0,
    rows_pulled: int = 0,
    rows_deleted: int = 0,
    refusal_reason: Optional[str] = None,
    error_detail: Optional[str] = None,
) -> None:
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE sync_runs SET finished_at = NOW(), status = :status, "
                "  rows_pushed = :pushed, rows_pulled = :pulled, "
                "  rows_deleted = :deleted, refusal_reason = :reason, "
                "  error_detail = :detail "
                "WHERE id = :id"
            ),
            {
                "id": run_id,
                "status": status,
                "pushed": rows_pushed,
                "pulled": rows_pulled,
                "deleted": rows_deleted,
                "reason": refusal_reason,
                "detail": error_detail,
            },
        )


def _latest_run(where: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(
                f"SELECT {_RUN_COLS} FROM sync_runs {where} "
                "ORDER BY started_at DESC, id DESC LIMIT 1"
            ),
            params,
        ).fetchone()
    return _run_to_dict(row) if row else None


def last_run(period: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if period is None:
        return _latest_run("", {})
    return _latest_run("WHERE period = :p", {"p": period})


def last_ok_run(period: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if period is None:
        return _latest_run("WHERE status = 'ok'", {})
    return _latest_run("WHERE status = 'ok' AND period = :p", {"p": period})


# --------------------------------------------------------------------------
# Per-row state
# --------------------------------------------------------------------------

def mark_synced(txn_id: str, transaction_id: str, period: str) -> None:
    """Advance the push watermark. Never touches the dispute columns."""
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sync_row_state "
                "  (txn_id, transaction_id, period, sheet_synced_at) "
                "VALUES (:txn_id, :transaction_id, :period, NOW()) "
                "ON CONFLICT (txn_id) DO UPDATE SET "
                "  transaction_id = EXCLUDED.transaction_id, "
                "  period = EXCLUDED.period, "
                "  sheet_synced_at = NOW()"
            ),
            {"txn_id": txn_id, "transaction_id": transaction_id, "period": period},
        )


def synced_at_map(txn_ids: List[str]) -> Dict[str, datetime]:
    if not txn_ids:
        return {}
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT txn_id, sheet_synced_at FROM sync_row_state "
                "WHERE txn_id = ANY(:ids) AND sheet_synced_at IS NOT NULL"
            ),
            {"ids": list(txn_ids)},
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def set_disputes_bulk(items: List[Dict[str, Any]]) -> int:
    """Upsert dispute state for many rows in one ``executemany`` round trip.

    Each item carries ``txn_id``, ``flag``, ``by``, ``note`` — the shape
    ``sync_period`` already builds from ``PullResult.my_disputes``. The only
    place this upsert's SQL is written; ``set_disputes`` delegates here as a
    single-row convenience so the two can never drift apart.
    """
    if not items:
        return 0
    params = [
        {
            "txn_id": i["txn_id"],
            "flag": i.get("flag"),
            "by": i.get("by"),
            "note": i.get("note"),
        }
        for i in items
    ]
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sync_row_state "
                "  (txn_id, transaction_id, period, dispute_flag, dispute_by, dispute_note) "
                "VALUES (:txn_id, :txn_id, '', :flag, :by, :note) "
                "ON CONFLICT (txn_id) DO UPDATE SET "
                "  dispute_flag = EXCLUDED.dispute_flag, "
                "  dispute_by = EXCLUDED.dispute_by, "
                "  dispute_note = EXCLUDED.dispute_note"
            ),
            params,
        )
    return len(items)


def set_disputes(
    txn_id: str, flag: Optional[str], by: Optional[str], note: Optional[str]
) -> None:
    """Record a dispute the peer raised against one of our rows.

    A single-row convenience kept for tests; production code batches through
    ``set_disputes_bulk``, which owns the actual upsert SQL.
    """
    set_disputes_bulk([{"txn_id": txn_id, "flag": flag, "by": by, "note": note}])


def get_row_state(txn_id: str) -> Optional[Dict[str, Any]]:
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {_ROW_STATE_COLS} FROM sync_row_state WHERE txn_id = :id"),
            {"id": txn_id},
        ).fetchone()
    return _row_state_to_dict(row) if row else None


def list_disputes_against_me() -> List[Dict[str, Any]]:
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT {_ROW_STATE_COLS} FROM sync_row_state "
                "WHERE dispute_flag = 'Y' ORDER BY txn_id"
            )
        ).fetchall()
    return [_row_state_to_dict(r) for r in rows]


def delete_row_state(txn_ids: List[str]) -> int:
    if not txn_ids:
        return 0
    with sync_engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM sync_row_state WHERE txn_id = ANY(:ids)"),
            {"ids": list(txn_ids)},
        )
    return result.rowcount


def transactions_updated_at(transaction_ids: List[str]) -> Dict[str, datetime]:
    """When each transaction document was last written, from ``json_stores``."""
    if not transaction_ids:
        return {}
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT key, updated_at FROM json_stores "
                "WHERE store_name = 'transactions' AND key = ANY(:ids)"
            ),
            {"ids": list(transaction_ids)},
        ).fetchall()
    return {r[0]: r[1] for r in rows}
