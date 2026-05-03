"""User-profile router — household preferences for the advisor.

Single-row table keyed on ``id='household'``. The advisor reads these
through ``analytics.build_financial_snapshot`` so every chat turn sees
the user's risk tolerance, time horizon, dependents, and debt strategy.

GET returns an empty (all-None) shape when the profile hasn't been set
yet so the frontend always has stable keys to render against.
"""
from typing import Optional

from fastapi import APIRouter
from sqlalchemy import text

from db.base import sync_engine
from models import UserProfileIn, UserProfileOut

router = APIRouter()

_PROFILE_ID = "household"


def _row_to_profile(row) -> UserProfileOut:
    return UserProfileOut(
        risk_tolerance=row[0],
        time_horizon_years=row[1],
        dependents=row[2],
        debt_strategy=row[3],
        notes=row[4] or "",
        updated_at=row[5].isoformat() if row[5] else None,
    )


def _load_profile() -> Optional[UserProfileOut]:
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT risk_tolerance, time_horizon_years, dependents, "
                "       debt_strategy, notes, updated_at "
                "FROM user_profile WHERE id = :id"
            ),
            {"id": _PROFILE_ID},
        ).fetchone()
    return _row_to_profile(row) if row else None


@router.get("/profile", response_model=UserProfileOut)
async def get_profile() -> UserProfileOut:
    """Return the household profile, or an empty shell if unset."""
    return _load_profile() or UserProfileOut()


@router.put("/profile", response_model=UserProfileOut)
async def upsert_profile(req: UserProfileIn) -> UserProfileOut:
    """Merge non-null fields from ``req`` into the stored profile.

    Partial updates: omitted fields keep their existing values. Set a
    field to ``""`` (notes) or pass an explicit value to overwrite. To
    *clear* a field, pass an empty string for notes; the typed enums and
    integers don't currently support clearing — re-PUT with the desired
    value or DELETE if we ever add it.
    """
    payload = req.model_dump(exclude_none=True)
    if not payload:
        # Nothing to update; return current (or empty) profile.
        return _load_profile() or UserProfileOut()

    # Build the SET clause dynamically so unspecified columns retain
    # their existing values via COALESCE on the conflict-update path.
    cols = list(payload.keys())
    insert_cols = ["id"] + cols
    insert_placeholders = [":id"] + [f":{c}" for c in cols]
    update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
    sql = (
        f"INSERT INTO user_profile ({', '.join(insert_cols)}) "
        f"VALUES ({', '.join(insert_placeholders)}) "
        f"ON CONFLICT (id) DO UPDATE SET {update_clause}, updated_at = NOW()"
    )

    params = {"id": _PROFILE_ID, **payload}
    with sync_engine.begin() as conn:
        conn.execute(text(sql), params)

    # Return the fresh row so the client doesn't have to GET right after.
    return _load_profile() or UserProfileOut()
