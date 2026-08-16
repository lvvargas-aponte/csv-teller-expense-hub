"""Equity routes — borrowing capacity and the deal analyzer.

Thin HTTP layer over ``properties.compute_usable_equity`` /
``compute_portfolio_equity`` / ``analyze_deal``.
"""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

import properties as properties_domain
from models import DealInputs

router = APIRouter()


@router.get("/equity/capacity")
async def capacity(
    max_ltv_pct: float = Query(75.0, ge=0, le=100),
    max_cltv_pct: float = Query(85.0, ge=0, le=100),
) -> Dict[str, Any]:
    """Borrowing capacity across every property.

    Each entry reports the payment increase and the cash flow that survives
    it alongside the extractable amount — the proceeds figure alone is the
    most misleading number in real estate.
    """
    return properties_domain.compute_portfolio_equity(
        max_ltv_pct=max_ltv_pct, max_cltv_pct=max_cltv_pct
    )


@router.get("/equity/capacity/{property_id}")
async def capacity_for(
    property_id: str,
    max_ltv_pct: float = Query(75.0, ge=0, le=100),
    max_cltv_pct: float = Query(85.0, ge=0, le=100),
) -> Dict[str, Any]:
    result = properties_domain.compute_usable_equity(
        property_id, max_ltv_pct=max_ltv_pct, max_cltv_pct=max_cltv_pct
    )
    if result.get("reason") == "not_found":
        raise HTTPException(status_code=404, detail="Property not found")
    return result


@router.post("/equity/analyze-deal")
async def analyze_deal(req: DealInputs) -> Dict[str, Any]:
    """Model a hypothetical purchase.

    Read ``net_effect.portfolio_cash_flow_delta`` before the deal's own cash
    flow: when the down payment is borrowed against a property you already
    own, a deal that looks positive standalone can still reduce total
    monthly income.
    """
    if req.purchase_price <= 0:
        raise HTTPException(status_code=422, detail="purchase_price must be > 0")
    if req.funded_from in ("heloc", "cash_out_refi") and not req.source_property_id:
        raise HTTPException(
            status_code=422,
            detail="source_property_id is required when funding from equity",
        )
    return properties_domain.analyze_deal(req.model_dump())
