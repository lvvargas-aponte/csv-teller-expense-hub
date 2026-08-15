"""Loan amortization — closed-form payment, per-period principal/interest
split, and full schedule generation.

**Pure and stateless by design: this module must never ``import state``.**
Everything it needs arrives as arguments, which keeps it trivially testable
and lets the retirement projection call ``remaining_balance()`` thousands of
times without touching a store.

Precision
---------
Money is ``float`` everywhere else in this codebase (transactions live as
JSONB). That is fine for aggregating a few hundred rows, but a 360-period
amortization loop accumulates visible drift, and the household will compare
the principal/interest split against a real servicer statement — a four-cent
mismatch discredits every other number in the app.

So: ``Decimal`` internally, quantized to cents at each period boundary,
converted to ``float`` at the public boundary. Decimal deliberately does not
leak out; ``db/accounts_repo.py`` already establishes the same
float-at-the-edge convention for ``Numeric`` columns.

Relationship to the payoff planner
----------------------------------
``build_schedule`` models ONE loan in isolation. ``simulate_payoff_plan``
models MANY debts competing for a shared pool of money, where a retired
debt's freed-up minimum cascades into the next one. They are different
problems; both live here so there is a single home for debt math.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Wide enough that intermediate products never lose cents before quantization.
getcontext().prec = 28

CENTS = Decimal("0.01")

# Mirrors ``state.PAYOFF_MAX_MONTHS``. Duplicated as a literal rather than
# imported so this module stays free of application state; the payoff router
# passes its own cap through explicitly.
MAX_PERIODS = 600

_MONTHS_PER_YEAR = 12


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _dec(value: Any) -> Decimal:
    """Coerce to Decimal via ``str`` so float noise isn't inherited.

    ``Decimal(0.1)`` is 0.1000000000000000055511151231257827; ``Decimal("0.1")``
    is exactly 0.1. Callers hand us floats, so route every one through str().
    """
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _money(value: Decimal) -> Decimal:
    """Round to cents, half-up (what a lender does, and what Python's
    banker's-rounding default does *not* do)."""
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def _f(value: Decimal) -> float:
    return float(value)


def monthly_rate(annual_rate_pct: Any) -> Decimal:
    """Periodic rate from a nominal annual percentage.

    ``6.5`` (meaning 6.5% APR) -> ``0.00541666…``. Not quantized — rounding
    the rate itself would introduce far more error than it removes.
    """
    return _dec(annual_rate_pct) / Decimal(100) / Decimal(_MONTHS_PER_YEAR)


# ---------------------------------------------------------------------------
# Closed-form primitives
# ---------------------------------------------------------------------------

def pmt(principal: Any, annual_rate_pct: Any, term_months: int) -> Decimal:
    """Level payment that amortizes ``principal`` over ``term_months``.

        P · r / (1 − (1 + r)^−n)

    A 0% loan divides evenly instead (the formula is undefined at r = 0).
    Returns a cent-quantized Decimal.
    """
    p = _dec(principal)
    n = int(term_months)
    if n <= 0:
        raise ValueError("term_months must be positive")
    if p <= 0:
        return Decimal("0.00")

    r = monthly_rate(annual_rate_pct)
    if r == 0:
        return _money(p / Decimal(n))

    growth = (Decimal(1) + r) ** n
    return _money(p * r * growth / (growth - Decimal(1)))


def nper(principal: Any, annual_rate_pct: Any, payment: Any) -> Optional[int]:
    """Periods needed to clear ``principal`` at a fixed ``payment``.

    Returns ``None`` when the loan never amortizes — i.e. the payment does
    not exceed the first period's interest. Callers must treat ``None`` as
    "this debt grows forever", not as zero.
    """
    p = _dec(principal)
    pay = _dec(payment)
    if p <= 0:
        return 0
    if pay <= 0:
        return None

    r = monthly_rate(annual_rate_pct)
    if r == 0:
        # ceil without float math
        periods = int((p / pay).to_integral_value(rounding="ROUND_CEILING"))
        return periods

    if pay <= p * r:
        return None

    # n = −ln(1 − P·r/A) / ln(1 + r)
    ratio = Decimal(1) - (p * r / pay)
    periods = -(ratio.ln()) / (Decimal(1) + r).ln()
    return int(periods.to_integral_value(rounding="ROUND_CEILING"))


def remaining_balance(
    principal: Any,
    annual_rate_pct: Any,
    payment: Any,
    periods_elapsed: int,
) -> Decimal:
    """Balance after ``periods_elapsed`` level payments, in closed form.

        B = P(1 + r)^k − A·((1 + r)^k − 1)/r

    Used by the retirement projection, which needs a balance 30 years out
    for every loan every year and must not build 360-row schedules to get
    it. Never returns negative — a loan that finished early reads as 0.
    """
    p = _dec(principal)
    pay = _dec(payment)
    k = int(periods_elapsed)
    if k <= 0:
        return _money(p)
    if p <= 0:
        return Decimal("0.00")

    r = monthly_rate(annual_rate_pct)
    if r == 0:
        return _money(max(Decimal("0"), p - pay * Decimal(k)))

    growth = (Decimal(1) + r) ** k
    balance = p * growth - pay * (growth - Decimal(1)) / r
    return _money(max(Decimal("0"), balance))


def split_for_period(
    *,
    principal: Any,
    annual_rate_pct: Any,
    payment: Any,
    period_index: int,
) -> Tuple[float, float]:
    """Interest and principal portions of one specific payment.

    ``period_index`` is 1-based: period 1 is the first payment ever made.
    This is the primitive behind "how much of THIS month's mortgage payment
    was interest?" — goal #6 — so it is deliberately cheap and standalone.

    Returns ``(interest, principal_portion)`` as floats. The principal
    portion is capped at the outstanding balance so a final partial payment
    doesn't over-amortize.
    """
    if period_index < 1:
        raise ValueError("period_index is 1-based")

    opening = remaining_balance(
        principal, annual_rate_pct, payment, period_index - 1
    )
    if opening <= 0:
        return (0.0, 0.0)

    interest = _money(opening * monthly_rate(annual_rate_pct))
    principal_portion = _money(min(_dec(payment) - interest, opening))
    return (_f(interest), _f(principal_portion))


def payoff_date(start: date, periods: int) -> date:
    """First of the month ``periods`` months after ``start``.

    Matches the month arithmetic the payoff router already uses, so dates
    stay consistent between the planner and the schedule.
    """
    total = start.month - 1 + int(periods)
    return date(start.year + total // _MONTHS_PER_YEAR, total % _MONTHS_PER_YEAR + 1, 1)


def current_period_index(first_payment_date: date, as_of: date) -> int:
    """Which payment number ``as_of`` falls in, 1-based.

    0 means the first payment hasn't come due yet. Whole months only —
    day-of-month is ignored, matching how the rest of the app buckets time.
    """
    months = (
        (as_of.year - first_payment_date.year) * _MONTHS_PER_YEAR
        + (as_of.month - first_payment_date.month)
    )
    return max(0, months + 1)


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AmortizationPeriod:
    period: int
    date: date
    payment: float          # principal + interest actually applied (excl. escrow)
    principal: float
    interest: float
    extra: float
    escrow: float
    balance: float          # closing balance after this payment
    cumulative_interest: float
    cumulative_principal: float


@dataclass(frozen=True)
class AmortizationResult:
    periods: List[AmortizationPeriod] = field(default_factory=list)
    monthly_payment: float = 0.0        # scheduled P&I, excl. escrow and extra
    total_interest: float = 0.0
    total_paid: float = 0.0             # principal + interest, excl. escrow
    payoff_date: Optional[date] = None
    payoff_months: int = 0
    truncated: bool = False             # hit max_periods without clearing
    negative_amortization: bool = False  # payment never covered the interest


def _rate_for_period(
    period: int,
    base_rate: Any,
    rate_schedule: Optional[Sequence[Tuple[int, Any]]],
) -> Any:
    """Rate in effect for a 1-based period.

    ``rate_schedule`` is ``[(through_period, annual_rate_pct), ...]`` — the
    first entry whose ``through_period`` is >= the period wins. This models
    promo/deferred-interest windows and ARM steps declaratively, replacing
    the ad-hoc promo bookkeeping the payoff router grew.
    """
    if not rate_schedule:
        return base_rate
    for through_period, rate in rate_schedule:
        if period <= through_period:
            return rate
    return base_rate


def build_schedule(
    *,
    principal: Any,
    annual_rate_pct: Any,
    term_months: int,
    start_date: date,
    payment: Any = None,
    extra_monthly: Any = 0.0,
    one_time_extras: Optional[Dict[int, Any]] = None,
    escrow_monthly: Any = 0.0,
    interest_only_months: int = 0,
    rate_schedule: Optional[Sequence[Tuple[int, Any]]] = None,
    max_periods: int = MAX_PERIODS,
) -> AmortizationResult:
    """Build a full payment-by-payment schedule.

    ``payment`` defaults to the closed-form level payment for the base rate
    and term. ``escrow_monthly`` is carried on each row for display but is
    NEVER part of the amortization math — taxes and insurance don't pay down
    principal, and property economics already counts them as operating
    expenses, so folding them in here would double-count them.

    ``one_time_extras`` maps 1-based period -> extra principal for that
    period only (a bonus, a tax refund).

    Guards against non-amortizing loans: if the payment doesn't exceed the
    first period's interest and there's no extra, returns immediately with
    ``negative_amortization=True`` rather than iterating 600 times to a
    meaningless total.
    """
    p = _dec(principal)
    term = int(term_months)
    if term <= 0:
        raise ValueError("term_months must be positive")
    if p <= 0:
        return AmortizationResult(
            monthly_payment=0.0, payoff_date=start_date, payoff_months=0
        )

    scheduled = _dec(payment) if payment is not None else pmt(
        principal, annual_rate_pct, term_months
    )
    extra_each = _dec(extra_monthly)
    escrow = _money(_dec(escrow_monthly))
    extras = {int(k): _dec(v) for k, v in (one_time_extras or {}).items()}
    io_months = int(interest_only_months)

    first_rate = _rate_for_period(1, annual_rate_pct, rate_schedule)
    first_interest = _money(p * monthly_rate(first_rate))
    if io_months <= 0 and scheduled + extra_each + extras.get(1, Decimal("0")) <= first_interest:
        return AmortizationResult(
            monthly_payment=_f(scheduled),
            negative_amortization=True,
            truncated=True,
            payoff_date=None,
            payoff_months=0,
        )

    balance = _money(p)
    cum_interest = Decimal("0")
    cum_principal = Decimal("0")
    rows: List[AmortizationPeriod] = []
    period = 0

    while balance > 0 and period < max_periods:
        period += 1
        rate = _rate_for_period(period, annual_rate_pct, rate_schedule)
        interest = _money(balance * monthly_rate(rate))

        if period <= io_months:
            # Interest-only: the payment covers interest, principal is untouched.
            principal_portion = Decimal("0")
            extra_now = Decimal("0")
        else:
            principal_portion = min(scheduled - interest, balance)
            if principal_portion < 0:
                principal_portion = Decimal("0")
            remaining_after = balance - principal_portion
            extra_now = min(extra_each + extras.get(period, Decimal("0")), remaining_after)
            if extra_now < 0:
                extra_now = Decimal("0")

            # Final-payment true-up. The level payment is quantized to cents,
            # so after `term` periods a few dollars of principal are always
            # left over — without this the schedule sprouts a stub 361st row
            # for $3.41 and every "payoff in N months" number is off by one.
            # Real lenders adjust the last payment instead, so we do too.
            # Guarded to a residual within one payment so a genuinely
            # underfunded loan still runs on and truncates honestly.
            residual = balance - principal_portion - extra_now
            if period >= term and Decimal("0") < residual <= scheduled:
                principal_portion = balance - extra_now

        principal_portion = _money(principal_portion)
        extra_now = _money(extra_now)
        balance = _money(balance - principal_portion - extra_now)
        cum_interest = _money(cum_interest + interest)
        cum_principal = _money(cum_principal + principal_portion + extra_now)

        rows.append(AmortizationPeriod(
            period=period,
            date=payoff_date(start_date, period - 1),
            payment=_f(_money(interest + principal_portion + extra_now)),
            principal=_f(principal_portion),
            interest=_f(interest),
            extra=_f(extra_now),
            escrow=_f(escrow),
            balance=_f(balance),
            cumulative_interest=_f(cum_interest),
            cumulative_principal=_f(cum_principal),
        ))

    truncated = balance > 0
    return AmortizationResult(
        periods=rows,
        monthly_payment=_f(scheduled),
        total_interest=_f(cum_interest),
        total_paid=_f(_money(cum_interest + cum_principal)),
        payoff_date=None if truncated else payoff_date(start_date, period),
        payoff_months=period,
        truncated=truncated,
        negative_amortization=False,
    )


def compare_extra_payment(
    *,
    principal: Any,
    annual_rate_pct: Any,
    term_months: int,
    start_date: date,
    extra_monthly: Any,
    payment: Any = None,
    escrow_monthly: Any = 0.0,
    rate_schedule: Optional[Sequence[Tuple[int, Any]]] = None,
    max_periods: int = MAX_PERIODS,
) -> Dict[str, Any]:
    """What does paying ``extra_monthly`` more each month actually buy?

    Runs the schedule twice — baseline and accelerated — and reports the
    difference. This is the payload behind "+$200/mo pays it off 4 years
    early and saves $38,000", which is the number that changes behavior.
    """
    common = dict(
        principal=principal,
        annual_rate_pct=annual_rate_pct,
        term_months=term_months,
        start_date=start_date,
        payment=payment,
        escrow_monthly=escrow_monthly,
        rate_schedule=rate_schedule,
        max_periods=max_periods,
    )
    baseline = build_schedule(extra_monthly=0.0, **common)
    accelerated = build_schedule(extra_monthly=extra_monthly, **common)

    def _summary(result: AmortizationResult) -> Dict[str, Any]:
        return {
            "monthly_payment": result.monthly_payment,
            "payoff_months": result.payoff_months,
            "payoff_date": result.payoff_date.isoformat() if result.payoff_date else None,
            "total_interest": result.total_interest,
            "total_paid": result.total_paid,
            "truncated": result.truncated,
            "negative_amortization": result.negative_amortization,
        }

    return {
        "baseline": _summary(baseline),
        "accelerated": _summary(accelerated),
        "extra_monthly": _f(_money(_dec(extra_monthly))),
        "interest_saved": _f(_money(
            _dec(baseline.total_interest) - _dec(accelerated.total_interest)
        )),
        "months_saved": baseline.payoff_months - accelerated.payoff_months,
    }


# ---------------------------------------------------------------------------
# Multi-debt payoff strategy simulation
# ---------------------------------------------------------------------------
#
# A different problem from build_schedule. That one amortizes ONE loan in
# isolation; this one models MANY debts competing for a shared pool of money,
# where the order you attack them in changes the outcome and a retired debt's
# freed-up minimum cascades into the next.
#
# Deliberately float math, not Decimal, unlike the rest of this module. This
# is a comparative planning tool — "avalanche beats snowball by $400" — not a
# statement reconciliation, so sub-cent precision buys nothing, and the output
# is pinned by tests_unit/test_payoff_plan_characterization.py. Switching it
# to Decimal would move every pinned number for no user-visible gain.

@dataclass(frozen=True)
class DebtInput:
    """One debt in a payoff plan.

    A plain dataclass rather than the Pydantic ``PayoffAccount`` so this
    module keeps no dependency on ``models`` (and therefore none on FastAPI).
    The router converts at its boundary.
    """
    name: str
    balance: float
    apr: float
    min_payment: float
    promo_apr: Optional[float] = None
    promo_expires: Optional[str] = None      # ISO YYYY-MM-DD


def _promo_window_months(debt: DebtInput, today: date) -> Optional[int]:
    """Whole months from today until this debt's promo rate expires.

    ``None`` when the debt has no promo window or the stored date is
    unparseable. Note the window is applied as ``period <= window``, so a
    promo expiring N months out charges the promo rate for N periods.
    """
    if debt.promo_apr is None or not debt.promo_expires:
        return None
    try:
        expires = date.fromisoformat(debt.promo_expires)
    except ValueError:
        return None
    return max(0, (expires.year - today.year) * 12 + (expires.month - today.month))


def order_debts(debts: Sequence[DebtInput], strategy: str) -> List[DebtInput]:
    """Attack order. Avalanche = highest APR first (least total interest);
    anything else = snowball, lowest balance first (fastest first win)."""
    if strategy == "avalanche":
        return sorted(debts, key=lambda d: d.apr, reverse=True)
    return sorted(debts, key=lambda d: d.balance)


def simulate_payoff_plan(
    debts: Sequence[DebtInput],
    *,
    extra_monthly: float = 0.0,
    strategy: str = "avalanche",
    as_of: Optional[date] = None,
    max_periods: int = MAX_PERIODS,
) -> Dict[str, Any]:
    """Month-by-month multi-debt payoff simulation.

    Each period: accrue interest and apply every debt's minimum, then throw
    the extra payment plus every freed-up minimum at the highest-priority
    surviving debt.

    Runs twice — once with the extra, once without — so
    ``interest_saved_vs_minimums`` reflects what the extra payment actually
    bought.
    """
    today = as_of or date.today()

    def _run(extra: float) -> Tuple[List[Dict[str, Any]], int]:
        ordered = order_debts(debts, strategy)
        count = len(ordered)
        balances = [d.balance for d in ordered]
        interest_paid = [0.0] * count
        payoff_months = [0] * count
        promo_windows = [_promo_window_months(d, today) for d in ordered]
        month = 0

        while any(b > 0 for b in balances) and month < max_periods:
            month += 1

            # Freed-up minimums cascade. Once a debt is retired its minimum
            # payment doesn't vanish from the budget — it rolls into whatever
            # you're attacking next. That snowballing is the entire point of
            # both strategies; without it the ordering changes nothing.
            rollover = sum(
                d.min_payment for i, d in enumerate(ordered) if balances[i] <= 0
            )

            for i, debt in enumerate(ordered):
                if balances[i] <= 0:
                    continue
                in_promo = promo_windows[i] is not None and month <= promo_windows[i]
                rate = debt.promo_apr if in_promo else debt.apr
                interest = balances[i] * (rate / 100.0 / 12.0)
                interest_paid[i] += interest
                balances[i] += interest
                balances[i] = max(0.0, balances[i] - debt.min_payment)
                if balances[i] <= 0:
                    payoff_months[i] = payoff_months[i] or month

            # Extra + rollover go to the first surviving debt in attack order.
            # Any surplus beyond what clears it spills to the next, so a large
            # extra payment isn't wasted in the month a debt is retired.
            available = extra + rollover
            for i in range(count):
                if available <= 0:
                    break
                if balances[i] <= 0:
                    continue
                applied = min(available, balances[i])
                balances[i] -= applied
                available -= applied
                if balances[i] <= 0:
                    payoff_months[i] = payoff_months[i] or month

        # Anything still outstanding hit the cap rather than being repaid.
        for i in range(count):
            if payoff_months[i] == 0 and balances[i] > 0:
                payoff_months[i] = max_periods

        rows: List[Dict[str, Any]] = []
        for i, debt in enumerate(ordered):
            months = payoff_months[i]
            rows.append({
                "name": debt.name,
                "payoff_months": months,
                "total_interest": round(interest_paid[i], 2),
                "payoff_date": payoff_date(today.replace(day=1), months).strftime("%Y-%m"),
                "promo_expired_before_payoff": (
                    promo_windows[i] is not None and months > promo_windows[i]
                ),
            })
        return rows, (max(payoff_months) if payoff_months else 0)

    with_extra, grand_months = _run(extra_monthly)
    baseline, _ = _run(0.0)

    grand_total_interest = round(sum(r["total_interest"] for r in with_extra), 2)
    baseline_total = round(sum(r["total_interest"] for r in baseline), 2)

    return {
        "accounts": with_extra,
        "grand_total_interest": grand_total_interest,
        "grand_total_months": grand_months,
        "interest_saved_vs_minimums": round(baseline_total - grand_total_interest, 2),
        "strategy": strategy,
    }
