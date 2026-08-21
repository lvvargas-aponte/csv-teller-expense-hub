"""Retirement projection.

Two behaviours carry the most weight. A mortgage retiring must raise that
property's net cash flow in the right year — that step change is the whole
buy-and-hold thesis. And "feasible" must mean sustained, not a single
crossing that later reverses when inflation outruns the payoff; reporting
the latter would be a lie with a number attached.
"""
from datetime import date

import pytest

import retirement
from retirement import (
    LoanProjection, PropertyProjection, RetirementInputs,
    build_sensitivity, project_retirement,
)

AS_OF = date(2026, 8, 15)


def _assumptions(**overrides):
    base = {
        **retirement.DEFAULT_ASSUMPTIONS,
        "current_age": 40,
        "retirement_spending_monthly": 5000,
        "horizon_years": 40,
        "social_security_monthly": 0,
    }
    base.update(overrides)
    return base


def _inputs(**overrides):
    params = {
        "assumptions": _assumptions(),
        "investment_balance": 0.0,
        "properties": [],
        "annual_spending_now": 60000.0,
    }
    params.update(overrides)
    return RetirementInputs(**params)


def _mortgage(years_in=5, term_months=360, payment=1500.0, principal=250000.0):
    return LoanProjection(
        name="Mortgage", principal=principal, rate_pct=6.0,
        term_months=term_months, payment=payment,
        months_elapsed=years_in * 12,
    )


class TestLoanProjection:
    def test_balance_falls_over_time(self):
        loan = _mortgage()
        assert loan.balance_after_years(10) < loan.balance_after_years(0)

    def test_balance_is_zero_once_the_term_ends(self):
        loan = _mortgage(years_in=5, term_months=360)
        assert loan.balance_after_years(25) == 0.0

    def test_is_retired_after_the_term(self):
        loan = _mortgage(years_in=5, term_months=360)
        assert loan.is_retired_after_years(24) is False
        assert loan.is_retired_after_years(25) is True

    def test_years_until_retired(self):
        assert _mortgage(years_in=5, term_months=360).years_until_retired() == 25

    def test_an_already_finished_loan_reports_zero(self):
        loan = _mortgage(years_in=40, term_months=360)
        assert loan.years_until_retired() == 0
        assert loan.balance_after_years(0) == 0.0


class TestMortgagePayoffStep:
    """The mechanic the whole strategy rests on."""

    def _with_property(self):
        prop = PropertyProjection(
            name="Maple St", value=400000, monthly_noi=2000,
            loans=[_mortgage(years_in=25, term_months=360, payment=1500)],
        )
        return _inputs(properties=[prop])

    def test_debt_service_stops_the_year_the_mortgage_ends(self):
        rows = project_retirement(self._with_property(), AS_OF)["rows"]
        # 25 years in on a 30-year loan: it retires in year 5.
        assert rows[4]["debt_service"] > 0
        assert rows[5]["debt_service"] == 0.0

    def test_rental_net_jumps_when_the_mortgage_retires(self):
        rows = project_retirement(self._with_property(), AS_OF)["rows"]
        before, after = rows[4]["rental_net"], rows[5]["rental_net"]
        assert after > before
        # The jump is roughly the annual payment, after rental tax.
        assert after - before == pytest.approx(1500 * 12 * 0.8, rel=0.15)

    def test_the_payoff_is_reported_as_a_milestone(self):
        result = project_retirement(self._with_property(), AS_OF)
        assert any(
            "Maple St: Mortgage" in m["mortgages_retired"]
            for m in result["milestones"]
        )

    def test_paying_a_mortgage_off_sooner_brings_retirement_forward(self):
        """Tenants retiring the debt earlier moves the date earlier.

        Debt service is set heavy enough that rent growth alone can't close
        the gap for years — otherwise both cases retire on the same date for
        reasons that have nothing to do with the mortgage, and the test
        passes while proving nothing.
        """
        assumptions = _assumptions(retirement_spending_monthly=3000)

        def _year_for(years_in):
            prop = PropertyProjection(
                name="Maple St", value=400000, monthly_noi=5000,
                loans=[_mortgage(years_in=years_in, term_months=360, payment=2500)],
            )
            return project_retirement(
                _inputs(properties=[prop], assumptions=assumptions), AS_OF
            )["earliest_retirement_year"]

        early = _year_for(25)   # mortgage retires in 5 years
        late = _year_for(5)     # mortgage retires in 25 years

        assert early is not None
        assert late is None or early < late


class TestSustainedFeasibility:
    def test_a_single_crossing_that_reverses_is_not_a_retirement_date(self):
        """Inflation can outrun a fixed income stream. A year that works and
        then stops working is not the answer."""
        # Rental income that never grows, against spending that inflates:
        # early years clear the bar, later ones don't.
        # $7,500/mo NOI nets $72,000 after tax, against $66,000 of spending —
        # comfortable today. With rents flat and 6% inflation, it isn't for long.
        prop = PropertyProjection(
            name="Flat", value=100000, monthly_noi=7500, loans=[],
            rent_growth_pct=0.0,
        )
        result = project_retirement(
            _inputs(
                properties=[prop],
                assumptions=_assumptions(
                    retirement_spending_monthly=5500, inflation_pct=6.0,
                    horizon_years=30,
                ),
            ),
            AS_OF,
        )
        rows = result["rows"]
        assert rows[0]["feasible"] is True      # works at first
        assert rows[-1]["feasible"] is False    # and stops working
        assert result["feasible"] is False      # so: not feasible

    def test_feasible_when_it_holds_through_the_horizon(self):
        prop = PropertyProjection(
            name="Strong", value=500000, monthly_noi=9000, loans=[],
        )
        result = project_retirement(_inputs(properties=[prop]), AS_OF)
        assert result["feasible"] is True
        assert result["earliest_retirement_year"] is not None
        assert all(r["feasible"] for r in result["rows"][result["years_away"]:])

    def test_retirement_age_matches_the_year(self):
        prop = PropertyProjection(
            name="Strong", value=500000, monthly_noi=9000, loans=[],
        )
        result = project_retirement(_inputs(properties=[prop]), AS_OF)
        assert result["earliest_retirement_age"] == 40 + result["years_away"]


class TestInvestments:
    def test_balance_compounds(self):
        result = project_retirement(
            _inputs(investment_balance=100000), AS_OF
        )
        assert result["rows"][10]["investment_balance"] > 100000

    def test_contributions_increase_the_balance(self):
        without = project_retirement(
            _inputs(investment_balance=100000), AS_OF
        )["rows"][10]["investment_balance"]
        with_contrib = project_retirement(
            _inputs(
                investment_balance=100000,
                assumptions=_assumptions(monthly_contribution=1000),
            ),
            AS_OF,
        )["rows"][10]["investment_balance"]
        assert with_contrib > without

    def test_withdrawal_capacity_is_the_swr_net_of_tax(self):
        result = project_retirement(_inputs(investment_balance=1000000), AS_OF)
        row = result["rows"][0]
        # 4% of $1m, less 15% tax.
        assert row["withdrawal_capacity"] == pytest.approx(1000000 * 0.04 * 0.85)


class TestSpendingAndIncome:
    def test_spending_inflates(self):
        rows = project_retirement(_inputs(), AS_OF)["rows"]
        assert rows[10]["spending_need"] > rows[0]["spending_need"]

    def test_explicit_monthly_spending_overrides_trailing_actuals(self):
        result = project_retirement(
            _inputs(
                annual_spending_now=999999,
                assumptions=_assumptions(retirement_spending_monthly=5000),
            ),
            AS_OF,
        )
        assert result["rows"][0]["spending_need"] == pytest.approx(60000.0)

    def test_trailing_spending_is_used_when_no_target_is_set(self):
        result = project_retirement(
            _inputs(
                annual_spending_now=72000,
                assumptions=_assumptions(retirement_spending_monthly=None),
            ),
            AS_OF,
        )
        assert result["rows"][0]["spending_need"] == pytest.approx(72000.0)

    def test_social_security_starts_at_its_age_not_before(self):
        result = project_retirement(
            _inputs(assumptions=_assumptions(
                social_security_monthly=2000, social_security_start_age=67,
            )),
            AS_OF,
        )
        rows = result["rows"]
        assert rows[26]["social_security"] == 0.0    # age 66
        assert rows[27]["social_security"] > 0       # age 67

    def test_rental_income_is_taxed(self):
        prop = PropertyProjection(name="P", value=100000, monthly_noi=1000, loans=[])
        row = project_retirement(_inputs(properties=[prop]), AS_OF)["rows"][0]
        # 20% effective rate by default.
        assert row["rental_net"] == pytest.approx(12000 * 0.8)

    def test_coverage_breakdown_attributes_the_income(self):
        prop = PropertyProjection(name="P", value=100000, monthly_noi=3000, loans=[])
        row = project_retirement(
            _inputs(properties=[prop], investment_balance=500000), AS_OF
        )["rows"][0]
        assert row["coverage"]["rental_pct"] > 0
        assert row["coverage"]["withdrawals_pct"] > 0


class TestInfeasible:
    def test_reports_the_contribution_that_would_fix_it(self):
        result = project_retirement(
            _inputs(assumptions=_assumptions(retirement_spending_monthly=12000)),
            AS_OF,
        )
        assert result["feasible"] is False
        assert result["required_monthly_contribution"] > 0

    def test_that_contribution_actually_makes_it_feasible(self):
        base = _inputs(assumptions=_assumptions(retirement_spending_monthly=12000))
        required = project_retirement(base, AS_OF)["required_monthly_contribution"]

        fixed = project_retirement(
            _inputs(assumptions=_assumptions(
                retirement_spending_monthly=12000,
                monthly_contribution=required * 1.01,
            )),
            AS_OF,
        )
        assert fixed["feasible"] is True

    def test_an_unreachable_target_returns_none_rather_than_the_ceiling(self):
        result = project_retirement(
            _inputs(assumptions=_assumptions(
                retirement_spending_monthly=5_000_000, horizon_years=5,
            )),
            AS_OF,
        )
        assert result["feasible"] is False
        assert result["required_monthly_contribution"] is None

    def test_the_solver_does_not_recurse(self):
        """The solver runs projections internally; those must not re-enter it."""
        result = project_retirement(
            _inputs(assumptions=_assumptions(retirement_spending_monthly=12000)),
            AS_OF,
            solve_shortfall=False,
        )
        assert "required_monthly_contribution" not in result


class TestGoal:
    """The target number, and the one property that matters: it is the
    feasibility test rearranged, so it can never contradict the date."""

    def test_target_is_spending_over_the_after_tax_withdrawal_rate(self):
        goal = project_retirement(_inputs(), AS_OF)["goal"]
        # $60k at 4% less 15% tax = 3.4% effective.
        assert goal["target"] == pytest.approx(60000 / 0.034, rel=1e-6)
        assert goal["effective_withdrawal_rate_pct"] == pytest.approx(3.4)

    def test_multiple_is_reported_against_spending(self):
        goal = project_retirement(_inputs(), AS_OF)["goal"]
        assert goal["multiple"] == pytest.approx(
            round(goal["target"] / 60000, 1)
        )

    def test_rental_profit_lowers_the_target(self):
        prop = PropertyProjection(name="P", value=100000, monthly_noi=1000, loans=[])
        with_rental = project_retirement(_inputs(properties=[prop]), AS_OF)["goal"]
        without = project_retirement(_inputs(), AS_OF)["goal"]

        assert with_rental["target"] < without["target"]
        # $12k NOI, 20% tax = $9,600 of spending the portfolio needn't fund.
        assert with_rental["rental_offset"] == pytest.approx(9600.0)
        assert with_rental["fund_from_investments"] == pytest.approx(60000 - 9600)
        # The gross figure still shows what it would take alone.
        assert with_rental["gross_target"] == pytest.approx(without["target"])

    def test_hitting_the_target_is_exactly_what_makes_year_zero_feasible(self):
        """The guarantee. Funded to the target means the projection agrees."""
        target = project_retirement(_inputs(), AS_OF)["goal"]["target"]

        assert project_retirement(
            _inputs(investment_balance=target * 0.999), AS_OF
        )["rows"][0]["feasible"] is False
        assert project_retirement(
            _inputs(investment_balance=target), AS_OF
        )["rows"][0]["feasible"] is True

    def test_progress_tracks_the_balance(self):
        target = project_retirement(_inputs(), AS_OF)["goal"]["target"]
        goal = project_retirement(
            _inputs(investment_balance=target / 4), AS_OF
        )["goal"]

        assert goal["funded_pct"] == pytest.approx(25.0, abs=0.1)
        assert goal["gap"] == pytest.approx(target * 0.75, rel=1e-3)
        assert goal["fully_funded"] is False

    def test_progress_is_capped_and_the_gap_never_goes_negative(self):
        goal = project_retirement(_inputs(investment_balance=50_000_000), AS_OF)["goal"]
        assert goal["funded_pct"] == 100.0
        assert goal["gap"] == 0.0
        assert goal["fully_funded"] is True

    def test_social_security_is_not_counted_before_it_can_be_drawn(self):
        """A target that assumes income you can't draw for 27 years isn't one."""
        goal = project_retirement(
            _inputs(assumptions=_assumptions(
                social_security_monthly=2000, social_security_start_age=67,
            )),
            AS_OF,
        )["goal"]
        assert goal["social_security_offset"] == 0.0
        assert goal["social_security_pending"] is True

    def test_social_security_lowers_the_target_once_eligible(self):
        goal = project_retirement(
            _inputs(assumptions=_assumptions(
                current_age=70, social_security_monthly=2000,
                social_security_start_age=67,
            )),
            AS_OF,
        )["goal"]
        assert goal["social_security_offset"] == pytest.approx(24000.0)
        assert goal["social_security_pending"] is False
        assert goal["fund_from_investments"] == pytest.approx(36000.0)

    def test_other_income_covering_everything_leaves_no_target(self):
        prop = PropertyProjection(name="P", value=100000, monthly_noi=9000, loans=[])
        goal = project_retirement(_inputs(properties=[prop]), AS_OF)["goal"]
        assert goal["fund_from_investments"] == 0.0
        assert goal["target"] == 0.0
        assert goal["fully_funded"] is True

    def test_no_spending_figure_means_no_goal(self):
        """Same standard the rest of the page holds to: decline, don't invent."""
        result = project_retirement(
            _inputs(annual_spending_now=0,
                    assumptions=_assumptions(retirement_spending_monthly=None)),
            AS_OF,
        )
        assert result["goal"] is None

    def test_a_zero_withdrawal_rate_declines_rather_than_dividing_by_zero(self):
        result = project_retirement(
            _inputs(assumptions=_assumptions(safe_withdrawal_rate_pct=0)), AS_OF
        )
        assert result["goal"] is None

    def test_the_goal_survives_a_degenerate_horizon(self):
        result = project_retirement(
            _inputs(assumptions=_assumptions(horizon_years=-5)), AS_OF
        )
        assert len(result["rows"]) == 1
        assert result["goal"]["target"] > 0


class TestGoalAfterPayoff:
    """While a mortgage runs most of the rent is the bank's. The headline
    target reflects that; ``after_payoff`` shows where the plan lands."""

    def _levered(self, **kw):
        # $3,000/mo NOI against a $2,000/mo payment: today the property nets
        # almost nothing, and after payoff it nets the lot.
        prop = PropertyProjection(
            name="Davie", value=400000, monthly_noi=3000,
            loans=[_mortgage(years_in=20, term_months=360, payment=2000)],
        )
        return _inputs(properties=[prop], **kw)

    def test_the_payoff_target_is_lower_than_the_levered_one(self):
        goal = project_retirement(self._levered(), AS_OF)["goal"]
        assert goal["after_payoff"]["target"] < goal["target"]

    def test_it_counts_the_whole_rent_once_the_debt_service_stops(self):
        goal = project_retirement(self._levered(), AS_OF)["goal"]
        # $36k NOI, 20% tax, no debt service at all.
        assert goal["after_payoff"]["rental_offset"] == pytest.approx(28800.0)
        assert goal["after_payoff"]["fund_from_investments"] == pytest.approx(
            60000 - 28800
        )

    def test_the_reduction_is_the_difference_between_the_two(self):
        goal = project_retirement(self._levered(), AS_OF)["goal"]
        assert goal["after_payoff"]["reduction"] == pytest.approx(
            goal["target"] - goal["after_payoff"]["target"], abs=0.01
        )

    def test_it_lands_on_the_last_payoff_not_the_first(self):
        early = PropertyProjection(
            name="Early", value=200000, monthly_noi=1500,
            loans=[_mortgage(years_in=25, term_months=360)],   # 5 years out
        )
        late = PropertyProjection(
            name="Late", value=200000, monthly_noi=1500,
            loans=[_mortgage(years_in=10, term_months=360)],   # 20 years out
        )
        goal = project_retirement(
            _inputs(properties=[early, late]), AS_OF
        )["goal"]
        assert goal["after_payoff"]["final_payoff_year"] == AS_OF.year + 20
        assert goal["after_payoff"]["final_payoff_age"] == 60

    def test_a_paid_off_portfolio_reports_no_second_target(self):
        """Nothing left to pay off, so the same number under a hopeful
        label would imply a gain that isn't coming."""
        prop = PropertyProjection(
            name="Owned", value=400000, monthly_noi=3000, loans=[],
        )
        goal = project_retirement(_inputs(properties=[prop]), AS_OF)["goal"]
        assert goal["after_payoff"] is None

    def test_no_properties_means_no_second_target(self):
        assert project_retirement(_inputs(), AS_OF)["goal"]["after_payoff"] is None

    def test_the_payoff_target_matches_feasibility_in_that_year(self):
        """The same guarantee the headline target carries, checked at the
        year the debt actually ends — rents have grown by then, so the real
        requirement is no higher than this today's-dollars figure."""
        inputs = self._levered()
        goal = project_retirement(inputs, AS_OF)["goal"]
        target = goal["after_payoff"]["target"]
        years = goal["after_payoff"]["final_payoff_year"] - AS_OF.year

        funded = project_retirement(
            RetirementInputs(
                assumptions={**inputs.assumptions, "investment_return_pct": 0.0,
                             "inflation_pct": 0.0, "rent_growth_pct": 0.0},
                investment_balance=target,
                properties=inputs.properties,
                annual_spending_now=inputs.annual_spending_now,
            ),
            AS_OF,
        )
        assert funded["rows"][years]["feasible"] is True


class TestSensitivity:
    def test_three_scenarios(self):
        assert len(build_sensitivity(_inputs(), AS_OF)) == 3

    def test_worse_assumptions_never_bring_retirement_forward(self):
        prop = PropertyProjection(
            name="Strong", value=500000, monthly_noi=9000, loans=[],
        )
        inputs = _inputs(properties=[prop], investment_balance=200000)
        base = project_retirement(inputs, AS_OF)["earliest_retirement_year"]

        for scenario in build_sensitivity(inputs, AS_OF):
            if scenario["earliest_retirement_year"] is not None and base is not None:
                assert scenario["earliest_retirement_year"] >= base

    def test_labelled_as_deterministic_not_probabilistic(self):
        result = project_retirement(_inputs(), AS_OF)
        assert result["model"] == "deterministic"
        assert result["monte_carlo"] is False


class TestGuards:
    def test_horizon_is_capped(self):
        result = project_retirement(
            _inputs(assumptions=_assumptions(horizon_years=500)), AS_OF
        )
        assert len(result["rows"]) == retirement.MAX_HORIZON_YEARS + 1

    def test_empty_inputs_warn_rather_than_pretend(self):
        result = project_retirement(
            _inputs(annual_spending_now=0,
                    assumptions=_assumptions(retirement_spending_monthly=None)),
            AS_OF,
        )
        assert result["warnings"]

    def test_no_assets_is_reported_not_projected(self):
        result = project_retirement(_inputs(), AS_OF)
        assert any("no properties" in w.lower() or "nothing to project" in w.lower()
                   for w in result["warnings"])


class TestEndpoints:
    def test_assumptions_default_before_anything_is_saved(self, client):
        body = client.get("/api/retirement/assumptions").json()
        assert body["configured"] is False
        assert body["assumptions"]["investment_return_pct"] == 7.0

    def test_saving_only_persists_supplied_fields(self, client):
        client.put("/api/retirement/assumptions", json={"current_age": 45})
        body = client.get("/api/retirement/assumptions").json()
        assert body["configured"] is True
        assert body["assumptions"]["current_age"] == 45
        # Unset fields still track the default rather than freezing it.
        assert body["assumptions"]["inflation_pct"] == 2.5

    def test_projection_runs(self, client):
        response = client.get("/api/retirement/projection")
        assert response.status_code == 200
        body = response.json()
        assert body["model"] == "deterministic"
        assert "rows" in body

    def test_projection_rejects_a_bad_date(self, client):
        assert client.get(
            "/api/retirement/projection", params={"as_of": "08/15/2026"}
        ).status_code == 422

    def test_what_if_does_not_save(self, client):
        client.put("/api/retirement/assumptions", json={"current_age": 45})
        response = client.post(
            "/api/retirement/projection", json={"current_age": 60}
        )
        assert response.json()["saved"] is False
        assert client.get(
            "/api/retirement/assumptions"
        ).json()["assumptions"]["current_age"] == 45

    def test_sensitivity_can_be_skipped(self, client):
        body = client.get(
            "/api/retirement/projection", params={"include_sensitivity": False}
        ).json()
        assert "sensitivity" not in body


class TestSpendingDerivation:
    """Guards against annualizing thin history into a fictional target."""

    def _seed_months(self, count, amount=3000):
        import state
        for i in range(count):
            month = 1 + i
            tid = f"s{i}"
            state.stored_transactions[tid] = {
                "id": tid, "transaction_id": tid,
                "date": f"2026-{month:02d}-05",
                "description": "GROCERY", "amount": amount,
                "transaction_type": "debit", "source": "simplefin",
                "category": "Groceries",
            }

    def test_one_month_does_not_become_a_yearly_target(self):
        """Annualizing a single month multiplies whatever it happened to
        contain — a bulk import, a one-off — by twelve."""
        from db import properties_repo_memory
        properties_repo_memory.install_for_tests()
        self._seed_months(1, amount=40000)

        inputs = retirement.build_retirement_inputs(as_of=AS_OF)
        assert inputs.annual_spending_now == 0.0

    def test_enough_history_derives_a_target(self):
        from db import properties_repo_memory
        properties_repo_memory.install_for_tests()
        self._seed_months(4, amount=3000)

        inputs = retirement.build_retirement_inputs(as_of=AS_OF)
        assert inputs.annual_spending_now == pytest.approx(36000.0)

    def test_thin_history_produces_an_explanatory_warning(self):
        from db import properties_repo_memory
        properties_repo_memory.install_for_tests()
        self._seed_months(1, amount=40000)

        inputs = retirement.build_retirement_inputs(as_of=AS_OF)
        result = project_retirement(inputs, AS_OF)
        assert any("transaction history" in w for w in result["warnings"])

    def test_the_current_partial_month_is_excluded(self):
        """August is half over; counting it would drag the average down."""
        import state
        from db import properties_repo_memory
        properties_repo_memory.install_for_tests()
        self._seed_months(4, amount=3000)
        state.stored_transactions["partial"] = {
            "id": "partial", "transaction_id": "partial",
            "date": "2026-08-02", "description": "GROCERY", "amount": 50,
            "transaction_type": "debit", "source": "simplefin",
            "category": "Groceries",
        }
        inputs = retirement.build_retirement_inputs(as_of=AS_OF)
        assert inputs.annual_spending_now == pytest.approx(36000.0)
