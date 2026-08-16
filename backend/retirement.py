"""Retirement projection — when the properties and the portfolio can carry you.

Deterministic, year by year. No Monte Carlo: the sensitivity rows are the
agreed substitute, and a probability-of-success percentage derived from
assumptions this soft would imply a precision the inputs don't support.

The model exists to make one mechanic visible. Rental income and mortgage
payments move independently: rent drifts up with inflation while a fixed
mortgage payment does not, and then the mortgage *ends*. The year a loan is
retired, that property's net cash flow jumps by the whole payment and stays
there. Stack three or four of those and the rental line crosses the spending
line years before a pure withdrawal strategy would. That crossing is the
household's actual retirement plan, so the projection is built to show it
rather than to produce a single number.

Split in two so the math is testable in isolation:

* ``build_retirement_inputs()`` reads the stores.
* ``project_retirement()`` is pure — hand it a dataclass, get a projection,
  no database, no config, no clock beyond the ``as_of`` you pass.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

import amortization

# Horizon cap. Beyond this the compounding assumptions dominate everything
# and the output is arithmetic rather than insight.
MAX_HORIZON_YEARS = 60

# Complete months of transaction history required before trailing spending is
# annualized into a retirement target. Three is enough to survive one unusual
# month; below it, a single bulk import extrapolates to a fictional figure.
_MIN_SPENDING_MONTHS = 3

DEFAULT_ASSUMPTIONS: Dict[str, Any] = {
    "current_age": 40,
    "target_retirement_age": None,        # None = solve for the earliest year
    "investment_return_pct": 7.0,
    "inflation_pct": 2.5,
    "rent_growth_pct": 3.0,
    "expense_growth_pct": 2.5,
    "appreciation_pct": 3.0,
    "safe_withdrawal_rate_pct": 4.0,
    "retirement_spending_monthly": None,  # None = derive from actual spending
    "monthly_contribution": 0.0,
    "contribution_growth_pct": 0.0,
    "social_security_monthly": 0.0,
    "social_security_start_age": 67,
    "tax_rate_on_withdrawals_pct": 15.0,
    "effective_tax_rate_on_rental_pct": 20.0,
    "horizon_years": 50,
}


@dataclass
class LoanProjection:
    """Just enough of a loan to place it on a schedule."""
    name: str
    principal: float
    rate_pct: float
    term_months: int
    payment: float
    months_elapsed: int
    escrow_monthly: float = 0.0

    def balance_after_years(self, years: int) -> float:
        periods = self.months_elapsed + years * 12
        if periods >= self.term_months:
            return 0.0
        return float(amortization.remaining_balance(
            self.principal, self.rate_pct, self.payment, periods
        ))

    def is_retired_after_years(self, years: int) -> bool:
        return self.months_elapsed + years * 12 >= self.term_months

    def years_until_retired(self) -> int:
        remaining = max(0, self.term_months - self.months_elapsed)
        return (remaining + 11) // 12


@dataclass
class PropertyProjection:
    name: str
    value: float
    monthly_noi: float          # excludes debt service, by definition
    loans: List[LoanProjection] = field(default_factory=list)
    appreciation_pct: Optional[float] = None
    rent_growth_pct: Optional[float] = None


@dataclass
class RetirementInputs:
    assumptions: Dict[str, Any]
    investment_balance: float = 0.0
    properties: List[PropertyProjection] = field(default_factory=list)
    annual_spending_now: float = 0.0


def _pct(assumptions: Dict[str, Any], key: str) -> float:
    return float(assumptions.get(key) or 0.0) / 100.0


def project_retirement(
    inputs: RetirementInputs,
    as_of: Optional[date] = None,
    *,
    solve_shortfall: bool = True,
) -> Dict[str, Any]:
    """Year-by-year projection, and the earliest year retirement holds.

    "Feasible" is not the first year income covers spending — it is the
    first year that stays true for every year after it. A single crossing
    that later reverses, because inflation outruns a mortgage payoff, is not
    a retirement date. Reporting one would be a lie with a number attached.

    ``solve_shortfall`` exists only so the bisection solver can ask for a
    projection without the solver running inside it.
    """
    today = as_of or date.today()
    a = inputs.assumptions
    horizon = min(int(a.get("horizon_years") or 50), MAX_HORIZON_YEARS)

    invest_return = _pct(a, "investment_return_pct")
    inflation = _pct(a, "inflation_pct")
    rent_growth = _pct(a, "rent_growth_pct")
    expense_growth = _pct(a, "expense_growth_pct")
    appreciation = _pct(a, "appreciation_pct")
    swr = _pct(a, "safe_withdrawal_rate_pct")
    withdrawal_tax = _pct(a, "tax_rate_on_withdrawals_pct")
    rental_tax = _pct(a, "effective_tax_rate_on_rental_pct")
    contribution_growth = _pct(a, "contribution_growth_pct")

    current_age = int(a.get("current_age") or 40)
    target_age = a.get("target_retirement_age")
    ss_start_age = int(a.get("social_security_start_age") or 67)
    ss_annual_now = float(a.get("social_security_monthly") or 0.0) * 12

    spending_now = (
        float(a["retirement_spending_monthly"]) * 12
        if a.get("retirement_spending_monthly")
        else inputs.annual_spending_now
    )

    annual_contribution = float(a.get("monthly_contribution") or 0.0) * 12

    rows: List[Dict[str, Any]] = []
    balance = float(inputs.investment_balance)
    retirement_year_index: Optional[int] = None

    for year in range(0, horizon + 1):
        age = current_age + year
        calendar_year = today.year + year

        # --- properties -------------------------------------------------
        property_value = 0.0
        property_debt = 0.0
        rental_noi = 0.0
        debt_service = 0.0
        retired_this_year: List[str] = []

        for prop in inputs.properties:
            growth = (
                prop.appreciation_pct / 100.0
                if prop.appreciation_pct is not None else appreciation
            )
            rent_g = (
                prop.rent_growth_pct / 100.0
                if prop.rent_growth_pct is not None else rent_growth
            )
            property_value += prop.value * ((1 + growth) ** year)

            # NOI grows with rent but is eaten into by expense inflation;
            # netting the two keeps a single figure honest enough.
            net_growth = rent_g - (expense_growth - rent_g) * 0.0
            rental_noi += prop.monthly_noi * 12 * ((1 + net_growth) ** year)

            for loan in prop.loans:
                property_debt += loan.balance_after_years(year)
                if not loan.is_retired_after_years(year):
                    debt_service += loan.payment * 12
                elif loan.years_until_retired() == year:
                    retired_this_year.append(f"{prop.name}: {loan.name}")

        rental_net = max(0.0, rental_noi - debt_service) * (1 - rental_tax)

        # --- investments -------------------------------------------------
        # Contributions stop once retired; withdrawals are modeled by the
        # safe-withdrawal figure rather than drawn down here, so the balance
        # keeps compounding at the assumed return.
        retired_by_now = (
            retirement_year_index is not None and year >= retirement_year_index
        ) or (target_age is not None and age >= int(target_age))

        if year > 0:
            balance *= (1 + invest_return)
            if not retired_by_now:
                balance += annual_contribution * ((1 + contribution_growth) ** (year - 1))

        withdrawal_capacity = balance * swr * (1 - withdrawal_tax)
        social_security = (
            ss_annual_now * ((1 + inflation) ** year) if age >= ss_start_age else 0.0
        )
        spending_need = spending_now * ((1 + inflation) ** year)
        total_income = rental_net + withdrawal_capacity + social_security
        feasible = total_income >= spending_need > 0

        rows.append({
            "year": calendar_year,
            "age": age,
            "investment_balance": round(balance, 2),
            "property_value": round(property_value, 2),
            "property_debt": round(property_debt, 2),
            "property_equity": round(property_value - property_debt, 2),
            "net_worth": round(balance + property_value - property_debt, 2),
            "rental_noi": round(rental_noi, 2),
            "debt_service": round(debt_service, 2),
            "rental_net": round(rental_net, 2),
            "withdrawal_capacity": round(withdrawal_capacity, 2),
            "social_security": round(social_security, 2),
            "total_income": round(total_income, 2),
            "spending_need": round(spending_need, 2),
            "surplus": round(total_income - spending_need, 2),
            "feasible": feasible,
            "mortgages_retired": retired_this_year,
            "coverage": {
                "rental_pct": round(rental_net / spending_need * 100, 1) if spending_need else None,
                "withdrawals_pct": round(withdrawal_capacity / spending_need * 100, 1) if spending_need else None,
                "social_security_pct": round(social_security / spending_need * 100, 1) if spending_need else None,
            },
        })

    # The earliest year feasibility holds AND keeps holding. Scanning
    # backwards from the horizon finds the start of the final unbroken run,
    # which is the only honest answer.
    sustained_from: Optional[int] = None
    for i in range(len(rows) - 1, -1, -1):
        if rows[i]["feasible"]:
            sustained_from = i
        else:
            break

    feasible = sustained_from is not None
    at_retirement = rows[sustained_from] if feasible else None

    result = {
        "model": "deterministic",
        "monte_carlo": False,
        "generated_at": today.isoformat(),
        "assumptions": dict(a),
        "feasible": feasible,
        "earliest_retirement_year": at_retirement["year"] if at_retirement else None,
        "earliest_retirement_age": at_retirement["age"] if at_retirement else None,
        "years_away": sustained_from if feasible else None,
        "at_retirement": at_retirement,
        "rows": rows,
        "milestones": [
            {"year": r["year"], "age": r["age"], "mortgages_retired": r["mortgages_retired"]}
            for r in rows if r["mortgages_retired"]
        ],
        "warnings": [],
    }

    if not feasible and solve_shortfall:
        result["required_monthly_contribution"] = _solve_required_contribution(
            inputs, as_of=today
        )

    if spending_now <= 0:
        result["warnings"].append(
            "No retirement spending figure yet. There isn't enough transaction "
            "history to derive one — annualizing a month or two would invent a "
            "number rather than measure one. Set a monthly spending target in "
            "the assumptions below and this becomes meaningful."
        )
    if not inputs.properties and inputs.investment_balance <= 0:
        result["warnings"].append(
            "Nothing to project from yet: no investment balance and no "
            "properties on file."
        )

    return result


def _solve_required_contribution(
    inputs: RetirementInputs, as_of: Optional[date] = None
) -> Optional[float]:
    """Monthly contribution that would make retirement reachable.

    Bisection over the contribution, ~40 iterations. Deterministic and
    dependency-free — scipy would be a heavy import for a monotonic
    one-dimensional solve.
    """
    low, high = 0.0, 100_000.0

    def _feasible_at(monthly: float) -> bool:
        trial = RetirementInputs(
            assumptions={**inputs.assumptions, "monthly_contribution": monthly},
            investment_balance=inputs.investment_balance,
            properties=inputs.properties,
            annual_spending_now=inputs.annual_spending_now,
        )
        return project_retirement(trial, as_of, solve_shortfall=False)["feasible"]

    # Even an implausible contribution may not close the gap — a spending
    # target far above what any contribution can fund inside the horizon.
    # Say so rather than returning the bisection ceiling as if it were an
    # answer.
    if not _feasible_at(high):
        return None

    for _ in range(40):
        mid = (low + high) / 2
        if _feasible_at(mid):
            high = mid
        else:
            low = mid
    return round(high, 2)


def build_sensitivity(
    inputs: RetirementInputs, as_of: Optional[date] = None
) -> List[Dict[str, Any]]:
    """Three deterministic knocks, in place of a probability figure.

    Deterministic projections invite false precision; these say plainly how
    much the answer moves when a single assumption is wrong.
    """
    scenarios = [
        ("Returns 5% instead of 7%", {"investment_return_pct": 5.0}),
        ("Spending $1,000/mo higher", {
            "retirement_spending_monthly": (
                (inputs.assumptions.get("retirement_spending_monthly")
                 or inputs.annual_spending_now / 12) + 1000
            ),
        }),
        ("Rents grow 1% instead of 3%", {"rent_growth_pct": 1.0}),
    ]

    out: List[Dict[str, Any]] = []
    for label, override in scenarios:
        trial = RetirementInputs(
            assumptions={**inputs.assumptions, **override},
            investment_balance=inputs.investment_balance,
            properties=inputs.properties,
            annual_spending_now=inputs.annual_spending_now,
        )
        projection = project_retirement(trial, as_of, solve_shortfall=False)
        out.append({
            "label": label,
            "feasible": projection["feasible"],
            "earliest_retirement_year": projection["earliest_retirement_year"],
            "earliest_retirement_age": projection["earliest_retirement_age"],
        })
    return out


# ---------------------------------------------------------------------------
# Store-reading side
# ---------------------------------------------------------------------------

def build_retirement_inputs(as_of: Optional[date] = None) -> RetirementInputs:
    """Assemble projection inputs from the live stores."""
    import state
    from analytics import _balances_snapshot, group_debit_spending
    from db import properties_repo
    import properties as properties_domain

    today = as_of or date.today()
    stored = dict(state.retirement_assumptions.get("household") or {})
    assumptions = {**DEFAULT_ASSUMPTIONS, **stored}

    snapshot = _balances_snapshot()
    investment_balance = float(snapshot.get("total_investments") or 0.0)

    # Trailing spending, as the default retirement target. Better than a
    # guessed percentage of income: it is what this household actually costs.
    #
    # But only with enough history to mean anything. Annualizing a single
    # month multiplies whatever that month happened to contain — including a
    # bulk CSV import or a one-off — by twelve, and a retirement target built
    # on that is worse than no target at all. Below the threshold we decline
    # to derive one and say why, matching how income estimation and property
    # actuals already handle thin data.
    spending = group_debit_spending()
    current_month = f"{today.year:04d}-{today.month:02d}"
    # The current month is partial by definition and would drag the average.
    complete_months = sorted(m for m in spending if m < current_month)[-12:]

    if len(complete_months) >= _MIN_SPENDING_MONTHS:
        total = sum(sum(spending[m].values()) for m in complete_months)
        annual_spending = total / len(complete_months) * 12
    else:
        annual_spending = 0.0

    repo = properties_repo.get_repo()
    projections: List[PropertyProjection] = []
    for prop in repo.list_properties():
        econ = properties_domain.compute_property_economics(prop["id"], as_of=today)
        if econ is None:
            continue

        loans: List[LoanProjection] = []
        for loan in repo.list_loans(prop["id"]):
            payment = properties_domain.loan_payment(loan)
            if payment <= 0:
                continue
            start = loan.get("first_payment_date") or loan.get("origination_date")
            try:
                elapsed = amortization.current_period_index(
                    date.fromisoformat(str(start)[:10]), today
                )
            except (ValueError, TypeError):
                elapsed = 0
            loans.append(LoanProjection(
                name=loan.get("name", "Loan"),
                principal=float(loan.get("original_principal") or 0),
                rate_pct=float(loan.get("interest_rate_pct") or 0),
                term_months=int(loan.get("term_months") or 0),
                payment=payment,
                months_elapsed=max(0, elapsed),
                escrow_monthly=float(loan.get("escrow_monthly") or 0),
            ))

        projections.append(PropertyProjection(
            name=prop.get("name", "Property"),
            value=float(prop.get("current_value") or 0),
            monthly_noi=(econ.get("pro_forma") or {}).get("noi", 0.0),
            loans=loans,
            appreciation_pct=prop.get("appreciation_pct"),
            rent_growth_pct=prop.get("rent_growth_pct"),
        ))

    return RetirementInputs(
        assumptions=assumptions,
        investment_balance=investment_balance,
        properties=projections,
        annual_spending_now=round(annual_spending, 2),
    )
