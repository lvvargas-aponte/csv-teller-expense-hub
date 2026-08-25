"""Repository for ``user_profile`` — the household's single settings row.

One row, keyed ``household``. Two readers want it — the settings API and the
advisor's grounding snapshot — and both used to carry their own column list and
index the result positionally, in two different orders. The column list and the
row→dict mapping live here so adding a column is one edit, not three.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import text

from db.base import sync_engine

PROFILE_ID = "household"

COLUMNS = (
    "risk_tolerance",
    "time_horizon_years",
    "dependents",
    "debt_strategy",
    "monthly_income",
    "emergency_fund_months",
    "birth_year",
    "target_retirement_age",
    "annual_retirement_spend",
    "expected_return_pct",
    "notes",
    "updated_at",
)

_SELECT_SQL = text(
    f"SELECT {', '.join(COLUMNS)} FROM user_profile WHERE id = :id"
)


def _to_dict(row) -> Dict[str, Any]:
    """Map a row onto ``COLUMNS`` by name, with DB types coerced for JSON.

    The ``Numeric`` columns arrive as ``Decimal`` at runtime; both callers
    want floats.
    """
    out: Dict[str, Any] = dict(zip(COLUMNS, row))
    for key in ("monthly_income", "annual_retirement_spend", "expected_return_pct"):
        if out.get(key) is not None:
            out[key] = float(out[key])
    for key in (
        "time_horizon_years",
        "dependents",
        "emergency_fund_months",
        "birth_year",
        "target_retirement_age",
    ):
        if out.get(key) is not None:
            out[key] = int(out[key])
    updated = out.get("updated_at")
    out["updated_at"] = updated.isoformat() if hasattr(updated, "isoformat") else updated
    return out


def load() -> Optional[Dict[str, Any]]:
    """The household profile as a dict keyed by column name, or None if unset."""
    with sync_engine.connect() as conn:
        row = conn.execute(_SELECT_SQL, {"id": PROFILE_ID}).fetchone()
    return _to_dict(row) if row else None


def upsert(values: Dict[str, Any]) -> None:
    """Merge ``values`` into the profile row, touching only the keys given.

    Column names are interpolated into the statement, so they are whitelisted
    against ``COLUMNS`` first — the caller's key set must never be able to
    decide what SQL is built.
    """
    cols = [c for c in values if c in COLUMNS and c != "updated_at"]
    if not cols:
        return

    insert_cols = ["id"] + cols
    placeholders = [":id"] + [f":{c}" for c in cols]
    update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
    sql = text(
        f"INSERT INTO user_profile ({', '.join(insert_cols)}) "
        f"VALUES ({', '.join(placeholders)}) "
        f"ON CONFLICT (id) DO UPDATE SET {update_clause}, updated_at = NOW()"
    )

    with sync_engine.begin() as conn:
        conn.execute(sql, {"id": PROFILE_ID, **{c: values[c] for c in cols}})
