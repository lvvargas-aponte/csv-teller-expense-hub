"""Retirement projection — a thin read over ``retirement.project()``.

No response model: the payload is an assumptions-carrying estimate whose
shape the service owns, and pinning it twice would only let the two drift.
"""
from typing import Any, Dict

from fastapi import APIRouter

import retirement

router = APIRouter()


@router.get("/retirement/projection")
async def get_projection() -> Dict[str, Any]:
    """The three-scenario band, or ``available: false`` naming what's missing."""
    return await retirement.project()
