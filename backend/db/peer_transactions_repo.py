"""Repository for ``peer_shared_transactions`` — the peer's rows, imported from the sheet.

Kept apart from local transactions so no existing analytics query picks them
up. The upsert deliberately does NOT touch the dispute columns: those are ours
to write, and re-importing the peer's row must not erase a dispute we raised.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text

from db.base import sync_engine

_COLS = (
    "txn_id, owner_user_id, date, description, amount, who, "
    "person_1_owes, person_2_owes, notes, reviewed, payer_user_id, "
    "carried_from_period, settles_in_period, dispute_flag, dispute_by, "
    "dispute_note, imported_at"
)

_UPSERT_SQL = text(
    "INSERT INTO peer_shared_transactions ("
    "  txn_id, owner_user_id, date, description, amount, who, "
    "  person_1_owes, person_2_owes, notes, reviewed, payer_user_id, "
    "  carried_from_period, settles_in_period"
    ") VALUES ("
    "  :txn_id, CAST(:owner_user_id AS UUID), CAST(:date AS DATE), :description, "
    "  :amount, :who, :person_1_owes, :person_2_owes, :notes, :reviewed, "
    "  CAST(:payer_user_id AS UUID), :carried_from_period, :settles_in_period"
    ") ON CONFLICT (txn_id) DO UPDATE SET "
    "  owner_user_id = EXCLUDED.owner_user_id, "
    "  date = EXCLUDED.date, "
    "  description = EXCLUDED.description, "
    "  amount = EXCLUDED.amount, "
    "  who = EXCLUDED.who, "
    "  person_1_owes = EXCLUDED.person_1_owes, "
    "  person_2_owes = EXCLUDED.person_2_owes, "
    "  notes = EXCLUDED.notes, "
    "  reviewed = EXCLUDED.reviewed, "
    "  payer_user_id = EXCLUDED.payer_user_id, "
    "  carried_from_period = EXCLUDED.carried_from_period, "
    "  settles_in_period = EXCLUDED.settles_in_period, "
    "  imported_at = NOW()"
)

_UPSERT_PARAMS = (
    "txn_id", "owner_user_id", "date", "description", "amount", "who",
    "person_1_owes", "person_2_owes", "notes", "reviewed", "payer_user_id",
    "carried_from_period", "settles_in_period",
)


def _to_dict(row) -> Dict[str, Any]:
    return {
        "txn_id": row[0],
        "owner_user_id": str(row[1]),
        "date": row[2].isoformat() if row[2] else None,
        "description": row[3],
        "amount": float(row[4]),
        "who": row[5],
        "person_1_owes": float(row[6]),
        "person_2_owes": float(row[7]),
        "notes": row[8],
        "reviewed": bool(row[9]),
        "payer_user_id": str(row[10]) if row[10] else None,
        "carried_from_period": row[11],
        "settles_in_period": row[12],
        "dispute_flag": row[13],
        "dispute_by": row[14],
        "dispute_note": row[15],
        "imported_at": row[16].isoformat() if row[16] else None,
    }


def upsert_many(rows: List[Dict[str, Any]]) -> int:
    """Insert or update the given rows. Returns the number processed.

    Rows are projected to the statement's bind parameters so callers may pass
    richer dicts; the dispute columns are excluded on purpose, since they are
    ours to write and re-importing the peer's row must not erase them.
    """
    if not rows:
        return 0
    params = [{k: r.get(k) for k in _UPSERT_PARAMS} for r in rows]
    with sync_engine.begin() as conn:
        conn.execute(_UPSERT_SQL, params)
    return len(rows)


def get(txn_id: str) -> Optional[Dict[str, Any]]:
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {_COLS} FROM peer_shared_transactions WHERE txn_id = :id"),
            {"id": txn_id},
        ).fetchone()
    return _to_dict(row) if row else None


def list_for_period(period: str) -> List[Dict[str, Any]]:
    """Rows settling in ``period`` (YYYY-MM).

    ``settles_in_period`` wins when set — that is how a transaction dated in a
    closed month settles in the current open one. Otherwise the row settles in
    the month of its own date.
    """
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT {_COLS} FROM peer_shared_transactions "
                "WHERE COALESCE(settles_in_period, TO_CHAR(date, 'YYYY-MM')) = :p "
                "ORDER BY date ASC, txn_id ASC"
            ),
            {"p": period},
        ).fetchall()
    return [_to_dict(r) for r in rows]


def set_dispute(
    txn_id: str, flag: Optional[str], by: Optional[str], note: Optional[str]
) -> bool:
    with sync_engine.begin() as conn:
        result = conn.execute(
            text(
                "UPDATE peer_shared_transactions SET "
                "  dispute_flag = :flag, dispute_by = :by, dispute_note = :note "
                "WHERE txn_id = :id"
            ),
            {"id": txn_id, "flag": flag, "by": by, "note": note},
        )
    return result.rowcount > 0
