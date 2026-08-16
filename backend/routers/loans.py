"""Loan routes — CRUD, amortization schedule, current payment split, what-if.

``GET /loans/{id}/current-payment`` is the endpoint behind "how much of my
mortgage payment went to interest vs principal", which is the question that
prompted this whole feature.
"""
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

import amortization
import properties as properties_domain
from db import properties_repo
from models import LoanIn, LoanWhatIfRequest

router = APIRouter()


def _validate(req: LoanIn) -> None:
    if not req.name.strip():
        raise HTTPException(status_code=422, detail="Loan name must not be empty")
    if req.original_principal <= 0:
        raise HTTPException(status_code=422, detail="original_principal must be > 0")
    if req.interest_rate_pct < 0:
        raise HTTPException(status_code=422, detail="interest_rate_pct must be >= 0")
    if req.term_months <= 0:
        raise HTTPException(status_code=422, detail="term_months must be > 0")
    if req.lien_position < 1:
        raise HTTPException(status_code=422, detail="lien_position must be >= 1")
    for field in ("escrow_monthly", "pmi_monthly", "extra_monthly"):
        if getattr(req, field) < 0:
            raise HTTPException(status_code=422, detail=f"{field} must be >= 0")
    for field in ("origination_date", "first_payment_date", "balloon_date"):
        value = getattr(req, field)
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                raise HTTPException(
                    status_code=422, detail=f"{field} must be ISO YYYY-MM-DD"
                )
    if req.property_id:
        if properties_repo.get_repo().get_property(req.property_id) is None:
            raise HTTPException(status_code=422, detail="property_id does not exist")


def _enrich(loan: Dict[str, Any]) -> Dict[str, Any]:
    """Attach the derived figures every loan view needs."""
    enriched = dict(loan)
    enriched["monthly_payment"] = properties_domain.loan_payment(loan)
    enriched["current_balance_resolved"] = properties_domain.resolve_loan_balance(loan)
    enriched["asset_value_resolved"] = properties_domain.resolve_asset_value(loan)

    asset_value = enriched["asset_value_resolved"]
    balance = enriched["current_balance_resolved"]
    if asset_value and balance is not None:
        enriched["equity"] = round(asset_value - balance, 2)
        enriched["ltv"] = round(balance / asset_value * 100.0, 2)
    else:
        enriched["equity"] = None
        enriched["ltv"] = None
    return enriched


def _rate_schedule(loan: Dict[str, Any]) -> Optional[List]:
    """Interest-only window expressed as a rate schedule.

    Kept as a hook: ARM steps and promo windows plug in here without the
    schedule builder needing to know what a loan is.
    """
    return None


@router.get("/loans")
async def list_loans(property_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """All loans, or just those secured by one property."""
    return [
        _enrich(loan)
        for loan in properties_repo.get_repo().list_loans(property_id)
    ]


@router.get("/loans/{loan_id}")
async def get_loan(loan_id: str) -> Dict[str, Any]:
    loan = properties_repo.get_repo().get_loan(loan_id)
    if loan is None:
        raise HTTPException(status_code=404, detail="Loan not found")
    return _enrich(loan)


@router.post("/loans", status_code=201)
async def create_loan(req: LoanIn) -> Dict[str, Any]:
    _validate(req)
    payload = req.model_dump()
    payload["id"] = properties_domain.new_loan_id()
    return _enrich(properties_repo.get_repo().upsert_loan(payload))


@router.put("/loans/{loan_id}")
async def update_loan(loan_id: str, req: LoanIn) -> Dict[str, Any]:
    repo = properties_repo.get_repo()
    if repo.get_loan(loan_id) is None:
        raise HTTPException(status_code=404, detail="Loan not found")
    _validate(req)
    payload = req.model_dump()
    payload["id"] = loan_id
    return _enrich(repo.upsert_loan(payload))


@router.delete("/loans/{loan_id}", status_code=204)
async def delete_loan(loan_id: str) -> None:
    if properties_repo.get_repo().delete_loan(loan_id) == 0:
        raise HTTPException(status_code=404, detail="Loan not found")


@router.get("/loans/{loan_id}/current-payment")
async def current_payment(loan_id: str) -> Dict[str, Any]:
    """How this month's payment splits between interest and principal.

    Also returns cumulative principal paid — on a rental, the "tenants have
    bought me this much of the house so far" number.
    """
    loan = properties_repo.get_repo().get_loan(loan_id)
    if loan is None:
        raise HTTPException(status_code=404, detail="Loan not found")

    split = properties_domain.loan_current_split(loan)
    split["loan_id"] = loan_id
    split["name"] = loan.get("name")
    return split


@router.get("/loans/{loan_id}/schedule")
async def get_schedule(
    loan_id: str,
    from_period: int = Query(1, ge=1, description="1-based, inclusive"),
    limit: int = Query(60, ge=1, le=600),
) -> Dict[str, Any]:
    """Amortization schedule, paginated.

    Defaults to the first 60 payments — a 360-row table is unreadable and
    the caller can page. Totals always describe the whole loan, not the
    returned slice.
    """
    loan = properties_repo.get_repo().get_loan(loan_id)
    if loan is None:
        raise HTTPException(status_code=404, detail="Loan not found")

    origination = loan.get("first_payment_date") or loan.get("origination_date")
    try:
        start = date.fromisoformat(str(origination)[:10])
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Loan has no usable start date")

    result = amortization.build_schedule(
        principal=loan.get("original_principal") or 0,
        annual_rate_pct=loan.get("interest_rate_pct") or 0,
        term_months=int(loan.get("term_months") or 0),
        start_date=start,
        payment=loan.get("payment_amount"),
        extra_monthly=loan.get("extra_monthly") or 0,
        escrow_monthly=loan.get("escrow_monthly") or 0,
        interest_only_months=int(loan.get("io_months") or 0),
        rate_schedule=_rate_schedule(loan),
    )

    window = result.periods[from_period - 1: from_period - 1 + limit]
    return {
        "loan_id": loan_id,
        "name": loan.get("name"),
        "monthly_payment": result.monthly_payment,
        "escrow_monthly": float(loan.get("escrow_monthly") or 0),
        "total_interest": result.total_interest,
        "total_paid": result.total_paid,
        "payoff_date": result.payoff_date.isoformat() if result.payoff_date else None,
        "payoff_months": result.payoff_months,
        "truncated": result.truncated,
        "negative_amortization": result.negative_amortization,
        "from_period": from_period,
        "limit": limit,
        "total_periods": len(result.periods),
        "periods": [
            {
                "period": p.period,
                "date": p.date.isoformat(),
                "payment": p.payment,
                "principal": p.principal,
                "interest": p.interest,
                "extra": p.extra,
                "escrow": p.escrow,
                "balance": p.balance,
                "cumulative_interest": p.cumulative_interest,
                "cumulative_principal": p.cumulative_principal,
            }
            for p in window
        ],
    }


@router.post("/loans/{loan_id}/what-if")
async def what_if(loan_id: str, req: LoanWhatIfRequest) -> Dict[str, Any]:
    """Months and interest saved by paying extra each month."""
    loan = properties_repo.get_repo().get_loan(loan_id)
    if loan is None:
        raise HTTPException(status_code=404, detail="Loan not found")
    if req.extra_monthly < 0:
        raise HTTPException(status_code=422, detail="extra_monthly must be >= 0")

    origination = loan.get("first_payment_date") or loan.get("origination_date")
    try:
        start = date.fromisoformat(str(origination)[:10])
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Loan has no usable start date")

    comparison = amortization.compare_extra_payment(
        principal=loan.get("original_principal") or 0,
        annual_rate_pct=loan.get("interest_rate_pct") or 0,
        term_months=int(loan.get("term_months") or 0),
        start_date=start,
        payment=loan.get("payment_amount"),
        extra_monthly=req.extra_monthly,
        escrow_monthly=loan.get("escrow_monthly") or 0,
    )
    comparison["loan_id"] = loan_id
    comparison["name"] = loan.get("name")
    return comparison
