"""Retirement routes — assumptions and the projection.

Thin HTTP layer. The math lives in ``backend/retirement.py`` and is pure;
this reads the stores and serializes.
"""
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

import retirement as retirement_domain
import state
from models import RetirementAssumptionsIn

router = APIRouter()


def _stored() -> Dict[str, Any]:
    return dict(state.retirement_assumptions.get("household") or {})


@router.get("/retirement/assumptions")
async def get_assumptions() -> Dict[str, Any]:
    """Saved assumptions merged over the defaults, so the UI always has a
    complete set to render even before anything has been configured."""
    return {
        "assumptions": {**retirement_domain.DEFAULT_ASSUMPTIONS, **_stored()},
        "defaults": retirement_domain.DEFAULT_ASSUMPTIONS,
        "configured": bool(_stored()),
    }


@router.put("/retirement/assumptions")
async def put_assumptions(req: RetirementAssumptionsIn) -> Dict[str, Any]:
    """Save assumptions. Only fields actually supplied are stored, so an
    unset value keeps falling back to the default rather than freezing
    today's default into the record."""
    supplied = {k: v for k, v in req.model_dump().items() if v is not None}
    merged = {**_stored(), **supplied}
    merged["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    state.retirement_assumptions["household"] = merged
    return {
        "assumptions": {**retirement_domain.DEFAULT_ASSUMPTIONS, **merged},
        "defaults": retirement_domain.DEFAULT_ASSUMPTIONS,
        "configured": True,
    }


@router.get("/retirement/projection")
async def projection(
    as_of: Optional[str] = Query(None, description="ISO date; defaults to today"),
    include_sensitivity: bool = Query(True),
) -> Dict[str, Any]:
    """Year-by-year projection and the earliest sustainable retirement year.

    ``earliest_retirement_year`` is the first year feasibility holds *and
    keeps holding* — a crossing that later reverses is not a retirement
    date.
    """
    parsed: Optional[date] = None
    if as_of:
        try:
            parsed = date.fromisoformat(as_of)
        except ValueError:
            raise HTTPException(status_code=422, detail="as_of must be ISO YYYY-MM-DD")

    inputs = retirement_domain.build_retirement_inputs(as_of=parsed)
    result = retirement_domain.project_retirement(inputs, as_of=parsed)
    result["inputs_summary"] = {
        "investment_balance": inputs.investment_balance,
        "property_count": len(inputs.properties),
        "annual_spending_now": inputs.annual_spending_now,
    }
    if include_sensitivity:
        result["sensitivity"] = retirement_domain.build_sensitivity(
            inputs, as_of=parsed
        )
    return result


@router.post("/retirement/projection")
async def what_if(req: RetirementAssumptionsIn) -> Dict[str, Any]:
    """Run a projection against supplied assumptions without saving them."""
    inputs = retirement_domain.build_retirement_inputs()
    overrides = {k: v for k, v in req.model_dump().items() if v is not None}
    inputs.assumptions = {**inputs.assumptions, **overrides}
    result = retirement_domain.project_retirement(inputs)
    result["sensitivity"] = retirement_domain.build_sensitivity(inputs)
    result["saved"] = False
    return result
