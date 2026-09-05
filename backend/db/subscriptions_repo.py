"""Repository for ``subscription_reviews`` — keep/cancel/ignore decisions.

Mirrors the sync-engine pattern used by ``user_facts_repo``: each function
is a single SQL round-trip, no business logic (the subscriptions router
composes calls with ``analytics.detect_recurring_charges``).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import text

from db.base import sync_engine


VALID_DECISIONS = ("keep", "cancel", "ignore")

# Mirrors the CHECK constraints in migration 0029. A declared value overrides
# what the detector inferred; NULL means "no opinion, keep inferring".
VALID_CADENCES = (
    "weekly", "biweekly", "monthly", "bimonthly",
    "quarterly", "semiannual", "annual",
)
VALID_TYPES = ("bill", "subscription", "recurring_spend")

_SELECT_COLS = (
    "merchant_key, decision, reviewed_amount, reviewed_at, "
    "declared_cadence, declared_type"
)


def _row_to_dict(row) -> Dict[str, Any]:
    return {
        "merchant_key": row[0],
        "decision": row[1],
        "reviewed_amount": float(row[2]) if row[2] is not None else None,
        "reviewed_at": row[3].isoformat() if row[3] else None,
        "declared_cadence": row[4],
        "declared_type": row[5],
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
    declared_cadence: Optional[str] = None,
    declared_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Record a decision, plus optionally the user's answer to how often the
    merchant bills and what kind of commitment it is.

    A declared value of ``None`` leaves whatever is stored untouched — someone
    answering "cancel" must not silently wipe a cadence they set earlier — so
    those two columns COALESCE instead of taking EXCLUDED outright.
    """
    if decision not in VALID_DECISIONS:
        raise ValueError(f"decision must be one of {VALID_DECISIONS}")
    if declared_cadence is not None and declared_cadence not in VALID_CADENCES:
        raise ValueError(f"declared_cadence must be one of {VALID_CADENCES}")
    if declared_type is not None and declared_type not in VALID_TYPES:
        raise ValueError(f"declared_type must be one of {VALID_TYPES}")
    with sync_engine.begin() as conn:
        row = conn.execute(
            text(
                "INSERT INTO subscription_reviews "
                "  (merchant_key, decision, reviewed_amount, reviewed_at, "
                "   declared_cadence, declared_type) "
                "VALUES (:key, :decision, :amount, NOW(), :cadence, :ctype) "
                "ON CONFLICT (merchant_key) DO UPDATE SET "
                "  decision = EXCLUDED.decision, "
                "  reviewed_amount = EXCLUDED.reviewed_amount, "
                "  reviewed_at = NOW(), "
                "  declared_cadence = COALESCE("
                "    EXCLUDED.declared_cadence, subscription_reviews.declared_cadence), "
                "  declared_type = COALESCE("
                "    EXCLUDED.declared_type, subscription_reviews.declared_type) "
                f"RETURNING {_SELECT_COLS}"
            ),
            {
                "key": merchant_key, "decision": decision, "amount": reviewed_amount,
                "cadence": declared_cadence, "ctype": declared_type,
            },
        ).fetchone()
    return _row_to_dict(row)


def delete_review(merchant_key: str) -> bool:
    with sync_engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM subscription_reviews WHERE merchant_key = :key"),
            {"key": merchant_key},
        )
    return result.rowcount > 0