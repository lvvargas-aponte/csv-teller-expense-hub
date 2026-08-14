"""Repository for ``subscription_reviews`` — keep/cancel/ignore decisions.

Mirrors the sync-engine pattern used by ``user_facts_repo``: each function
is a single SQL round-trip, no business logic (the subscriptions router
composes calls with ``analytics.detect_recurring_charges``).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy import text

from db.base import sync_engine

logger = logging.getLogger(__name__)

VALID_DECISIONS = ("keep", "cancel", "ignore")

_SELECT_COLS = "merchant_key, decision, reviewed_amount, reviewed_at"


def _row_to_dict(row) -> Dict[str, Any]:
    return {
        "merchant_key": row[0],
        "decision": row[1],
        "reviewed_amount": float(row[2]) if row[2] is not None else None,
        "reviewed_at": row[3].isoformat() if row[3] else None,
    }


def list_reviews() -> Dict[str, Dict[str, Any]]:
    """All review rows keyed by merchant_key."""
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT {_SELECT_COLS} FROM subscription_reviews")
        ).fetchall()
    return {r[0]: _row_to_dict(r) for r in rows}


def upsert_review(
    merchant_key: str,
    decision: str,
    reviewed_amount: Optional[float] = None,
) -> Dict[str, Any]:
    if decision not in VALID_DECISIONS:
        raise ValueError(f"decision must be one of {VALID_DECISIONS}")
    with sync_engine.begin() as conn:
        row = conn.execute(
            text(
                "INSERT INTO subscription_reviews "
                "  (merchant_key, decision, reviewed_amount, reviewed_at) "
                "VALUES (:key, :decision, :amount, NOW()) "
                "ON CONFLICT (merchant_key) DO UPDATE SET "
                "  decision = EXCLUDED.decision, "
                "  reviewed_amount = EXCLUDED.reviewed_amount, "
                "  reviewed_at = NOW() "
                f"RETURNING {_SELECT_COLS}"
            ),
            {"key": merchant_key, "decision": decision, "amount": reviewed_amount},
        ).fetchone()
    return _row_to_dict(row)


def delete_review(merchant_key: str) -> bool:
    with sync_engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM subscription_reviews WHERE merchant_key = :key"),
            {"key": merchant_key},
        )
    return result.rowcount > 0