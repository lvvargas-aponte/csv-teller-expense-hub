"""Property routes — CRUD, valuations, per-property economics, portfolio.

Thin HTTP layer. All arithmetic lives in ``properties.py``; the repo lives
in ``db/properties_repo.py``.
"""
from datetime import date
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

import properties as properties_domain
from db import properties_repo
from models import PropertyIn, ValuationIn

router = APIRouter()


def _validate(req: PropertyIn) -> None:
    if not req.name.strip():
        raise HTTPException(status_code=422, detail="Property name must not be empty")
    if req.units < 1:
        raise HTTPException(status_code=422, detail="units must be >= 1")
    for field in (
        "purchase_price", "closing_costs", "capital_improvements",
        "monthly_rent", "other_monthly_income", "property_tax_annual",
        "insurance_annual", "hoa_monthly", "utilities_monthly",
        "other_monthly_expense",
    ):
        value = getattr(req, field)
        if value is not None and value < 0:
            raise HTTPException(status_code=422, detail=f"{field} must be >= 0")
    for field in (
        "vacancy_rate_pct", "mgmt_fee_pct", "maintenance_pct_of_rent",
        "capex_reserve_pct_of_rent",
    ):
        value = getattr(req, field)
        if value is not None and not (0 <= value <= 100):
            raise HTTPException(
                status_code=422, detail=f"{field} must be between 0 and 100"
            )


def _payload(req: PropertyIn) -> Dict[str, Any]:
    return req.model_dump()


@router.get("/properties")
async def list_properties() -> List[Dict[str, Any]]:
    """Every property, each with economics attached.

    Economics are computed rather than stored so a rent change or a new
    valuation is reflected immediately.
    """
    repo = properties_repo.get_repo()
    return [
        properties_domain.compute_property_economics(p["id"]) or p
        for p in repo.list_properties()
    ]


@router.get("/properties/portfolio")
async def get_portfolio() -> Dict[str, Any]:
    """Portfolio totals: value, debt, equity, NOI, cash flow, underperformers.

    Declared before ``/properties/{property_id}`` so "portfolio" isn't
    captured as a property id.
    """
    return properties_domain.compute_portfolio()


@router.get("/properties/suggest-transactions")
async def suggest_transactions(limit: int = 200) -> List[Dict[str, Any]]:
    """Untagged transactions that look like they belong to a property.

    Suggestions only — the caller confirms before anything is written. A
    mis-attributed rent payment distorts NOI, cash flow and the retirement
    projection downstream, so this never auto-applies.

    Declared above ``/properties/{property_id}`` so the literal path isn't
    captured as an id.
    """
    return properties_domain.suggest_property_for_transactions(limit=limit)


@router.get("/properties/{property_id}")
async def get_property(property_id: str) -> Dict[str, Any]:
    economics = properties_domain.compute_property_economics(property_id)
    if economics is None:
        raise HTTPException(status_code=404, detail="Property not found")
    return economics


@router.post("/properties", status_code=201)
async def create_property(req: PropertyIn) -> Dict[str, Any]:
    _validate(req)
    repo = properties_repo.get_repo()

    property_id = properties_domain.new_property_id()
    payload = _payload(req)
    payload["id"] = property_id
    repo.upsert_property(payload)

    # A purchase price is itself a valuation — seed the timeseries so equity
    # works immediately rather than waiting for a manual entry.
    if req.purchase_price and req.purchase_date:
        try:
            repo.add_valuation(
                property_id=property_id,
                as_of=date.fromisoformat(req.purchase_date),
                value=req.purchase_price,
                source="purchase",
                notes="Seeded from purchase price",
            )
        except ValueError:
            raise HTTPException(
                status_code=422, detail="purchase_date must be ISO YYYY-MM-DD"
            )

    return properties_domain.compute_property_economics(property_id)


@router.put("/properties/{property_id}")
async def update_property(property_id: str, req: PropertyIn) -> Dict[str, Any]:
    repo = properties_repo.get_repo()
    if repo.get_property(property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found")
    _validate(req)

    payload = _payload(req)
    payload["id"] = property_id
    repo.upsert_property(payload)
    return properties_domain.compute_property_economics(property_id)


@router.delete("/properties/{property_id}", status_code=204)
async def delete_property(property_id: str) -> None:
    """Remove a property.

    Valuations and rental terms cascade. Loans survive with ``property_id``
    cleared — selling the house must not delete the mortgage record.
    """
    if properties_repo.get_repo().delete_property(property_id) == 0:
        raise HTTPException(status_code=404, detail="Property not found")


@router.get("/properties/{property_id}/valuations")
async def list_valuations(property_id: str) -> List[Dict[str, Any]]:
    repo = properties_repo.get_repo()
    if repo.get_property(property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found")
    return repo.list_valuations(property_id)


@router.post("/properties/{property_id}/valuations", status_code=201)
async def add_valuation(property_id: str, req: ValuationIn) -> Dict[str, Any]:
    """Record a value. Only moves ``current_value`` when it is the newest on
    file, so backfilling an old appraisal can't clobber a current number."""
    repo = properties_repo.get_repo()
    if repo.get_property(property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found")
    if req.value <= 0:
        raise HTTPException(status_code=422, detail="value must be > 0")

    try:
        as_of = date.fromisoformat(req.as_of) if req.as_of else date.today()
    except ValueError:
        raise HTTPException(status_code=422, detail="as_of must be ISO YYYY-MM-DD")

    repo.add_valuation(
        property_id=property_id, as_of=as_of, value=req.value,
        source=req.source, notes=req.notes,
    )
    return properties_domain.compute_property_economics(property_id)
