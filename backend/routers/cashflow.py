"""Cash-flow outlook — a thin read over ``analytics.project_cashflow``.

No response model: the payload is an estimate whose shape the service owns,
and the projection carries its own confidence, so pinning it twice would only
let the two drift.
"""
from typing import Any, Dict

from fastapi import APIRouter, Query

from analytics import project_cashflow

router = APIRouter()


@router.get("/cashflow/projection")
async def get_cashflow_projection(
    horizon_days: int = Query(30, ge=1, le=180),
) -> Dict[str, Any]:
    """Income in, bills out, typical spending out, projected net."""
    return project_cashflow(horizon_days=horizon_days)
