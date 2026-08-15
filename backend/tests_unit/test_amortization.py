"""Tests for the amortization engine.

The headline assertions are the externally-verifiable ones: a $300k /
30-year / 6.5% mortgage has a $1,896.20 payment, and the schedule's own
interest column must sum to the reported total with the final balance
landing on exactly zero. If those three hold, the engine reconciles with a
real servicer statement.
"""
from datetime import date
from decimal import Decimal

import pytest

import amortization as amort


class TestPmt:
    def test_known_thirty_year_mortgage(self):
        """$300,000 at 6.5% over 360 months == $1,896.20/mo."""
        assert amort.pmt(300000, 6.5, 360) == Decimal("1896.20")

    def test_known_fifteen_year_mortgage(self):
        """$250,000 at 5.25% over 180 months == $2,009.69/mo."""
        assert amort.pmt(250000, 5.25, 180) == Decimal("2009.69")

    def test_known_auto_loan(self):
        """$28,000 at 4.9% over 60 months == $527.11/mo."""
        assert amort.pmt(28000, 4.9, 60) == Decimal("527.11")

    def test_zero_interest_divides_evenly(self):
        assert amort.pmt(1200, 0, 12) == Decimal("100.00")

    def test_zero_principal_is_zero_payment(self):
        assert amort.pmt(0, 6.5, 360) == Decimal("0.00")

    def test_non_positive_term_rejected(self):
        with pytest.raises(ValueError):
            amort.pmt(1000, 5.0, 0)

    def test_float_input_does_not_leak_binary_noise(self):
        """0.1-style floats must not poison the result via Decimal(float)."""
        assert amort.pmt(100000.0, 3.1, 360) == amort.pmt("100000", "3.1", 360)


class TestNper:
    def test_zero_rate(self):
        assert amort.nper(1000, 0, 100) == 10

    def test_partial_final_period_rounds_up(self):
        assert amort.nper(1050, 0, 100) == 11

    def test_matches_term_for_its_own_payment(self):
        """The level payment clears the loan in its own term.

        Allows 361: the payment is quantized to cents, so the exact-math
        answer can land a hair past the final period. ``build_schedule``
        trues that up in the last payment; ``nper`` reports it honestly.
        """
        payment = amort.pmt(300000, 6.5, 360)
        assert amort.nper(300000, 6.5, payment) in (360, 361)

    def test_payment_below_interest_returns_none(self):
        """$10,000 at 29.99% accrues ~$250/mo; a $50 payment never amortizes."""
        assert amort.nper(10000, 29.99, 50) is None

    def test_payment_exactly_equal_to_interest_returns_none(self):
        interest = 10000 * 0.2999 / 12
        assert amort.nper(10000, 29.99, interest) is None

    def test_zero_balance_is_already_paid(self):
        assert amort.nper(0, 6.5, 500) == 0


class TestRemainingBalance:
    def test_before_any_payment_is_full_principal(self):
        assert amort.remaining_balance(300000, 6.5, 1896.20, 0) == Decimal("300000.00")

    def test_agrees_with_iterated_schedule(self):
        """Closed form and the row-by-row loop must not diverge.

        The retirement projection uses the closed form for speed; the loan
        detail page uses the schedule. They have to agree or equity numbers
        will differ between two screens.
        """
        result = amort.build_schedule(
            principal=300000, annual_rate_pct=6.5, term_months=360,
            start_date=date(2026, 1, 1),
        )
        # The iterative schedule quantizes interest to cents every period;
        # the closed form doesn't. Over 360 periods that compounds into a
        # few dollars of drift, which is expected and harmless — the two are
        # used for different things (projection speed vs. displayed rows).
        # A dollar per 100 periods is the honest bound.
        for checkpoint in (1, 12, 60, 180, 359):
            closed = amort.remaining_balance(
                300000, 6.5, result.monthly_payment, checkpoint
            )
            iterated = Decimal(str(result.periods[checkpoint - 1].balance))
            tolerance = Decimal("0.05") + Decimal(checkpoint) / Decimal(100)
            assert abs(closed - iterated) <= tolerance, (
                f"period {checkpoint}: closed={closed} iterated={iterated}"
            )

    def test_never_returns_negative(self):
        assert amort.remaining_balance(1000, 0, 100, 50) == Decimal("0.00")

    def test_zero_rate_is_linear(self):
        assert amort.remaining_balance(1200, 0, 100, 5) == Decimal("700.00")


class TestSplitForPeriod:
    def test_first_payment_interest_matches_hand_calculation(self):
        """Month 1 interest is simply balance x rate / 12."""
        interest, principal = amort.split_for_period(
            principal=300000, annual_rate_pct=6.5, payment=1896.20, period_index=1
        )
        assert interest == pytest.approx(1625.00)         # 300000 * .065 / 12
        assert principal == pytest.approx(271.20)
        assert interest + principal == pytest.approx(1896.20)

    def test_principal_share_grows_over_the_life_of_the_loan(self):
        early_i, early_p = amort.split_for_period(
            principal=300000, annual_rate_pct=6.5, payment=1896.20, period_index=1
        )
        late_i, late_p = amort.split_for_period(
            principal=300000, annual_rate_pct=6.5, payment=1896.20, period_index=300
        )
        assert early_i > early_p     # early payments are mostly interest
        assert late_p > late_i       # late payments are mostly principal
        assert late_i < early_i

    def test_after_payoff_returns_zeros(self):
        assert amort.split_for_period(
            principal=1200, annual_rate_pct=0, payment=100, period_index=99
        ) == (0.0, 0.0)

    def test_period_index_is_one_based(self):
        with pytest.raises(ValueError):
            amort.split_for_period(
                principal=1000, annual_rate_pct=5, payment=100, period_index=0
            )


class TestBuildSchedule:
    def _mortgage(self, **overrides):
        params = dict(
            principal=300000, annual_rate_pct=6.5, term_months=360,
            start_date=date(2026, 1, 1),
        )
        params.update(overrides)
        return amort.build_schedule(**params)

    def test_runs_the_full_term(self):
        result = self._mortgage()
        assert result.payoff_months == 360
        assert len(result.periods) == 360
        assert result.truncated is False
        assert result.negative_amortization is False

    def test_final_balance_is_exactly_zero(self):
        assert self._mortgage().periods[-1].balance == 0.0

    def test_interest_column_sums_to_reported_total(self):
        result = self._mortgage()
        summed = round(sum(p.interest for p in result.periods), 2)
        assert summed == pytest.approx(result.total_interest, abs=0.01)

    def test_principal_column_sums_to_the_original_loan(self):
        result = self._mortgage()
        summed = sum(p.principal + p.extra for p in result.periods)
        assert summed == pytest.approx(300000, abs=0.01)

    def test_cumulative_columns_track_the_running_sums(self):
        result = self._mortgage()
        running = 0.0
        for period in result.periods[:24]:
            running = round(running + period.interest, 2)
            assert period.cumulative_interest == pytest.approx(running, abs=0.01)

    def test_total_paid_is_principal_plus_interest(self):
        result = self._mortgage()
        assert result.total_paid == pytest.approx(300000 + result.total_interest, abs=0.02)

    def test_first_period_dated_at_start(self):
        result = self._mortgage()
        assert result.periods[0].date == date(2026, 1, 1)
        assert result.periods[1].date == date(2026, 2, 1)

    def test_payoff_date_is_term_months_out(self):
        assert self._mortgage().payoff_date == date(2056, 1, 1)

    def test_zero_principal_short_circuits(self):
        result = self._mortgage(principal=0)
        assert result.periods == []
        assert result.payoff_months == 0

    def test_zero_interest_loan(self):
        result = amort.build_schedule(
            principal=1200, annual_rate_pct=0, term_months=12,
            start_date=date(2026, 1, 1),
        )
        assert result.payoff_months == 12
        assert result.total_interest == 0.0
        assert result.periods[-1].balance == 0.0


class TestExtraPayments:
    _COMMON = dict(
        principal=300000, annual_rate_pct=6.5, term_months=360,
        start_date=date(2026, 1, 1),
    )

    def test_extra_monthly_shortens_the_term(self):
        baseline = amort.build_schedule(**self._COMMON)
        accelerated = amort.build_schedule(extra_monthly=200, **self._COMMON)
        assert accelerated.payoff_months < baseline.payoff_months
        assert accelerated.total_interest < baseline.total_interest
        assert accelerated.periods[-1].balance == 0.0

    def test_extra_still_repays_exactly_the_principal(self):
        result = amort.build_schedule(extra_monthly=200, **self._COMMON)
        summed = sum(p.principal + p.extra for p in result.periods)
        assert summed == pytest.approx(300000, abs=0.01)

    def test_one_time_extra_applies_to_its_period_only(self):
        result = amort.build_schedule(one_time_extras={13: 10000}, **self._COMMON)
        assert result.periods[12].extra == pytest.approx(10000.0)
        assert result.periods[11].extra == 0.0
        assert result.periods[13].extra == 0.0

    def test_extra_never_overshoots_the_remaining_balance(self):
        result = amort.build_schedule(
            principal=1000, annual_rate_pct=5, term_months=12,
            start_date=date(2026, 1, 1), extra_monthly=5000,
        )
        assert result.periods[-1].balance == 0.0
        assert all(p.balance >= 0 for p in result.periods)

    def test_compare_extra_payment_reports_the_savings(self):
        comparison = amort.compare_extra_payment(extra_monthly=200, **self._COMMON)
        assert comparison["months_saved"] > 0
        assert comparison["interest_saved"] > 0
        assert comparison["baseline"]["payoff_months"] == 360
        assert (
            comparison["accelerated"]["payoff_months"]
            == 360 - comparison["months_saved"]
        )

    def test_compare_with_zero_extra_is_a_no_op(self):
        comparison = amort.compare_extra_payment(extra_monthly=0, **self._COMMON)
        assert comparison["months_saved"] == 0
        assert comparison["interest_saved"] == pytest.approx(0.0)


class TestNegativeAmortization:
    def test_payment_below_interest_is_flagged_not_iterated(self):
        """The current payoff planner reports ~$21.6bn here. Flag instead."""
        result = amort.build_schedule(
            principal=10000, annual_rate_pct=29.99, term_months=360,
            start_date=date(2026, 1, 1), payment=50,
        )
        assert result.negative_amortization is True
        assert result.truncated is True
        assert result.periods == []
        assert result.payoff_date is None

    def test_extra_payment_can_rescue_a_non_amortizing_payment(self):
        result = amort.build_schedule(
            principal=10000, annual_rate_pct=29.99, term_months=360,
            start_date=date(2026, 1, 1), payment=50, extra_monthly=500,
        )
        assert result.negative_amortization is False
        assert result.payoff_months > 0

    def test_slow_but_amortizing_loan_is_not_flagged(self):
        """A payment just above interest amortizes — slowly, but it does."""
        result = amort.build_schedule(
            principal=10000, annual_rate_pct=29.99, term_months=600,
            start_date=date(2026, 1, 1), payment=300,
        )
        assert result.negative_amortization is False
        assert result.payoff_months > 0


class TestCaps:
    def test_truncates_at_max_periods_without_clearing(self):
        result = amort.build_schedule(
            principal=500000, annual_rate_pct=10, term_months=360,
            start_date=date(2026, 1, 1), payment=4200, max_periods=24,
        )
        assert result.truncated is True
        assert result.payoff_months == 24
        assert result.payoff_date is None
        assert result.periods[-1].balance > 0

    def test_default_cap_matches_the_payoff_planner(self):
        assert amort.MAX_PERIODS == 600


class TestInterestOnly:
    def test_principal_untouched_during_the_io_window(self):
        result = amort.build_schedule(
            principal=200000, annual_rate_pct=6.0, term_months=360,
            start_date=date(2026, 1, 1), interest_only_months=24,
        )
        assert result.periods[0].principal == 0.0
        assert result.periods[23].principal == 0.0
        assert result.periods[0].balance == 200000.0
        assert result.periods[23].balance == 200000.0

    def test_amortization_resumes_after_the_io_window(self):
        result = amort.build_schedule(
            principal=200000, annual_rate_pct=6.0, term_months=360,
            start_date=date(2026, 1, 1), interest_only_months=24,
        )
        assert result.periods[24].principal > 0
        assert result.periods[24].balance < 200000.0

    def test_io_costs_more_interest_than_amortizing_from_day_one(self):
        common = dict(
            principal=200000, annual_rate_pct=6.0, term_months=360,
            start_date=date(2026, 1, 1),
        )
        assert (
            amort.build_schedule(interest_only_months=24, **common).total_interest
            > amort.build_schedule(**common).total_interest
        )


class TestRateSchedule:
    def test_promo_window_then_regular_rate(self):
        """0% for 12 periods, then 26.99% — a deferred-interest card."""
        result = amort.build_schedule(
            principal=4000, annual_rate_pct=26.99, term_months=600,
            start_date=date(2026, 1, 1), payment=100,
            rate_schedule=[(12, 0.0)],
        )
        assert result.periods[0].interest == 0.0
        assert result.periods[11].interest == 0.0
        assert result.periods[12].interest > 0

    def test_longer_promo_costs_less_interest(self):
        common = dict(
            principal=4000, annual_rate_pct=26.99, term_months=600,
            start_date=date(2026, 1, 1), payment=200,
        )
        short = amort.build_schedule(rate_schedule=[(3, 0.0)], **common)
        long = amort.build_schedule(rate_schedule=[(12, 0.0)], **common)
        assert long.total_interest < short.total_interest

    def test_no_schedule_uses_the_base_rate_throughout(self):
        result = amort.build_schedule(
            principal=4000, annual_rate_pct=12.0, term_months=60,
            start_date=date(2026, 1, 1),
        )
        assert result.periods[0].interest == pytest.approx(40.0)   # 4000 * .12/12


class TestEscrow:
    def test_escrow_is_carried_but_never_amortized(self):
        """Escrow must not pay down principal.

        Property economics already counts taxes and insurance as operating
        expenses; if escrow also reduced the balance here it would both
        double-count the money and overstate equity.
        """
        with_escrow = amort.build_schedule(
            principal=300000, annual_rate_pct=6.5, term_months=360,
            start_date=date(2026, 1, 1), escrow_monthly=450,
        )
        without = amort.build_schedule(
            principal=300000, annual_rate_pct=6.5, term_months=360,
            start_date=date(2026, 1, 1),
        )
        assert with_escrow.periods[0].escrow == 450.0
        assert with_escrow.payoff_months == without.payoff_months
        assert with_escrow.total_interest == without.total_interest
        assert with_escrow.periods[0].balance == without.periods[0].balance

    def test_escrow_excluded_from_the_payment_column(self):
        result = amort.build_schedule(
            principal=300000, annual_rate_pct=6.5, term_months=360,
            start_date=date(2026, 1, 1), escrow_monthly=450,
        )
        first = result.periods[0]
        assert first.payment == pytest.approx(first.principal + first.interest)


class TestDateHelpers:
    def test_payoff_date_rolls_the_year(self):
        assert amort.payoff_date(date(2026, 11, 1), 3) == date(2027, 2, 1)

    def test_payoff_date_zero_offset(self):
        assert amort.payoff_date(date(2026, 5, 1), 0) == date(2026, 5, 1)

    def test_current_period_index_is_one_based(self):
        assert amort.current_period_index(date(2026, 1, 1), date(2026, 1, 15)) == 1
        assert amort.current_period_index(date(2026, 1, 1), date(2026, 2, 1)) == 2

    def test_current_period_index_before_first_payment_is_zero(self):
        assert amort.current_period_index(date(2026, 6, 1), date(2026, 1, 1)) == 0

    def test_current_period_index_spans_years(self):
        assert amort.current_period_index(date(2020, 3, 1), date(2026, 3, 1)) == 73


class TestPurity:
    def test_module_does_not_import_application_state(self):
        """Guards the design rule in the module docstring.

        amortization.py must stay callable from the retirement projection
        and from tests without any store, database, or config present.
        """
        import inspect
        # Inspect real import statements only — the module docstring names
        # the rule it is following, which would otherwise match.
        code_lines = [
            line.strip() for line in inspect.getsource(amort).splitlines()
            if line.startswith(("import ", "from "))
        ]
        assert not [
            line for line in code_lines
            if line.startswith(("import state", "from state"))
        ], code_lines
