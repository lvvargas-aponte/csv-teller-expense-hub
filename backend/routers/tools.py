"""Tools routes: payoff plan calculator, allocation waterfall, AI advice.

Thin HTTP layer only — the simulation lives in ``amortization`` and the
waterfall in ``allocation``, so both can be unit-tested without a client
and reused outside a request.
"""
import logging
from datetime import date

from fastapi import APIRouter

import allocation
import amortization
from llm_client import ask_ollama
from models import AllocateRequest, AllocationSettingsIn, PayoffRequest, PayoffAdviceRequest
import state

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/tools/payoff-plan")
async def payoff_plan(req: PayoffRequest):
    """Compute a month-by-month debt payoff plan (avalanche or snowball)."""
    debts = [
        amortization.DebtInput(
            name=a.name,
            balance=a.balance,
            apr=a.apr,
            min_payment=a.min_payment,
            promo_apr=a.promo_apr,
            promo_expires=a.promo_expires,
        )
        for a in req.accounts
    ]
    return amortization.simulate_payoff_plan(
        debts,
        extra_monthly=req.extra_monthly,
        strategy=req.strategy,
        max_periods=state.PAYOFF_MAX_MONTHS,
    )


@router.post("/tools/allocate")
async def allocate_extra(req: AllocateRequest):
    """Split spare money across the tiers, in order, with both sides shown."""
    as_of = None
    if req.as_of:
        try:
            as_of = date.fromisoformat(req.as_of[:10])
        except ValueError:
            as_of = None
    return allocation.allocate_from_stores(
        req.amount, cadence=req.cadence, as_of=as_of,
    )


@router.get("/tools/allocation-settings")
async def get_allocation_settings():
    """Stored settings merged over the defaults, so the UI sees real values.

    ``employer_match_known`` is deliberately ``None`` until answered — that
    absence is what makes the waterfall ask instead of assuming.
    """
    stored = dict(state.allocation_settings.get("household") or {})
    return {**allocation.DEFAULT_SETTINGS, **stored}


@router.put("/tools/allocation-settings")
async def put_allocation_settings(payload: AllocationSettingsIn):
    """Merge-then-write, so a partial update can't null a sibling field."""
    stored = dict(state.allocation_settings.get("household") or {})
    stored.update(payload.model_dump(exclude_none=True))
    state.allocation_settings["household"] = stored
    return {**allocation.DEFAULT_SETTINGS, **stored}


@router.post("/tools/payoff-advice")
async def payoff_advice(req: PayoffAdviceRequest):
    """Call a local Ollama LLM to give personalised debt-payoff advice."""

    strategy_label = (
        "Avalanche (pay highest-APR debt first)"
        if req.strategy == "avalanche"
        else "Snowball (pay lowest-balance debt first)"
    )

    lines = [
        "You are a warm, knowledgeable personal financial advisor. "
        "A client has shared their debt situation and wants your advice.\n",
        "## Their debts",
    ]
    for acct in req.accounts:
        lines.append(
            f"- {acct.name}: ${acct.balance:,.2f} balance at {acct.apr:.2f}% APR, "
            f"minimum payment ${acct.min_payment:,.2f}/mo"
        )

    lines.append(f"\nStrategy chosen: {strategy_label}")
    if req.extra_monthly > 0:
        lines.append(f"Extra monthly payment toward debt: ${req.extra_monthly:,.2f}")

    if req.plan_results:
        lines.append("\n## Calculated payoff plan")
        for acct in req.plan_results.get("accounts", []):
            lines.append(
                f"- {acct['name']}: paid off in {acct.get('months', '?')} months "
                f"({acct.get('payoff_date', '?')}), total interest ${acct.get('total_interest', 0):,.2f}"
            )
        lines.append(
            f"Total interest across all debts: ${req.plan_results.get('grand_total_interest', 0):,.2f}"
        )
        saved = req.plan_results.get("interest_saved_vs_minimums")
        if saved is not None and saved > 0:
            lines.append(f"Interest saved vs. paying minimums only: ${saved:,.2f}")

    lines += [
        "\n## Your task",
        "Provide a brief, personalised response (4-6 sentences) that covers:",
        "1. A quick assessment of their debt situation",
        "2. Whether their chosen strategy makes sense for them and why",
        "3. One or two specific, actionable tips to pay off faster or save more interest",
        "\nBe direct, encouraging, and specific. Use dollar amounts from the data above.",
    ]
    prompt_text = "\n".join(lines)

    result = await ask_ollama(prompt_text)
    return {"ai_available": result["ai_available"], "advice": result["text"]}
