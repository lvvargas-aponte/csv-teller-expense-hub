"""Credit utilization endpoint — per-card balance vs. credit_limit.

Thin serializer over :func:`credit_health_service.build`, which the health
score reads as well.
"""
from typing import Any, Dict

from fastapi import APIRouter

import analytics
import credit_health_service
import health_service

router = APIRouter()


@router.get("/accounts/credit-health")
async def credit_health() -> Dict[str, Any]:
    composition = await credit_health_service.build()
    # What the balances cost per month rides along: the card that shows
    # utilization is where "and it costs you $214/month" belongs.
    composition["carry_cost"] = await analytics.compute_carry_cost()
    return composition


@router.get("/accounts/borrowing-power")
async def borrowing_power() -> Dict[str, Any]:
    """What a lender reads, as opposed to what a score reports.

    Replaces the credit-factors panel, which framed the page around FICO's
    five factors and could honestly measure one of them: payment history
    needs delinquencies no bank feed carries, length of history and new credit
    need an open date on every account, and credit mix is a count nobody can
    act on. Four of five rendered as placeholders.

    Debt-to-income is the trade. It is not a score factor at all — no bureau
    holds an income figure — but it is what actually gates a mortgage, and it
    is computable here precisely because this app has the bank feed a credit
    monitor does not.
    """
    ratios = await health_service.compute_ratios()
    carry = await analytics.compute_carry_cost()

    return {
        "dti": {
            "pct": ratios.get("dti_pct"),
            "monthly_debt_payments": ratios.get("monthly_debt_payments"),
            "monthly_income": (ratios.get("income") or {}).get("monthly"),
            "income_source": (ratios.get("income") or {}).get("source"),
            "income_confidence": (ratios.get("income") or {}).get("confidence"),
            "comfortable_pct": health_service.DTI_COMFORTABLE_PCT,
            "ceiling_pct": health_service.DTI_CEILING_PCT,
            # Each debt's contribution and whether it was read off a statement
            # or estimated from the balance and APR.
            "payments": ratios.get("debt_payments") or [],
            # Non-empty means the ratio is missing a payment and must not be
            # shown as a figure — see health_service._debts_missing_a_payment.
            "debts_missing_payment": ratios.get("debts_missing_payment") or [],
        },
        "interest_history": analytics.compute_interest_history(),
        "carry_cost": {
            "monthly_interest": (carry or {}).get("monthly_interest"),
            "accounts_missing_apr": (carry or {}).get("accounts_missing_apr"),
        },
    }
