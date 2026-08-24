"""Health-score endpoint — thin serializer over :mod:`health_service`."""
from typing import Any, Dict

from fastapi import APIRouter

import health_service

router = APIRouter()


@router.get("/health/score")
async def health_score() -> Dict[str, Any]:
    return await health_service.compute_health_score()


@router.get("/health/ratios")
async def health_ratios() -> Dict[str, Any]:
    return await health_service.compute_ratios()
