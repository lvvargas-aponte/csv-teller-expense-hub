"""User-profile router — household preferences for the advisor.

Single-row table keyed on ``id='household'``. The advisor reads these
through ``analytics.build_financial_snapshot`` so every chat turn sees
the user's risk tolerance, time horizon, dependents, and debt strategy.

GET returns an empty (all-None) shape when the profile hasn't been set
yet so the frontend always has stable keys to render against.
"""
from typing import Optional

from fastapi import APIRouter

from db import profile_repo
from models import UserProfileIn, UserProfileOut

router = APIRouter()


def _load_profile() -> Optional[UserProfileOut]:
    row = profile_repo.load()
    if not row:
        return None
    return UserProfileOut(
        risk_tolerance=row["risk_tolerance"],
        time_horizon_years=row["time_horizon_years"],
        dependents=row["dependents"],
        debt_strategy=row["debt_strategy"],
        monthly_income=row["monthly_income"],
        emergency_fund_months=row["emergency_fund_months"],
        birth_year=row["birth_year"],
        target_retirement_age=row["target_retirement_age"],
        annual_retirement_spend=row["annual_retirement_spend"],
        expected_return_pct=row["expected_return_pct"],
        notes=row["notes"] or "",
        updated_at=row["updated_at"],
    )


@router.get("/profile", response_model=UserProfileOut)
async def get_profile() -> UserProfileOut:
    """Return the household profile, or an empty shell if unset."""
    return _load_profile() or UserProfileOut()


@router.put("/profile", response_model=UserProfileOut)
async def upsert_profile(req: UserProfileIn) -> UserProfileOut:
    """Merge the fields present in ``req`` into the stored profile.

    Presence, not nullness, decides what changes: a key the client omits
    keeps its stored value, and a key sent as ``null`` clears the column.
    That distinction is what lets the settings page's "Not set" option
    actually unset a field — under the older exclude-none rule, choosing
    it silently left the previous answer in place.
    """
    payload = req.model_dump(exclude_unset=True)
    # notes is NOT NULL; "cleared" means the empty string, not NULL.
    if "notes" in payload and payload["notes"] is None:
        payload["notes"] = ""

    profile_repo.upsert(payload)

    # Return the fresh row so the client doesn't have to GET right after.
    return _load_profile() or UserProfileOut()
