"""Where the next spare dollar should go.

A strict waterfall. Each tier consumes from the amount and passes the
remainder down, so the answer is an ordered split rather than a single
recommendation — which is what the question actually deserves: $500 spare
usually belongs in two or three places, not one.

The ordering is not a matter of taste. A 50% employer match beats a 24%
credit card beats a 7% expected return beats a 3.25% mortgage, and the only
judgement call in that chain is where the emergency buffer sits. That one is
a household decision, so it's a setting — with the cost of the choice
quantified in the caveats rather than hidden.

Two things this module refuses to do:

* **Invent an input.** An unknown employer match produces a ``question``,
  not an assumed 0%. Same for contribution room.
* **Compute a tax position.** It models contribution room, uses the stored
  withdrawal-tax assumption when comparing a mortgage against the market,
  and says "ask a CPA" about deductibility. Anything more would be a tax
  return, badly.

Split like ``retirement.py``: ``allocate()`` is pure, ``build_context()``
reads the stores.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Literal, Optional

Cadence = Literal["monthly", "one_time"]

# Contribution limits go stale every January. They ship as editable defaults
# stamped with the year they were correct for, and the payload carries that
# year so the UI can say so out loud rather than quietly misreport room.
DEFAULT_CONTRIBUTION_LIMITS_YEAR = 2026
DEFAULT_CONTRIBUTION_LIMITS: Dict[str, float] = {
    "401k": 24500.0,
    "ira": 7500.0,
    "hsa": 4400.0,
}

DEFAULT_SETTINGS: Dict[str, Any] = {
    "emergency_fund_months": 3,
    # None means "we haven't been told" — which produces a question rather
    # than an assumption. False would be an assumption.
    "employer_match_known": None,
    "employer_match_pct": None,               # 50 = fifty cents on the dollar
    "employer_match_limit_pct_of_pay": None,  # matched up to N% of pay
    "annual_gross_income": None,
    "annual_contribution_limits": dict(DEFAULT_CONTRIBUTION_LIMITS),
    "contribution_limits_as_of_year": DEFAULT_CONTRIBUTION_LIMITS_YEAR,
    "contributed_ytd": {},                    # {"401k": 0.0, "ira": 0.0, ...}
    "property_fund_monthly_target": None,
}

# Below this an allocation is noise — a $3 line item in a waterfall makes the
# whole answer look unserious.
_MIN_ALLOCATION = 5.0

# Keywords that mark a big_purchase goal as a property down-payment fund.
# Explicit and small on purpose: guessing wrong here routes real money.
_PROPERTY_GOAL_HINTS = (
    "propert", "house", "home", "duplex", "rental", "down payment",
    "downpayment", "real estate",
)

# A dollar put toward debt on the 1st of a month is exposed for 11.5 months
# of the first year, one put in on the 1st of December for 0.5. Summed over
# twelve equal contributions that's 72 month-dollars, i.e. six months of
# average exposure — the multiplier used to state first-year interest
# avoided for a recurring contribution.
_MONTHLY_FIRST_YEAR_MONTHS = 6.0


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

@dataclass
class DebtSlot:
    """A revolving or installment debt, with the rate that should rank it."""
    id: str
    name: str
    balance: float
    apr: float
    effective_apr: float
    rate_basis: str                    # human-readable "why this rate"
    minimum_payment: float = 0.0
    deferred_interest: bool = False
    promo_expires: Optional[str] = None


@dataclass
class MortgageSlot:
    id: str
    name: str
    balance: float
    rate_pct: float
    payment: float
    term_months: int = 0
    months_elapsed: int = 0
    first_payment_date: Optional[str] = None
    property_name: Optional[str] = None


@dataclass
class EmployerMatch:
    """Known match terms. Absent entirely when we haven't been told."""
    match_pct: float                   # 50 = fifty cents on the dollar
    limit_pct_of_pay: float
    annual_gross_income: float

    @property
    def monthly_target(self) -> float:
        return self.annual_gross_income / 12.0 * self.limit_pct_of_pay / 100.0


@dataclass
class PropertyFund:
    goal_id: str
    name: str
    monthly_required: Optional[float]
    remaining: float


@dataclass
class AllocationContext:
    monthly_essential_spend: float = 0.0
    cash_on_hand: float = 0.0
    emergency_fund_months: int = 3
    debts: List[DebtSlot] = field(default_factory=list)
    mortgages: List[MortgageSlot] = field(default_factory=list)
    investment_return_pct: float = 7.0
    tax_rate_on_withdrawals_pct: float = 15.0
    employer_match: Optional[EmployerMatch] = None
    employer_match_known: Optional[bool] = None
    contribution_limits: Dict[str, float] = field(default_factory=dict)
    contribution_limits_year: Optional[int] = None
    contributed_ytd: Dict[str, float] = field(default_factory=dict)
    property_fund: Optional[PropertyFund] = None
    debt_strategy: str = "avalanche"
    # False when no recurring bills were detected, so the essentials figure
    # is debt minimums only. The buffer target is then almost certainly too
    # small, and the waterfall has to say so rather than report "funded".
    essentials_include_bills: bool = True

    @property
    def emergency_target(self) -> float:
        return round(self.monthly_essential_spend * self.emergency_fund_months, 2)

    @property
    def after_tax_return_pct(self) -> float:
        """Expected return net of the stored withdrawal-tax assumption.

        Deliberately crude — it applies the withdrawal rate to the whole
        return, which overstates the drag on a taxable account where only
        realized gains are taxed. Stated in ``caveats`` rather than modeled,
        because modeling it properly means modeling a tax return.
        """
        return round(
            self.investment_return_pct * (1 - self.tax_rate_on_withdrawals_pct / 100.0),
            2,
        )


# ---------------------------------------------------------------------------
# Effective APR
# ---------------------------------------------------------------------------

def effective_apr(
    *,
    apr: Optional[float],
    promo_apr: Optional[float] = None,
    promo_expires: Optional[str] = None,
    deferred_interest: bool = False,
    today: Optional[date] = None,
) -> tuple:
    """The rate that should actually drive priority, and why.

    A nominal 0% is not a 0% cost of carry, and the difference between the
    two promo types is the whole point:

    * **Deferred interest** — interest is accruing right now at the regular
      rate and is merely *waived* if the balance clears by the deadline. The
      card is already a full-rate debt; it just hasn't billed yet. Ranking it
      at 0% is how people get a four-figure surprise.
    * **A true promotional rate** — nothing accrues until expiry. Over a
      twelve-month comparison window the cost is the blend of the promo rate
      for the months that remain and the regular rate for the rest.

    Returns ``(rate_pct, basis)`` where ``basis`` is the sentence the UI
    shows next to it.
    """
    regular = float(apr or 0.0)
    today = today or date.today()

    if promo_apr is None or not promo_expires:
        return regular, "stated APR"

    try:
        expiry = date.fromisoformat(str(promo_expires)[:10])
    except (ValueError, TypeError):
        return regular, "stated APR (promo date unreadable)"

    months_left = max(0.0, (expiry - today).days / 30.44)
    if months_left <= 0:
        return regular, "promo has expired — the regular rate applies"

    if deferred_interest:
        return regular, (
            f"deferred interest — it is accruing at {regular:.2f}% today and is "
            f"only waived if the balance clears by {expiry.isoformat()}"
        )

    promo = float(promo_apr)
    window = min(months_left, 12.0)
    blended = (promo * window + regular * (12.0 - window)) / 12.0
    return round(blended, 2), (
        f"{promo:.2f}% until {expiry.isoformat()}, then {regular:.2f}% — "
        f"blended over the next year"
    )


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------

def _allocation(
    *,
    tier: int,
    key: str,
    label: str,
    amount: float,
    rationale: str,
    benefit: Optional[Dict[str, Any]] = None,
    cta: Optional[Dict[str, str]] = None,
    target_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "tier": tier,
        "key": key,
        "label": label,
        "amount": round(amount, 2),
        "rationale": rationale,
        "quantified_benefit": benefit,
        "cta": cta,
        "target_id": target_id,
    }


def _skip(tier: int, key: str, label: str, reason: str) -> Dict[str, Any]:
    return {"tier": tier, "key": key, "label": label, "reason": reason}


def _guaranteed_return(rate_pct: float, amount: float, cadence: Cadence) -> Dict[str, Any]:
    """First-year interest avoided, and the risk-free rate it represents."""
    months = 12.0 if cadence == "one_time" else _MONTHLY_FIRST_YEAR_MONTHS
    avoided = amount * (rate_pct / 100.0) * (months / 12.0)
    return {
        "label": "interest avoided in the first year",
        "value": round(avoided, 2),
        "rate_pct": round(rate_pct, 2),
        "guaranteed": True,
        "horizon": "first year",
    }


def _projected_growth(
    rate_pct: float, amount: float, cadence: Cadence, years: int = 10
) -> Dict[str, Any]:
    r = rate_pct / 100.0
    if cadence == "one_time":
        future = amount * ((1 + r) ** years)
    else:
        # Ordinary annuity on the annualized contribution.
        annual = amount * 12
        future = annual * (((1 + r) ** years - 1) / r) if r else annual * years
    return {
        "label": f"projected value in {years} years",
        "value": round(future, 2),
        "rate_pct": round(rate_pct, 2),
        "guaranteed": False,
        "horizon": f"{years} years",
    }


# ---------------------------------------------------------------------------
# Tiers
# ---------------------------------------------------------------------------

def _tier_employer_match(remaining: float, ctx: AllocationContext, cadence: Cadence, out: Dict):
    """Tier 1 — the only guaranteed 50–100% return available to anyone.

    An unknown match does not halt the waterfall: uncertainty about a
    benefit is not a reason to leave the rest of the money unallocated.
    """
    if ctx.employer_match_known is None or (
        ctx.employer_match_known and ctx.employer_match is None
    ):
        out["questions"].append({
            "key": "employer_match",
            "question": "Does your employer match retirement contributions, and up to what percentage of your pay?",
            "why": (
                "A 50% match is an instant, guaranteed 50% return — it outranks "
                "every other use of a dollar, including a 24% credit card. "
                "Until this is answered the waterfall may be starting one tier "
                "too low."
            ),
        })
        return remaining

    if not ctx.employer_match_known or ctx.employer_match is None:
        out["skipped"].append(_skip(
            1, "employer_match", "Employer match",
            "No employer match available.",
        ))
        return remaining

    if cadence == "one_time":
        out["skipped"].append(_skip(
            1, "employer_match", "Employer match",
            "Matches are paid per paycheck, so a lump sum can't capture one. "
            "Raising your payroll contribution rate is the way to reach it.",
        ))
        return remaining

    match = ctx.employer_match
    target = match.monthly_target
    if target < _MIN_ALLOCATION:
        out["skipped"].append(_skip(
            1, "employer_match", "Employer match",
            "The matched amount is too small to be worth routing separately.",
        ))
        return remaining

    amount = min(remaining, target)
    if amount < _MIN_ALLOCATION:
        return remaining

    matched = amount * match.match_pct / 100.0
    out["allocations"].append(_allocation(
        tier=1,
        key="employer_match",
        label="Retirement contribution, up to the employer match",
        amount=amount,
        rationale=(
            f"Your employer adds {match.match_pct:.0f}c per dollar up to "
            f"{match.limit_pct_of_pay:.0f}% of pay — about "
            f"${target:,.0f}/mo. That is a guaranteed "
            f"{match.match_pct:.0f}% return, immediately, and it is the only "
            f"place a dollar does better than paying off expensive debt."
        ),
        benefit={
            "label": "employer contribution",
            "value": round(matched, 2),
            "rate_pct": match.match_pct,
            "guaranteed": True,
            "horizon": "per month",
        },
        cta={"label": "Open retirement plan", "tab": "retirement"},
    ))
    return remaining - amount


def _tier_emergency_floor(remaining: float, ctx: AllocationContext, cadence: Cadence, out: Dict):
    """Tier 2 — the buffer, and a hard stop until it exists.

    Returns ``(remaining, halt)``. When the floor isn't met, every lower
    tier is skipped: without a buffer, the next unexpected expense becomes
    new debt at whatever rate is available, which undoes the tier below it
    anyway.
    """
    target = ctx.emergency_target
    if target <= 0:
        out["skipped"].append(_skip(
            2, "emergency_fund", "Emergency fund",
            "Not enough data on monthly essential spending to size a buffer.",
        ))
        return remaining, False

    shortfall = target - ctx.cash_on_hand
    if shortfall <= 0:
        out["skipped"].append(_skip(
            2, "emergency_fund", "Emergency fund",
            f"Already funded — ${ctx.cash_on_hand:,.0f} on hand covers "
            f"{ctx.emergency_fund_months} months of essentials "
            f"(${target:,.0f}).",
        ))
        return remaining, False

    amount = min(remaining, shortfall)
    months_covered = (
        ctx.cash_on_hand / ctx.monthly_essential_spend
        if ctx.monthly_essential_spend else 0.0
    )
    out["allocations"].append(_allocation(
        tier=2,
        key="emergency_fund",
        label=f"Emergency fund, to {ctx.emergency_fund_months} months",
        amount=amount,
        rationale=(
            f"${ctx.cash_on_hand:,.0f} on hand covers {months_covered:.1f} months "
            f"of the ${ctx.monthly_essential_spend:,.0f} you must pay each month. "
            f"${shortfall:,.0f} more reaches {ctx.emergency_fund_months} months. "
            f"Without it, the next surprise becomes new debt."
        ),
        benefit={
            "label": "months of cover added",
            "value": round(amount / ctx.monthly_essential_spend, 2)
            if ctx.monthly_essential_spend else None,
            "guaranteed": True,
            "horizon": "buffer",
        },
        cta={"label": "Review goals", "tab": "goals"},
    ))

    remaining -= amount
    halt = remaining < _MIN_ALLOCATION
    if halt:
        out["skipped"].append(_skip(
            0, "below_emergency_floor", "Everything below the buffer",
            f"The emergency fund is still ${shortfall - amount:,.0f} short, so "
            f"nothing is routed past it this month.",
        ))
    return remaining, halt


def _tier_high_interest_debt(remaining: float, ctx: AllocationContext, cadence: Cadence, out: Dict):
    """Tier 3 — every debt costing more than the market is expected to pay.

    The comparison is against the *expected* investment return, and it is
    not close for a credit card: paying down 24% debt is a guaranteed 24%,
    where 7% in the market is an average across decades that includes years
    of losses.
    """
    hurdle = ctx.investment_return_pct
    expensive = [d for d in ctx.debts if d.effective_apr > hurdle and d.balance > 0]

    if not expensive:
        if ctx.debts:
            out["skipped"].append(_skip(
                3, "high_interest_debt", "High-interest debt",
                f"No debt costs more than the {hurdle:.1f}% you expect from "
                f"investing, so paying it down early is the worse trade.",
            ))
        return remaining

    if ctx.debt_strategy == "snowball":
        expensive.sort(key=lambda d: d.balance)
        order_note = "smallest balance first (snowball)"
    else:
        expensive.sort(key=lambda d: -d.effective_apr)
        order_note = "highest rate first (avalanche)"

    for debt in expensive:
        if remaining < _MIN_ALLOCATION:
            break
        amount = min(remaining, debt.balance)
        if amount < _MIN_ALLOCATION:
            continue

        urgency = ""
        if debt.deferred_interest and debt.promo_expires:
            urgency = (
                f" This one is deferred-interest: clear it before "
                f"{debt.promo_expires} or the whole accrued amount is billed at "
                f"once."
            )

        out["allocations"].append(_allocation(
            tier=3,
            key="high_interest_debt",
            label=f"Pay down {debt.name}",
            amount=amount,
            rationale=(
                f"{debt.rate_basis.capitalize()}, which is above the "
                f"{hurdle:.1f}% you expect from investing. Paying it is a "
                f"guaranteed {debt.effective_apr:.2f}% return; the market's is "
                f"not. Ordered {order_note}.{urgency}"
            ),
            benefit=_guaranteed_return(debt.effective_apr, amount, cadence),
            cta={"label": "Open payoff plan", "tab": "debt-payoff"},
            target_id=debt.id,
        ))
        remaining -= amount

    return remaining


def _tier_tax_advantaged(remaining: float, ctx: AllocationContext, cadence: Cadence, out: Dict):
    """Tier 4 — contribution room, which expires at year end and never returns."""
    if not ctx.contribution_limits:
        out["questions"].append({
            "key": "contribution_room",
            "question": "How much 401(k) / IRA / HSA room do you have left this year?",
            "why": (
                "Tax-advantaged room is use-it-or-lose-it: December 31 passes "
                "and that year's allowance is gone permanently."
            ),
        })
        return remaining

    total_room = 0.0
    parts: List[str] = []
    for name, limit in ctx.contribution_limits.items():
        used = float(ctx.contributed_ytd.get(name) or 0.0)
        room = max(0.0, float(limit) - used)
        if room > 0:
            total_room += room
            parts.append(f"{name.upper()} ${room:,.0f}")

    if total_room <= 0:
        out["skipped"].append(_skip(
            4, "tax_advantaged", "Tax-advantaged accounts",
            "This year's contribution room is already used.",
        ))
        return remaining

    monthly_room = total_room / 12.0 if cadence == "monthly" else total_room
    amount = min(remaining, monthly_room)
    if amount < _MIN_ALLOCATION:
        return remaining

    out["allocations"].append(_allocation(
        tier=4,
        key="tax_advantaged",
        label="Tax-advantaged investing",
        amount=amount,
        rationale=(
            f"${total_room:,.0f} of room left for "
            f"{ctx.contribution_limits_year or 'this year'} "
            f"({', '.join(parts)}). Room does not roll over — what isn't used "
            f"by December 31 is gone for good, which is why this outranks a "
            f"taxable account holding the identical fund."
        ),
        benefit=_projected_growth(ctx.investment_return_pct, amount, cadence),
        cta={"label": "Open investments", "tab": "investments"},
    ))
    return remaining - amount


def _tier_property_fund(remaining: float, ctx: AllocationContext, cadence: Cadence, out: Dict):
    """Tier 5 — the next down payment, when a goal says one is being saved for."""
    fund = ctx.property_fund
    if fund is None:
        out["skipped"].append(_skip(
            5, "property_fund", "Property acquisition fund",
            "No property or big-purchase goal on file. Add one and spare cash "
            "starts routing here.",
        ))
        return remaining

    want = fund.monthly_required if cadence == "monthly" else fund.remaining
    want = want if want and want > 0 else fund.remaining
    amount = min(remaining, want) if want and want > 0 else remaining
    if amount < _MIN_ALLOCATION:
        return remaining

    out["allocations"].append(_allocation(
        tier=5,
        key="property_fund",
        label=f"{fund.name}",
        amount=amount,
        rationale=(
            f"${fund.remaining:,.0f} still to raise. This is the tier where "
            f"the plan compounds fastest: a down payment buys an asset a "
            f"tenant then pays down for you."
        ),
        benefit={
            "label": "remaining to target",
            "value": round(max(0.0, fund.remaining - amount), 2),
            "guaranteed": True,
            "horizon": "to goal",
        },
        cta={"label": "Open equity & deals", "tab": "equity"},
        target_id=fund.goal_id,
    ))
    return remaining - amount


def _tier_invest_or_principal(remaining: float, ctx: AllocationContext, cadence: Cadence, out: Dict):
    """Tier 6 — the last dollar: market, or the mortgage.

    Extra principal only when the mortgage costs more than the market is
    expected to return after tax. Otherwise invest — and say plainly why the
    mortgage lost, because "why not just pay off the house" is the question
    that actually gets asked.
    """
    if remaining < _MIN_ALLOCATION:
        return remaining

    after_tax = ctx.after_tax_return_pct
    costliest = max(ctx.mortgages, key=lambda m: m.rate_pct, default=None)

    if costliest is not None and costliest.rate_pct > after_tax:
        benefit = _guaranteed_return(costliest.rate_pct, remaining, cadence)
        try:
            import amortization
            if costliest.first_payment_date and costliest.term_months:
                comparison = amortization.compare_extra_payment(
                    principal=costliest.balance,
                    annual_rate_pct=costliest.rate_pct,
                    term_months=max(1, costliest.term_months - costliest.months_elapsed),
                    start_date=date.today(),
                    payment=costliest.payment,
                    extra_monthly=remaining if cadence == "monthly" else 0.0,
                )
                if cadence == "monthly" and (comparison.get("months_saved") or 0) > 0:
                    benefit = {
                        "label": "interest avoided over the life of the loan",
                        "value": round(comparison["interest_saved"], 2),
                        "rate_pct": costliest.rate_pct,
                        "guaranteed": True,
                        "horizon": f"{comparison['months_saved']} months sooner",
                    }
        except Exception:  # noqa: BLE001 - the simple figure is a fine fallback
            pass

        out["allocations"].append(_allocation(
            tier=6,
            key="extra_mortgage_principal",
            label=f"Extra principal on {costliest.name}",
            amount=remaining,
            rationale=(
                f"At {costliest.rate_pct:.2f}% the mortgage costs more than the "
                f"{after_tax:.2f}% you'd expect to keep from the market after "
                f"tax. Paying it down is the same return with none of the risk "
                f"— and it brings forward the year the rent stops going to a "
                f"lender."
            ),
            benefit=benefit,
            cta={"label": "Open loans", "tab": "loans"},
            target_id=costliest.id,
        ))
        return 0.0

    out["allocations"].append(_allocation(
        tier=6,
        key="taxable_investing",
        label="Taxable brokerage",
        amount=remaining,
        rationale=(
            f"Nothing left costs more than the {after_tax:.2f}% after-tax "
            f"return you expect, so this is where the money works hardest."
        ),
        benefit=_projected_growth(ctx.investment_return_pct, remaining, cadence),
        cta={"label": "Open investments", "tab": "investments"},
    ))

    if costliest is not None:
        out["skipped"].append(_skip(
            6, "extra_mortgage_principal", f"Extra principal on {costliest.name}",
            f"At {costliest.rate_pct:.2f}% it is cheaper than the "
            f"{after_tax:.2f}% after-tax return you expect from investing, so "
            f"paying it early costs you the difference. It also converts liquid "
            f"money into equity you can only reach by borrowing or selling.",
        ))
    return 0.0


# ---------------------------------------------------------------------------
# The waterfall
# ---------------------------------------------------------------------------

def allocate(
    amount: float,
    ctx: AllocationContext,
    *,
    cadence: Cadence = "monthly",
) -> Dict[str, Any]:
    """Split ``amount`` across the tiers, in order, and explain both sides.

    ``skipped`` is not an afterthought — "why not the mortgage?" is the
    question the user will actually have, and an answer that only lists
    winners is not an answer.
    """
    if amount <= 0:
        return {
            "available": False,
            "reason": "no_amount",
            "detail": "Nothing to allocate.",
        }

    out: Dict[str, Any] = {
        "allocations": [], "skipped": [], "questions": [], "caveats": [],
    }
    remaining = float(amount)

    remaining = _tier_employer_match(remaining, ctx, cadence, out)
    remaining, halt = _tier_emergency_floor(remaining, ctx, cadence, out)

    if not halt:
        remaining = _tier_high_interest_debt(remaining, ctx, cadence, out)
        remaining = _tier_tax_advantaged(remaining, ctx, cadence, out)
        remaining = _tier_property_fund(remaining, ctx, cadence, out)
        remaining = _tier_invest_or_principal(remaining, ctx, cadence, out)

    # --- caveats: the places this answer is softest -------------------------
    # The buffer gates everything below it, so a target built on an
    # incomplete essentials figure quietly waves money past a tier it should
    # have stopped at. Cheaper to say so than to be confidently wrong.
    if not ctx.essentials_include_bills and ctx.monthly_essential_spend > 0:
        out["caveats"].append(
            f"No recurring bills were detected, so ${ctx.monthly_essential_spend:,.0f}/mo "
            f"of essentials counts debt minimums only — rent, utilities and "
            f"insurance are missing. The real emergency-fund target is very "
            f"likely higher than ${ctx.emergency_target:,.0f}. Import a few more "
            f"months of transactions, or raise the buffer months in settings."
        )
    if ctx.contribution_limits_year:
        out["caveats"].append(
            f"Contribution limits are the {ctx.contribution_limits_year} figures. "
            f"Confirm them against your plan documents — they change most years."
        )
    if any(m.rate_pct > 0 for m in ctx.mortgages):
        out["caveats"].append(
            "Mortgage interest may be deductible, which would lower its real "
            "cost and tilt the last tier toward investing. This app does not "
            "compute your tax position — ask a CPA."
        )
    out["caveats"].append(
        "The after-tax return applies the withdrawal-tax assumption to the "
        "whole return, which overstates the drag on a taxable account where "
        "only realized gains are taxed."
    )

    # The emergency floor outranking expensive debt is the one genuinely
    # contested call in the waterfall. Rather than bury it, price it.
    unfunded = ctx.emergency_target - ctx.cash_on_hand
    if unfunded > 0:
        worst = max((d for d in ctx.debts), key=lambda d: d.effective_apr, default=None)
        if worst is not None and worst.effective_apr > 15:
            annual_cost = worst.balance * worst.effective_apr / 100.0
            out["caveats"].append(
                f"Holding to a {ctx.emergency_fund_months}-month buffer before "
                f"attacking {worst.name} leaves ${worst.balance:,.0f} accruing at "
                f"{worst.effective_apr:.2f}% — about ${annual_cost:,.0f} a year. "
                f"Many planners fund a smaller starter buffer first, then the "
                f"card, then the rest. Lower the buffer target in settings if "
                f"you want that order."
            )

    allocated = round(sum(a["amount"] for a in out["allocations"]), 2)
    return {
        "available": True,
        "amount": round(float(amount), 2),
        "cadence": cadence,
        "allocated": allocated,
        "unallocated": round(float(amount) - allocated, 2),
        "allocations": out["allocations"],
        "skipped": out["skipped"],
        "questions": out["questions"],
        "caveats": out["caveats"],
        "assumptions": {
            "investment_return_pct": ctx.investment_return_pct,
            "after_tax_return_pct": ctx.after_tax_return_pct,
            "tax_rate_on_withdrawals_pct": ctx.tax_rate_on_withdrawals_pct,
            "emergency_fund_months": ctx.emergency_fund_months,
            "emergency_target": ctx.emergency_target,
            "debt_strategy": ctx.debt_strategy,
            "contribution_limits_year": ctx.contribution_limits_year,
        },
    }


# ---------------------------------------------------------------------------
# Store-reading side
# ---------------------------------------------------------------------------

def _property_fund_from_goals(goals: List[Dict[str, Any]]) -> Optional[PropertyFund]:
    """The first big-purchase goal that reads like a property fund."""
    for goal in goals:
        if (goal.get("kind") or "") != "big_purchase":
            continue
        haystack = f"{goal.get('name', '')} {goal.get('notes', '')}".lower()
        if not any(hint in haystack for hint in _PROPERTY_GOAL_HINTS):
            continue
        remaining = float(goal.get("target_amount") or 0) - float(
            goal.get("current_balance") or 0
        )
        if remaining <= 0:
            continue
        return PropertyFund(
            goal_id=goal.get("id", ""),
            name=goal.get("name", "Property fund"),
            monthly_required=goal.get("monthly_required"),
            remaining=round(remaining, 2),
        )
    return None


def build_context(as_of: Optional[date] = None) -> AllocationContext:
    """Assemble the waterfall's inputs from the live stores."""
    import state
    from analytics import (
        _balances_snapshot,
        _debts_from_accounts,
        _load_user_profile,
        compute_goal_statuses,
        compute_safe_to_spend,
    )

    today = as_of or date.today()
    settings = {**DEFAULT_SETTINGS, **(dict(state.allocation_settings.get("household") or {}))}

    # Essentials come from safe-to-spend so the buffer target matches what
    # the coach and the Today page already tell the user they owe.
    monthly_essential = 0.0
    essentials_include_bills = True
    sts = compute_safe_to_spend(as_of=today)
    if sts.get("available"):
        commitments = sts["commitments"]
        monthly_essential = float(
            commitments["fixed_bills"] + commitments["minimum_debt_payments"]
        )
        essentials_include_bills = float(commitments["fixed_bills"]) > 0

    snapshot = _balances_snapshot()
    cash = float(snapshot.get("total_cash") or 0.0)

    debts: List[DebtSlot] = []
    for entry in _debts_from_accounts(snapshot):
        balance = abs(float(entry.get("balance") or 0.0))
        if balance <= 0:
            continue
        details = state.account_details.get(entry.get("account_id") or "") or {}
        rate, basis = effective_apr(
            apr=entry.get("apr"),
            promo_apr=details.get("promo_apr"),
            promo_expires=details.get("promo_expires"),
            deferred_interest=bool(details.get("deferred_interest")),
            today=today,
        )
        debts.append(DebtSlot(
            id=entry.get("account_id", ""),
            name=entry.get("name") or "Card",
            balance=round(balance, 2),
            apr=float(entry.get("apr") or 0.0),
            effective_apr=rate,
            rate_basis=f"{rate:.2f}% — {basis}",
            minimum_payment=float(entry.get("minimum_payment") or 0.0),
            deferred_interest=bool(details.get("deferred_interest")),
            promo_expires=details.get("promo_expires"),
        ))

    mortgages: List[MortgageSlot] = []
    try:
        import amortization
        import properties as properties_domain
        from db import properties_repo
        repo = properties_repo.get_repo()
        prop_names = {p["id"]: p.get("name", "") for p in repo.list_properties()}
        for loan in repo.list_loans():
            balance = properties_domain.resolve_loan_balance(loan, today)
            if not balance or balance <= 0:
                continue
            start = loan.get("first_payment_date") or loan.get("origination_date")
            try:
                elapsed = amortization.current_period_index(
                    date.fromisoformat(str(start)[:10]), today
                )
            except (ValueError, TypeError):
                elapsed = 0
            mortgages.append(MortgageSlot(
                id=loan.get("id", ""),
                name=loan.get("name") or "Loan",
                balance=round(float(balance), 2),
                rate_pct=float(loan.get("interest_rate_pct") or 0.0),
                payment=properties_domain.loan_payment(loan),
                term_months=int(loan.get("term_months") or 0),
                months_elapsed=max(0, elapsed),
                first_payment_date=str(start)[:10] if start else None,
                property_name=prop_names.get(loan.get("property_id") or ""),
            ))
    except Exception:  # noqa: BLE001 - properties are optional
        mortgages = []

    retirement_assumptions: Dict[str, Any] = {}
    try:
        import retirement as retirement_domain
        retirement_assumptions = {
            **retirement_domain.DEFAULT_ASSUMPTIONS,
            **(dict(state.retirement_assumptions.get("household") or {})),
        }
    except Exception:  # noqa: BLE001
        retirement_assumptions = {}

    match: Optional[EmployerMatch] = None
    known = settings.get("employer_match_known")
    if known and settings.get("annual_gross_income"):
        match = EmployerMatch(
            match_pct=float(settings.get("employer_match_pct") or 0.0),
            limit_pct_of_pay=float(settings.get("employer_match_limit_pct_of_pay") or 0.0),
            annual_gross_income=float(settings["annual_gross_income"]),
        )

    profile = _load_user_profile() or {}

    return AllocationContext(
        monthly_essential_spend=round(monthly_essential, 2),
        cash_on_hand=round(cash, 2),
        emergency_fund_months=int(settings.get("emergency_fund_months") or 3),
        debts=debts,
        mortgages=mortgages,
        investment_return_pct=float(
            retirement_assumptions.get("investment_return_pct") or 7.0
        ),
        tax_rate_on_withdrawals_pct=float(
            retirement_assumptions.get("tax_rate_on_withdrawals_pct") or 0.0
        ),
        employer_match=match,
        employer_match_known=known,
        contribution_limits=dict(settings.get("annual_contribution_limits") or {}),
        contribution_limits_year=settings.get("contribution_limits_as_of_year"),
        contributed_ytd=dict(settings.get("contributed_ytd") or {}),
        property_fund=_property_fund_from_goals(compute_goal_statuses()),
        debt_strategy=profile.get("debt_strategy") or "avalanche",
        essentials_include_bills=essentials_include_bills,
    )


def allocate_from_stores(
    amount: float,
    *,
    cadence: Cadence = "monthly",
    as_of: Optional[date] = None,
) -> Dict[str, Any]:
    """Convenience wrapper: build the context, run the waterfall."""
    return allocate(amount, build_context(as_of=as_of), cadence=cadence)
