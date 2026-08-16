"""The proactive coach — ranked, dated, dollar-quantified next actions.

``/api/alerts`` answers "what's wrong?". This answers "what should I do
about it?", which is a different and more useful question: every action
carries an amount, a deadline where one exists, and what it protects.

**Every decision here is rule-based.** The amounts, the impact figures and
the reasons are all deterministic and are what the UI renders. An optional
LLM layer rewrites the top few into a sentence of narration, but it never
originates a number, never reorders anything, and never decides whether to
act — and any narration containing a figure that isn't in the payload is
discarded outright. A fabricated dollar amount that the user then acts on
is the worst thing this module could do.

Rules live in one function each so a misfiring rule can be found and
silenced without unpicking the ranking.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional

import state

# Urgency drives the primary sort. "now" means today's behaviour changes.
URGENCY_ORDER = {"now": 0, "this_week": 1, "this_month": 2, "fyi": 3}

# Tie-break when urgency and dollar impact match. Roughly: stop bleeding,
# then protect commitments, then grow.
KIND_PRIORITY = {
    "spend_less": 0,
    "pay_bill": 1,
    "emergency_fund": 2,
    "fund_goal": 3,
    "pay_extra": 4,
    "review_property": 5,
    "route_surplus": 6,
    "tap_equity": 7,
}

# A coach that emits thirty items is a to-do list nobody reads.
DEFAULT_LIMIT = 6

# Below this, an action costs more attention than it returns.
_MIN_IMPACT_DOLLARS = 25.0


def _action(
    *,
    id: str,
    kind: str,
    urgency: str,
    title: str,
    detail: str,
    amount: Optional[float] = None,
    impact: Optional[Dict[str, Any]] = None,
    due_date: Optional[str] = None,
    cta: Optional[Dict[str, str]] = None,
    why: Optional[List[str]] = None,
    source: str = "",
) -> Dict[str, Any]:
    return {
        "id": id,
        "kind": kind,
        "urgency": urgency,
        "title": title,
        "detail": detail,
        "amount": round(amount, 2) if amount is not None else None,
        "impact": impact,
        "due_date": due_date,
        "cta": cta,
        "why": why or [],
        "source": source,
        "dismissible": True,
    }


def _period_key(today: date) -> str:
    """Actions are scoped to a period so a dismissal expires with it.

    ``over_budget:Dining:2026-08`` dismissed in August correctly returns in
    September rather than being silenced forever.
    """
    return f"{today.year:04d}-{today.month:02d}"


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def rule_daily_allowance(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Today's spending instruction, straight from safe-to-spend."""
    sts = ctx.get("safe_to_spend") or {}
    if not sts.get("available"):
        return []

    period = _period_key(ctx["today"])
    if sts.get("over_budget"):
        return [_action(
            id=f"daily_allowance:over:{period}",
            kind="spend_less",
            urgency="now",
            title="Hold off on spending today",
            detail=(
                f"You're ${sts['overspend_amount']:,.0f} past this month's plan. "
                f"Spending nothing more keeps your bills, debt minimums and "
                f"goal contributions intact."
            ),
            amount=0.0,
            impact={
                "label": "overspend to recover",
                "value": sts["overspend_amount"],
                "horizon": "this month",
            },
            why=[
                f"${sts['spent_so_far']:,.0f} spent against a "
                f"${sts['discretionary_pool']:,.0f} discretionary pool",
                f"{sts['period']['days_remaining']} days still to cover",
            ],
            cta={"label": "See today", "tab": "today"},
            source="rule:daily_allowance",
        )]

    if sts.get("pace") == "over":
        return [_action(
            id=f"daily_allowance:pace:{period}",
            kind="spend_less",
            urgency="now",
            title=f"Keep today under ${sts['daily_safe_to_spend']:,.0f}",
            detail=(
                f"You're ahead of pace for the month. ${sts['daily_safe_to_spend']:,.0f} "
                f"a day for the remaining {sts['period']['days_remaining']} days "
                f"brings it back in line."
            ),
            amount=sts["daily_safe_to_spend"],
            why=[
                f"${sts['spent_so_far']:,.0f} spent, about "
                f"${sts['expected_spend_to_date']:,.0f} expected by now",
            ],
            cta={"label": "See today", "tab": "today"},
            source="rule:daily_allowance",
        )]
    return []


def rule_budget_overspend(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Per-category overruns, quantified in dollars and in days of allowance."""
    from analytics import compute_budget_statuses

    out: List[Dict[str, Any]] = []
    period = _period_key(ctx["today"])
    sts = ctx.get("safe_to_spend") or {}
    daily = sts.get("daily_safe_to_spend") or 0

    for status in compute_budget_statuses():
        over_by = status["current_month_spent"] - status["monthly_limit"]
        if status.get("over_budget") and over_by >= _MIN_IMPACT_DOLLARS:
            days = f" — about {over_by / daily:.0f} days of your allowance" if daily > 0 else ""
            out.append(_action(
                id=f"over_budget:{status['category']}:{period}",
                kind="spend_less",
                urgency="this_week",
                title=f"{status['category']} is ${over_by:,.0f} over",
                detail=(
                    f"${status['current_month_spent']:,.0f} spent against a "
                    f"${status['monthly_limit']:,.0f} cap{days}."
                ),
                amount=over_by,
                impact={"label": "over cap", "value": over_by, "horizon": "this month"},
                why=[f"{status['percent_used']:.0f}% of the monthly cap used"],
                cta={"label": "Review budgets", "tab": "budgets"},
                source="rule:budget_overspend",
            ))
        elif status["percent_used"] >= 90 and not status.get("over_budget"):
            remaining = status["monthly_limit"] - status["current_month_spent"]
            out.append(_action(
                id=f"budget_near:{status['category']}:{period}",
                kind="spend_less",
                urgency="this_month",
                title=f"{status['category']} has ${remaining:,.0f} left",
                detail=(
                    f"{status['percent_used']:.0f}% of the cap is gone with "
                    f"{sts.get('period', {}).get('days_remaining', '?')} days to go."
                ),
                amount=remaining,
                cta={"label": "Review budgets", "tab": "budgets"},
                source="rule:budget_overspend",
            ))
    return out


def rule_bill_due_soon(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Bills landing within a week, flagged when cash looks tight."""
    out: List[Dict[str, Any]] = []
    sts = ctx.get("safe_to_spend") or {}
    remaining = sts.get("remaining_pool")

    for bill in (ctx.get("bills") or {}).get("bills", []):
        if bill["days_until"] > 7:
            continue
        amount = bill.get("minimum_payment") or bill.get("balance") or 0
        if amount < _MIN_IMPACT_DOLLARS:
            continue

        if bill["days_until"] == 0:
            when = "today"
        elif bill["days_until"] == 1:
            when = "tomorrow"
        else:
            when = f"in {bill['days_until']} days"

        tight = remaining is not None and remaining < amount
        out.append(_action(
            id=f"bill_due:{bill['name']}:{bill['due_date']}",
            kind="pay_bill",
            urgency="now" if bill["days_until"] <= 2 else "this_week",
            title=f"{bill['name']} — ${amount:,.0f} due {when}",
            detail=(
                f"Only ${remaining:,.0f} is left in this month's discretionary "
                f"pool, so this one needs planning."
                if tight else
                f"Due {bill['due_date']}."
            ),
            amount=amount,
            due_date=bill["due_date"],
            cta={"label": "See bills", "tab": "bills"},
            source="rule:bill_due_soon",
        ))
    return out


def rule_goal_behind(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Goals off pace, with the monthly figure needed to recover."""
    from analytics import compute_goal_statuses

    out: List[Dict[str, Any]] = []
    period = _period_key(ctx["today"])
    for goal in compute_goal_statuses():
        if goal.get("pace_status") not in ("behind", "stalled"):
            continue
        required = goal.get("monthly_required") or 0
        actual = goal.get("actual_monthly_contribution") or 0
        gap = required - actual
        if gap < _MIN_IMPACT_DOLLARS:
            continue

        out.append(_action(
            id=f"goal_behind:{goal['id']}:{period}",
            kind="fund_goal",
            urgency="this_month",
            title=f"{goal['name']} needs ${gap:,.0f} more a month",
            detail=(
                f"On track it wants ${required:,.0f}/mo; you're putting in "
                f"about ${actual:,.0f}. Either find the difference or move the "
                f"target date."
            ),
            amount=gap,
            impact={"label": "monthly shortfall", "value": gap, "horizon": "until target"},
            due_date=goal.get("target_date"),
            why=[f"{goal['progress_pct']:.0f}% of the way there"],
            cta={"label": "Review goals", "tab": "goals"},
            source="rule:goal_behind",
        ))
    return out


def rule_extra_payment_impact(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """What an extra payment on the priciest debt actually buys."""
    import amortization

    loans = ctx.get("loans") or []
    if not loans:
        return []

    costly = max(loans, key=lambda l: float(l.get("interest_rate_pct") or 0))
    rate = float(costly.get("interest_rate_pct") or 0)
    if rate <= 0:
        return []

    start = costly.get("first_payment_date") or costly.get("origination_date")
    try:
        start_date = date.fromisoformat(str(start)[:10])
    except (ValueError, TypeError):
        return []

    try:
        comparison = amortization.compare_extra_payment(
            principal=costly.get("original_principal") or 0,
            annual_rate_pct=rate,
            term_months=int(costly.get("term_months") or 0),
            start_date=start_date,
            payment=costly.get("payment_amount"),
            extra_monthly=200.0,
        )
    except (ValueError, TypeError):
        return []

    saved = comparison.get("interest_saved") or 0
    months = comparison.get("months_saved") or 0
    if saved < 100 or months <= 0:
        return []

    return [_action(
        id=f"extra_payment:{costly['id']}",
        kind="pay_extra",
        urgency="fyi",
        title=f"$200/mo extra on {costly['name']} saves ${saved:,.0f}",
        detail=(
            f"At {rate:.2f}%, an extra $200 a month clears it {months} months "
            f"sooner and avoids ${saved:,.0f} of interest."
        ),
        amount=200.0,
        impact={"label": "interest avoided", "value": saved, "horizon": "life of loan"},
        why=[f"{months} months earlier payoff"],
        cta={"label": "Open loans", "tab": "loans"},
        source="rule:extra_payment_impact",
    )]


def rule_promo_apr_expiring(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Deferred-interest windows about to close.

    The Debt Payoff work already stores promo_expires; nothing consumed it
    until now. A 0% promo ending with a balance still on the card is the
    most expensive surprise in consumer credit.
    """
    out: List[Dict[str, Any]] = []
    today = ctx["today"]

    for account_id, details in state.account_details.items():
        expires = (details or {}).get("promo_expires")
        if not expires:
            continue
        try:
            expiry = date.fromisoformat(str(expires)[:10])
        except ValueError:
            continue
        days = (expiry - today).days
        if days < 0 or days > 60:
            continue

        meta = ctx["bills_module"].account_lookup(account_id)
        balance = abs(float(meta.get("ledger") or 0.0))
        if balance < _MIN_IMPACT_DOLLARS:
            continue

        regular = float(details.get("apr") or 0)
        annual_cost = balance * regular / 100.0
        out.append(_action(
            id=f"promo_expiring:{account_id}:{expiry.isoformat()}",
            kind="pay_extra",
            urgency="this_week" if days <= 14 else "this_month",
            title=(
                f"{meta.get('name') or 'Card'} promo rate ends in {days} days"
            ),
            detail=(
                f"${balance:,.0f} still on the card. Once the promo ends it "
                f"accrues at {regular:.2f}%, roughly ${annual_cost:,.0f} a year."
            ),
            amount=balance,
            impact={
                "label": "interest exposure",
                "value": round(annual_cost, 2),
                "horizon": "per year",
            },
            due_date=expiry.isoformat(),
            cta={"label": "Open payoff plan", "tab": "debt-payoff"},
            source="rule:promo_apr_expiring",
        ))
    return out


def rule_property_underperforming(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Properties the classifier flagged, with its quantified reasons."""
    portfolio = ctx.get("portfolio") or {}
    out: List[Dict[str, Any]] = []

    for entry in portfolio.get("underperforming", []):
        out.append(_action(
            id=f"property_review:{entry['property_id']}",
            kind="review_property",
            urgency="this_month",
            title=f"{entry['name']} needs a look",
            detail=entry["reasons"][0] if entry.get("reasons") else "",
            why=entry.get("reasons", [])[1:],
            cta={"label": "Open property", "tab": "properties"},
            source="rule:property_underperforming",
        ))
    return out


def rule_emergency_fund_floor(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Cash below a few months of essentials outranks any growth suggestion."""
    from analytics import _balances_snapshot

    sts = ctx.get("safe_to_spend") or {}
    if not sts.get("available"):
        return []

    monthly_essentials = (
        sts["commitments"]["fixed_bills"] + sts["commitments"]["minimum_debt_payments"]
    )
    if monthly_essentials <= 0:
        return []

    cash = float(_balances_snapshot().get("total_cash") or 0.0)
    months = cash / monthly_essentials
    if months >= 3:
        return []

    target = monthly_essentials * 3
    shortfall = target - cash
    return [_action(
        id="emergency_fund_floor",
        kind="emergency_fund",
        urgency="this_month",
        title=f"Cash covers {months:.1f} months of essentials",
        detail=(
            f"${cash:,.0f} on hand against ${monthly_essentials:,.0f} of monthly "
            f"commitments. Three months' worth would be ${target:,.0f}."
        ),
        amount=shortfall,
        impact={"label": "to reach 3 months", "value": round(shortfall, 2), "horizon": "buffer"},
        why=["A thin buffer turns any surprise into new debt"],
        cta={"label": "Review goals", "tab": "goals"},
        source="rule:emergency_fund_floor",
    )]


def rule_surplus_routing(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Money left over, and the single best place to put it.

    Deliberately simple for now: the full allocation waterfall (employer
    match, emergency floor, APR-versus-expected-return, tax-advantaged room)
    lands with the allocation module. This covers the common case — spare
    cash and expensive debt — without pretending to more rigour than it has.
    """
    sts = ctx.get("safe_to_spend") or {}
    if not sts.get("available") or sts.get("pace") != "under":
        return []

    surplus = sts.get("remaining_pool") or 0
    days_left = sts["period"]["days_remaining"]
    expected_leftover = surplus - (sts["daily_safe_to_spend"] * days_left * 0.8)
    if expected_leftover < 100:
        return []

    debts = [
        (account_id, details) for account_id, details in state.account_details.items()
        if (details or {}).get("apr")
    ]
    if not debts:
        return []

    account_id, details = max(debts, key=lambda d: float(d[1].get("apr") or 0))
    meta = ctx["bills_module"].account_lookup(account_id)
    balance = abs(float(meta.get("ledger") or 0.0))
    if balance < _MIN_IMPACT_DOLLARS:
        return []

    apr = float(details.get("apr") or 0)
    amount = round(min(expected_leftover, balance), 2)
    annual_saved = amount * apr / 100.0

    return [_action(
        id=f"route_surplus:{_period_key(ctx['today'])}",
        kind="route_surplus",
        urgency="fyi",
        title=f"About ${amount:,.0f} spare — put it on {meta.get('name') or 'your card'}",
        detail=(
            f"You're running under pace this month. At {apr:.2f}%, paying that "
            f"down is a guaranteed {apr:.2f}% return — better than any "
            f"comparable-risk investment."
        ),
        amount=amount,
        impact={
            "label": "interest avoided",
            "value": round(annual_saved, 2),
            "horizon": "per year",
        },
        cta={"label": "Open payoff plan", "tab": "debt-payoff"},
        source="rule:surplus_routing",
    )]


RULES = (
    rule_daily_allowance,
    rule_budget_overspend,
    rule_bill_due_soon,
    rule_goal_behind,
    rule_emergency_fund_floor,
    rule_promo_apr_expiring,
    rule_extra_payment_impact,
    rule_property_underperforming,
    rule_surplus_routing,
)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _build_context(today: date) -> Dict[str, Any]:
    """Gather every signal once, so nine rules don't re-derive the same data."""
    import bills as bills_module
    from analytics import compute_safe_to_spend

    ctx: Dict[str, Any] = {"today": today, "bills_module": bills_module}

    try:
        ctx["safe_to_spend"] = compute_safe_to_spend(as_of=today)
    except Exception:  # noqa: BLE001
        ctx["safe_to_spend"] = {"available": False}

    try:
        ctx["bills"] = bills_module.upcoming_bills(today=today)
    except Exception:  # noqa: BLE001
        ctx["bills"] = {"bills": []}

    try:
        import properties as properties_domain
        from db import properties_repo
        ctx["portfolio"] = properties_domain.compute_portfolio(as_of=today)
        ctx["loans"] = properties_repo.get_repo().list_loans()
    except Exception:  # noqa: BLE001
        ctx["portfolio"] = {}
        ctx["loans"] = []

    return ctx


def _impact_dollars(action: Dict[str, Any]) -> float:
    impact = action.get("impact") or {}
    return float(impact.get("value") or action.get("amount") or 0)


def build_actions(
    today: Optional[date] = None, limit: int = DEFAULT_LIMIT
) -> Dict[str, Any]:
    """Run every rule, drop dismissed items, rank, and cap.

    Ranked by urgency first, then dollar impact, then kind — so "you're over
    budget today" outranks "you could save $38k over thirty years", even
    though the second number is far larger. Today's behaviour is the thing
    the user can still change.
    """
    today = today or date.today()
    ctx = _build_context(today)

    actions: List[Dict[str, Any]] = []
    for rule in RULES:
        try:
            actions.extend(rule(ctx))
        except Exception:  # noqa: BLE001 - one bad rule must not blank the feed
            continue

    dismissed = set(state.coach_dismissals.keys())
    actions = [a for a in actions if a["id"] not in dismissed]

    actions.sort(key=lambda a: (
        URGENCY_ORDER.get(a["urgency"], 99),
        -_impact_dollars(a),
        KIND_PRIORITY.get(a["kind"], 99),
    ))
    for rank, action in enumerate(actions, start=1):
        action["rank"] = rank

    counts: Dict[str, int] = {}
    for action in actions:
        counts[action["urgency"]] = counts.get(action["urgency"], 0) + 1

    return {
        "generated_at": today.isoformat(),
        "actions": actions[:limit],
        "total": len(actions),
        "counts": counts,
    }


# ---------------------------------------------------------------------------
# Optional narration
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(r"\d[\d,]*\.?\d*")


def _numbers_in(text: str) -> set:
    """Bare numeric tokens, commas stripped, trailing zeros normalized."""
    out = set()
    for match in _NUMBER_RE.findall(text or ""):
        cleaned = match.replace(",", "").rstrip(".")
        if not cleaned:
            continue
        try:
            out.add(round(float(cleaned), 2))
        except ValueError:
            continue
    return out


def verify_narration(narration: str, actions: List[Dict[str, Any]]) -> bool:
    """True when every figure in ``narration`` appears in the payload.

    The highest-risk failure this module could produce is a plausible,
    fabricated dollar amount that the user acts on. Rather than trusting the
    model to stay grounded, the narration is checked against the numbers the
    rules actually produced and dropped wholesale if anything is unaccounted
    for. Cheap, and it fails safe: no narration is strictly better than a
    wrong one.
    """
    if not narration:
        return False

    allowed: set = set()
    for action in actions:
        for value in (action.get("amount"), (action.get("impact") or {}).get("value")):
            if value is not None:
                allowed.add(round(float(value), 2))
                allowed.add(float(int(value)))          # "$1,840" for 1840.00
        allowed |= _numbers_in(action.get("title", ""))
        allowed |= _numbers_in(action.get("detail", ""))
        for reason in action.get("why", []):
            allowed |= _numbers_in(reason)

    # Small integers are ordinals and counts ("the 3 things", "2 days"), not
    # claims about money.
    return all(n in allowed or n <= 31 for n in _numbers_in(narration))
