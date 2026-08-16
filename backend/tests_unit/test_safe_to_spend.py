"""Safe-to-spend engine.

The load-bearing behaviour is that overspending today lowers tomorrow's
number without any carry-over bookkeeping — the pool is recomputed from
actual month-to-date spend on every call while the day count shrinks.
"""
from datetime import date

import pytest

import state
from analytics import compute_safe_to_spend
from db import properties_repo_memory


@pytest.fixture(autouse=True)
def _properties():
    """Safe-to-spend reaches into properties for rental income."""
    return properties_repo_memory.install_for_tests()


def _paycheck(tid, day, amount=4000.0):
    """A credit that income detection will recognize as recurring."""
    state.stored_transactions[tid] = {
        "id": tid, "transaction_id": tid, "date": day,
        "description": "ACME CORP DIRECT DEP", "amount": amount,
        "transaction_type": "credit", "source": "simplefin",
        "category": "Income", "account_type": "checking",
    }


def _spend(tid, day, amount, category="Dining", description="RESTAURANT"):
    state.stored_transactions[tid] = {
        "id": tid, "transaction_id": tid, "date": day,
        "description": description, "amount": amount,
        "transaction_type": "debit", "source": "simplefin",
        "category": category,
    }


def _seed_income():
    """Six months of paychecks — enough for high confidence."""
    for i, month in enumerate(range(3, 9)):
        _paycheck(f"pay{i}a", f"2026-{month:02d}-01")
        _paycheck(f"pay{i}b", f"2026-{month:02d}-15")


AUG_15 = date(2026, 8, 15)


class TestAvailability:
    def test_no_income_refuses_rather_than_guessing(self):
        _spend("s1", "2026-08-02", 50)
        result = compute_safe_to_spend(as_of=AUG_15)
        assert result["available"] is False
        assert result["reason"] == "no_income_detected"

    def test_detected_income_produces_a_number(self):
        _seed_income()
        result = compute_safe_to_spend(as_of=AUG_15)
        assert result["available"] is True
        assert result["income"]["monthly"] > 0
        assert result["daily_safe_to_spend"] >= 0


class TestPoolArithmetic:
    def test_pool_is_income_minus_commitments(self):
        _seed_income()
        result = compute_safe_to_spend(as_of=AUG_15)
        assert result["discretionary_pool"] == pytest.approx(
            result["income"]["monthly"] - result["commitments"]["total"], abs=0.01
        )

    def test_remaining_is_pool_minus_spend(self):
        _seed_income()
        _spend("s1", "2026-08-02", 300)
        result = compute_safe_to_spend(as_of=AUG_15)
        assert result["remaining_pool"] == pytest.approx(
            result["discretionary_pool"] - result["spent_so_far"], abs=0.01
        )
        assert result["spent_so_far"] == 300.0

    def test_daily_divides_remaining_by_days_left(self):
        _seed_income()
        result = compute_safe_to_spend(as_of=AUG_15)
        # August has 31 days; the 15th leaves 17 including today.
        assert result["period"]["days_remaining"] == 17
        assert result["daily_safe_to_spend"] == pytest.approx(
            result["remaining_pool"] / 17, abs=0.01
        )

    def test_weekly_is_seven_days_of_allowance(self):
        _seed_income()
        result = compute_safe_to_spend(as_of=AUG_15)
        assert result["weekly_safe_to_spend"] == pytest.approx(
            result["daily_safe_to_spend"] * 7, abs=0.01
        )

    def test_weekly_shrinks_when_fewer_than_seven_days_remain(self):
        _seed_income()
        result = compute_safe_to_spend(as_of=date(2026, 8, 29))
        assert result["period"]["days_remaining"] == 3
        assert result["weekly_safe_to_spend"] == pytest.approx(
            result["daily_safe_to_spend"] * 3, abs=0.01
        )

    def test_spending_outside_the_current_month_is_ignored(self):
        _seed_income()
        _spend("old", "2026-07-20", 900)
        assert compute_safe_to_spend(as_of=AUG_15)["spent_so_far"] == 0.0

    def test_future_dated_spending_is_ignored(self):
        _seed_income()
        _spend("future", "2026-08-28", 500)
        assert compute_safe_to_spend(as_of=AUG_15)["spent_so_far"] == 0.0


class TestOverspendRollsForward:
    """The mechanism, asserted directly."""

    def test_spending_more_today_lowers_tomorrow(self):
        _seed_income()
        restrained = compute_safe_to_spend(as_of=AUG_15)["daily_safe_to_spend"]

        _spend("splurge", "2026-08-15", 400)
        after = compute_safe_to_spend(as_of=AUG_15)["daily_safe_to_spend"]

        assert after < restrained
        # $400 spread across the 17 remaining days.
        assert restrained - after == pytest.approx(400 / 17, abs=0.05)

    def test_no_carryover_ledger_is_kept(self):
        """Recomputed from transactions each call — deleting the spend
        restores the number exactly, which a stored ledger would not."""
        _seed_income()
        before = compute_safe_to_spend(as_of=AUG_15)["daily_safe_to_spend"]
        _spend("splurge", "2026-08-15", 400)
        del state.stored_transactions["splurge"]
        assert compute_safe_to_spend(as_of=AUG_15)["daily_safe_to_spend"] == before

    def test_as_of_reproduces_an_earlier_day(self):
        _seed_income()
        _spend("s1", "2026-08-10", 200)
        yesterday = compute_safe_to_spend(as_of=date(2026, 8, 14))
        today = compute_safe_to_spend(as_of=AUG_15)
        # Same spend, one fewer day to spread it over.
        assert yesterday["period"]["days_remaining"] == 18
        assert today["period"]["days_remaining"] == 17
        assert today["daily_safe_to_spend"] > yesterday["daily_safe_to_spend"]


class TestOverBudget:
    def test_daily_clamps_to_zero_rather_than_going_negative(self):
        _seed_income()
        _spend("huge", "2026-08-02", 99999)
        result = compute_safe_to_spend(as_of=AUG_15)
        assert result["daily_safe_to_spend"] == 0.0
        assert result["over_budget"] is True
        assert result["overspend_amount"] > 0

    def test_overspend_amount_is_the_shortfall(self):
        _seed_income()
        _spend("huge", "2026-08-02", 99999)
        result = compute_safe_to_spend(as_of=AUG_15)
        assert result["overspend_amount"] == pytest.approx(
            abs(result["remaining_pool"]), abs=0.01
        )


class TestPeriodEdges:
    def test_first_of_the_month(self):
        _seed_income()
        result = compute_safe_to_spend(as_of=date(2026, 8, 1))
        assert result["period"]["days_remaining"] == 31

    def test_last_day_of_the_month_never_divides_by_zero(self):
        _seed_income()
        result = compute_safe_to_spend(as_of=date(2026, 8, 31))
        assert result["period"]["days_remaining"] == 1
        assert result["daily_safe_to_spend"] == pytest.approx(
            result["remaining_pool"], abs=0.01
        )

    def test_february_has_twenty_eight_days(self):
        _seed_income()
        result = compute_safe_to_spend(as_of=date(2026, 2, 1))
        assert result["period"]["days_total"] == 28

    def test_leap_february_has_twenty_nine(self):
        _seed_income()
        result = compute_safe_to_spend(as_of=date(2028, 2, 1))
        assert result["period"]["days_total"] == 29


class TestCommitments:
    def test_credit_card_minimums_reduce_the_pool(self):
        _seed_income()
        without = compute_safe_to_spend(as_of=AUG_15)["discretionary_pool"]

        state.account_details["card_1"] = {"minimum_payment": 250}
        after = compute_safe_to_spend(as_of=AUG_15)
        assert after["commitments"]["minimum_debt_payments"] == 250.0
        assert after["discretionary_pool"] == pytest.approx(without - 250, abs=0.01)

    def test_loan_payments_include_escrow(self):
        """Escrow really does leave the account every month, even though it
        doesn't reduce principal."""
        _seed_income()
        repo = properties_repo_memory.active()
        repo.upsert_loan({
            "id": "loan_1", "name": "Mortgage",
            "original_principal": 240000, "interest_rate_pct": 6.0,
            "term_months": 360, "origination_date": date(2020, 1, 1),
            "payment_amount": 1438.92, "escrow_monthly": 600,
        })
        result = compute_safe_to_spend(as_of=AUG_15)
        assert result["commitments"]["minimum_debt_payments"] == pytest.approx(
            2038.92, abs=0.01
        )

    def test_goal_contributions_reduce_the_pool(self):
        _seed_income()
        state.goals["goal_1"] = {
            "id": "goal_1", "name": "Emergency fund", "kind": "emergency_fund",
            "target_amount": 12000, "current_balance": 0,
            "target_date": "2027-08-01",
        }
        result = compute_safe_to_spend(as_of=AUG_15)
        assert result["commitments"]["required_goal_contributions"] > 0


class TestBillExclusion:
    def _seed_recurring_bill(self):
        for i, month in enumerate(range(3, 9)):
            _spend(f"util{i}", f"2026-{month:02d}-05", 180,
                   category="Utilities", description="CITY POWER CO")

    def test_bills_are_committed_not_discretionary(self):
        _seed_income()
        self._seed_recurring_bill()
        result = compute_safe_to_spend(as_of=AUG_15)
        assert result["commitments"]["fixed_bills"] > 0

    def test_bill_spend_is_not_double_counted_against_the_pool(self):
        """A utility bill is subtracted once as a commitment. Counting it
        again as discretionary spend would charge it twice."""
        _seed_income()
        self._seed_recurring_bill()
        result = compute_safe_to_spend(as_of=AUG_15)
        assert result["spent_so_far"] == 0.0
        assert "Utilities" in result["excluded_categories"]

    def test_discretionary_spend_still_counts(self):
        _seed_income()
        self._seed_recurring_bill()
        _spend("dinner", "2026-08-10", 75)
        assert compute_safe_to_spend(as_of=AUG_15)["spent_so_far"] == 75.0


class TestPace:
    """Pace compares spend against a straight line through the month, so the
    threshold moves with the pool rather than being a fixed dollar figure."""

    def test_spending_ahead_of_schedule_reads_over(self):
        _seed_income()
        # $8,000 pool, day 15 of 31 → roughly $3,871 expected by now.
        result = compute_safe_to_spend(as_of=AUG_15)
        expected = result["expected_spend_to_date"]

        _spend("s1", "2026-08-02", expected * 1.5)
        assert compute_safe_to_spend(as_of=AUG_15)["pace"] == "over"

    def test_spending_roughly_on_the_line_reads_on_track(self):
        _seed_income()
        expected = compute_safe_to_spend(as_of=AUG_15)["expected_spend_to_date"]

        _spend("s1", "2026-08-02", expected)
        assert compute_safe_to_spend(as_of=AUG_15)["pace"] == "on_track"

    def test_spending_nothing_reads_under(self):
        _seed_income()
        assert compute_safe_to_spend(as_of=AUG_15)["pace"] == "under"


class TestExplainability:
    def test_components_break_income_down(self):
        _seed_income()
        components = compute_safe_to_spend(as_of=AUG_15)["income"]["components"]
        assert set(components) == {"paychecks", "inbound_transfers", "rental_net"}

    def test_commitments_are_itemized(self):
        _seed_income()
        commitments = compute_safe_to_spend(as_of=AUG_15)["commitments"]
        assert commitments["total"] == pytest.approx(
            commitments["fixed_bills"]
            + commitments["minimum_debt_payments"]
            + commitments["required_goal_contributions"],
            abs=0.01,
        )

    def test_assumptions_are_stated(self):
        _seed_income()
        assumptions = compute_safe_to_spend(as_of=AUG_15)["assumptions"]
        assert assumptions["basis"] == "calendar_month"
        assert assumptions["days_remaining_includes_today"] is True

    def test_missing_budgets_produce_a_caveat(self):
        _seed_income()
        caveats = " ".join(compute_safe_to_spend(as_of=AUG_15)["caveats"])
        assert "budget" in caveats.lower()

    def test_negative_pool_produces_a_caveat(self):
        _seed_income()
        state.account_details["card_1"] = {"minimum_payment": 99999}
        caveats = " ".join(compute_safe_to_spend(as_of=AUG_15)["caveats"])
        assert "exceeds income" in caveats


class TestRentalIncome:
    def test_positive_rental_cash_flow_adds_to_income(self):
        _seed_income()
        base = compute_safe_to_spend(as_of=AUG_15)["income"]["monthly"]

        repo = properties_repo_memory.active()
        repo.upsert_property({
            "id": "prop_1", "name": "Maple St", "status": "rental",
            "monthly_rent": 3000, "vacancy_rate_pct": 0,
            "maintenance_pct_of_rent": 0, "capex_reserve_pct_of_rent": 0,
        })
        result = compute_safe_to_spend(as_of=AUG_15)
        assert result["income"]["components"]["rental_net"] > 0
        assert result["income"]["monthly"] > base

    def test_loss_making_property_does_not_reduce_income(self):
        """A property running at a loss shows up through its transactions,
        not as negative income here."""
        _seed_income()
        repo = properties_repo_memory.active()
        repo.upsert_property({
            "id": "prop_1", "name": "Money Pit", "status": "rental",
            "monthly_rent": 100, "property_tax_annual": 12000,
        })
        result = compute_safe_to_spend(as_of=AUG_15)
        assert result["income"]["components"]["rental_net"] == 0.0


class TestEndpoint:
    def test_returns_the_payload(self, client):
        _seed_income()
        response = client.get("/api/budgets/safe-to-spend")
        assert response.status_code == 200
        assert response.json()["available"] is True

    def test_accepts_an_as_of_date(self, client):
        _seed_income()
        response = client.get(
            "/api/budgets/safe-to-spend", params={"as_of": "2026-08-15"}
        )
        assert response.json()["period"]["days_remaining"] == 17

    def test_rejects_a_bad_date(self, client):
        assert client.get(
            "/api/budgets/safe-to-spend", params={"as_of": "08/15/2026"}
        ).status_code == 422

    def test_route_is_not_captured_as_a_category(self, client):
        """/budgets/safe-to-spend must not hit /budgets/{category}."""
        assert client.get("/api/budgets/safe-to-spend").status_code == 200
