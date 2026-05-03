"""Tools routes: payoff plan calculator and AI advice."""
import logging
from datetime import date

from fastapi import APIRouter

from llm_client import ask_ollama
from models import PayoffAccount, PayoffRequest, PayoffAdviceRequest
import state

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/tools/payoff-plan")
async def payoff_plan(req: PayoffRequest):
    """Compute a month-by-month debt payoff plan using avalanche or snowball strategy."""
    max_months = state.PAYOFF_MAX_MONTHS

    def _simulate(
        accounts_input: list[PayoffAccount], extra: float, strategy: str
    ) -> tuple[list[dict], int]:
        """Run the payoff simulation; return per-account results and total months."""
        if strategy == "avalanche":
            ordered = sorted(accounts_input, key=lambda a: a.apr, reverse=True)
        else:
            ordered = sorted(accounts_input, key=lambda a: a.balance)

        balances = [a.balance for a in ordered]
        interest_paid = [0.0] * len(ordered)
        payoff_months = [0] * len(ordered)
        month = 0

        while any(b > 0 for b in balances) and month < max_months:
            month += 1
            # Apply interest and minimum payments
            for i, acct in enumerate(ordered):
                if balances[i] <= 0:
                    continue
                monthly_rate = acct.apr / 100.0 / 12.0
                interest = balances[i] * monthly_rate
                interest_paid[i] += interest
                balances[i] += interest
                balances[i] = max(0.0, balances[i] - acct.min_payment)
                if balances[i] <= 0:
                    payoff_months[i] = payoff_months[i] or month

            # Apply extra to priority account (first non-zero balance)
            remaining_extra = extra
            for i in range(len(ordered)):
                if balances[i] > 0 and remaining_extra > 0:
                    applied = min(remaining_extra, balances[i])
                    balances[i] -= applied
                    remaining_extra -= applied
                    if balances[i] <= 0:
                        payoff_months[i] = payoff_months[i] or month
                    break

        # Catch any that never reached 0 (hit cap)
        for i in range(len(ordered)):
            if payoff_months[i] == 0 and balances[i] > 0:
                payoff_months[i] = max_months

        results = []
        today = date.today()
        for i, acct in enumerate(ordered):
            pm = payoff_months[i]
            payoff_date_obj = date(
                today.year + (today.month - 1 + pm) // 12,
                (today.month - 1 + pm) % 12 + 1,
                1,
            )
            results.append({
                "name": acct.name,
                "payoff_months": pm,
                "total_interest": round(interest_paid[i], 2),
                "payoff_date": payoff_date_obj.strftime("%Y-%m"),
            })
        total_months = max(payoff_months) if payoff_months else 0
        return results, total_months

    with_extra, grand_months = _simulate(req.accounts, req.extra_monthly, req.strategy)
    baseline, _ = _simulate(req.accounts, 0.0, req.strategy)

    grand_total_interest = round(sum(a["total_interest"] for a in with_extra), 2)
    baseline_total = round(sum(a["total_interest"] for a in baseline), 2)
    interest_saved = round(baseline_total - grand_total_interest, 2)

    return {
        "accounts": with_extra,
        "grand_total_interest": grand_total_interest,
        "grand_total_months": grand_months,
        "interest_saved_vs_minimums": interest_saved,
        "strategy": req.strategy,
    }


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
