"""Retirement projection — a thin read over ``retirement.project()``.

No response model: the payload is an assumptions-carrying estimate whose
shape the service owns, and pinning it twice would only let the two drift.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query

import retirement

router = APIRouter()


@router.get("/retirement/projection")
async def get_projection(
    inflation_pct: Optional[float] = Query(None, ge=0, le=20),
    withdrawal_rate_pct: Optional[float] = Query(None, gt=0, le=20),
) -> Dict[str, Any]:
    """The three-scenario band, or ``available: false`` naming what's missing.

    The two overrides are what-ifs, not preferences: inflation and the
    withdrawal rate are house-wide constants with no per-household column, so
    a nudge on the card changes this view and nothing else.
    """
    return await retirement.project(
        inflation_pct=inflation_pct, withdrawal_rate_pct=withdrawal_rate_pct
    )
