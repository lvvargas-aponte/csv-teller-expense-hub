"""Credit utilization endpoint — per-card balance vs. credit_limit.

Thin serializer over :func:`credit_health_service.build`, which the health
score reads as well.
"""
from typing import Any, Dict

from fastapi import APIRouter

import credit_health_service

router = APIRouter()


@router.get("/accounts/credit-health")
async def credit_health() -> Dict[str, Any]:
    return credit_health_service.build()
