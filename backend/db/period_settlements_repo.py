"""Repository for ``period_settlements`` — each instance's position on a month.

One row per (period, user_id). Mine is authored here and pushed to the hidden
``_sync`` worksheet; the peer's is pulled from it and never authored locally.

Settlement is advisory: either instance may mark a month paid without the
other's agreement, so ``pif_at`` lives on each side's own row. ``is_settled``
is therefore an OR across both rows, not an AND.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from db.base import sync_engine

_COLS = (
    "period, user_id, ready_at, closed_at, net_amount, debtor_user_id, "
    "pif_at, pif_note, updated_at"
)


def _iso(value) -> Optional[str]:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _to_dict(row) -> Dict[str, Any]:
    return {
        "period": row[0],
        "user_id": row[1],
        "ready_at": _iso(row[2]),
        "closed_at": _iso(row[3]),
        "net_amount": float(row[4]) if row[4] is not None else None,
        "debtor_user_id": row[5],
        "pif_at": _iso(row[6]),
        "pif_note": row[7],
        "updated_at": _iso(row[8]),
    }


_UPSERT_SQL = text(
    "INSERT INTO period_settlements ("
    "  period, user_id, ready_at, closed_at, net_amount, debtor_user_id, "
    "  pif_at, pif_note"
    ") VALUES ("
    "  :period, :user_id, CAST(:ready_at AS TIMESTAMPTZ), "
    "  CAST(:closed_at AS TIMESTAMPTZ), :net_amount, :debtor_user_id, "
    "  CAST(:pif_at AS TIMESTAMPTZ), :pif_note"
    ") ON CONFLICT (period, user_id) DO UPDATE SET "
    "  ready_at = EXCLUDED.ready_at, "
    "  closed_at = EXCLUDED.closed_at, "
    "  net_amount = EXCLUDED.net_amount, "
    "  debtor_user_id = EXCLUDED.debtor_user_id, "
    "  pif_at = EXCLUDED.pif_at, "
    "  pif_note = EXCLUDED.pif_note, "
    "  updated_at = NOW()"
)

_FIELDS = (
    "ready_at", "closed_at", "net_amount", "debtor_user_id", "pif_at", "pif_note",
)


def upsert(period: str, user_id: str, **fields: Any) -> Dict[str, Any]:
    """Write one instance's whole record. Absent fields are cleared, not kept —
    the caller always passes the complete desired state so that withdrawing
    ready, or reopening a settled month, is a plain write rather than a delete.
    """
    params = {"period": period, "user_id": user_id}
    for name in _FIELDS:
        value = fields.get(name)
        params[name] = str(value) if isinstance(value, Decimal) else value

    with sync_engine.begin() as conn:
        conn.execute(_UPSERT_SQL, params)
    return get(period, user_id)


def get(period: str, user_id: str) -> Optional[Dict[str, Any]]:
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(
                f"SELECT {_COLS} FROM period_settlements "
                "WHERE period = :p AND user_id = :u"
            ),
            {"p": period, "u": user_id},
        ).fetchone()
    return _to_dict(row) if row else None


def list_for_period(period: str) -> List[Dict[str, Any]]:
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT {_COLS} FROM period_settlements "
                "WHERE period = :p ORDER BY user_id ASC"
            ),
            {"p": period},
        ).fetchall()
    return [_to_dict(r) for r in rows]


def settled_periods() -> List[str]:
    """Every period ANY instance has marked paid in full.

    An OR, not an AND: settlement is advisory, so one side saying it is paid
    closes the month for both. Reopening is equally one-sided.
    """
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT DISTINCT period FROM period_settlements "
                "WHERE pif_at IS NOT NULL ORDER BY period ASC"
            )
        ).fetchall()
    return [r[0] for r in rows]
