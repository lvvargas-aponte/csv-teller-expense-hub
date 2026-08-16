"""Rental-property economics.

The two assertions that matter most are the ones guarding the classic
errors: NOI must exclude debt service, and escrow must not be counted both
as an operating expense and as part of debt service. Get either wrong and
cap rate, DSCR and every downstream retirement number are quietly wrong.
"""
from datetime import date

import pytest

import properties
import state
from db import properties_repo_memory


@pytest.fixture
def repo():
    return properties_repo_memory.install_for_tests()


def _property(repo, pid="prop_1", **overrides):
    row = {
        "id": pid,
        "name": "Maple St Duplex",
        "status": "rental",
        "monthly_rent": 3000,
        "other_monthly_income": 0,
        "vacancy_rate_pct": 0,
        "property_tax_annual": 6000,       # $500/mo
        "insurance_annual": 1200,          # $100/mo
        "hoa_monthly": 0,
        "utilities_monthly": 0,
        "landscaping_monthly": 0,
        "other_monthly_expense": 0,
        "mgmt_fee_pct": 0,
        "maintenance_pct_of_rent": 0,
        "capex_reserve_pct_of_rent": 0,
        "current_value": 400000,
    }
    row.update(overrides)
    return repo.upsert_property(row)


def _loan(repo, lid="loan_1", **overrides):
    row = {
        "id": lid,
        "name": "Mortgage",
        "property_id": "prop_1",
        "original_principal": 240000,
        "current_principal": 200000,
        "interest_rate_pct": 6.0,
        "term_months": 360,
        "origination_date": date(2020, 1, 1),
        "first_payment_date": date(2020, 2, 1),
        "payment_amount": 1438.92,
        "escrow_monthly": 600,             # taxes + insurance escrowed
        "lien_position": 1,
    }
    row.update(overrides)
    return repo.upsert_loan(row)


class TestProFormaTraps:
    def test_noi_excludes_debt_service(self, repo):
        """The #1 rental-math error. NOI measures the property, not the
        financing — otherwise a cash purchase and a leveraged one look the
        same and cap rate is meaningless."""
        _property(repo)
        prop = repo.get_property("prop_1")

        without_debt = properties.compute_pro_forma(prop, [])
        with_debt = properties.compute_pro_forma(prop, [_loan(repo)])

        assert without_debt["noi"] == with_debt["noi"]
        assert with_debt["debt_service"] > 0
        assert with_debt["cash_flow"] < with_debt["noi"]

    def test_escrow_is_not_double_counted(self, repo):
        """Taxes and insurance are already in operating expenses. Adding the
        escrow into debt service would charge the property twice."""
        _property(repo)
        prop = repo.get_property("prop_1")
        loan = _loan(repo, escrow_monthly=600)

        result = properties.compute_pro_forma(prop, [loan])

        # Debt service is P&I only — the $600 escrow is absent from it.
        assert result["debt_service"] == pytest.approx(1438.92)
        # And taxes+insurance appear exactly once, via the expense model.
        assert result["operating_expenses"] == pytest.approx(600.0)

    def test_escrow_amount_does_not_change_the_result(self, repo):
        _property(repo)
        prop = repo.get_property("prop_1")
        low = properties.compute_pro_forma(prop, [_loan(repo, escrow_monthly=0)])
        high = properties.compute_pro_forma(prop, [_loan(repo, escrow_monthly=900)])
        assert low["cash_flow"] == high["cash_flow"]


class TestProForma:
    def test_basic_arithmetic(self, repo):
        _property(repo)
        result = properties.compute_pro_forma(repo.get_property("prop_1"), [])

        assert result["gross_scheduled_income"] == 3000.0
        assert result["effective_gross_income"] == 3000.0
        assert result["operating_expenses"] == 600.0     # 6000/12 + 1200/12
        assert result["noi"] == 2400.0
        assert result["cash_flow"] == 2400.0

    def test_vacancy_reduces_effective_gross_income(self, repo):
        _property(repo, vacancy_rate_pct=5)
        result = properties.compute_pro_forma(repo.get_property("prop_1"), [])
        assert result["vacancy_loss"] == 150.0
        assert result["effective_gross_income"] == 2850.0

    def test_percentage_reserves_are_taken_on_rent(self, repo):
        _property(repo, maintenance_pct_of_rent=5, capex_reserve_pct_of_rent=5)
        result = properties.compute_pro_forma(repo.get_property("prop_1"), [])
        assert result["operating_expenses"] == pytest.approx(900.0)  # 600 + 300

    def test_flat_monthly_expenses_add_at_face_value(self, repo):
        """HOA, utilities and landscaping are already monthly — they go in as
        given, unlike the annual tax/insurance figures."""
        _property(repo, hoa_monthly=45, utilities_monthly=80, landscaping_monthly=120)
        result = properties.compute_pro_forma(repo.get_property("prop_1"), [])
        assert result["operating_expenses"] == pytest.approx(600.0 + 245.0)

    def test_management_fee_is_taken_on_effective_gross_income(self, repo):
        """Managers charge on rent collected, not rent scheduled."""
        _property(repo, vacancy_rate_pct=10, mgmt_fee_pct=10)
        result = properties.compute_pro_forma(repo.get_property("prop_1"), [])
        assert result["operating_expenses"] == pytest.approx(600.0 + 270.0)

    def test_non_rental_produces_no_income(self, repo):
        """A primary residence is a liability on the cash-flow statement."""
        _property(repo, status="primary_residence")
        result = properties.compute_pro_forma(repo.get_property("prop_1"), [])
        assert result["gross_scheduled_income"] == 0.0
        assert result["noi"] < 0

    def test_expense_ratio_is_none_without_income(self, repo):
        _property(repo, monthly_rent=0)
        result = properties.compute_pro_forma(repo.get_property("prop_1"), [])
        assert result["expense_ratio"] is None

    def test_multiple_loans_sum_into_debt_service(self, repo):
        _property(repo)
        prop = repo.get_property("prop_1")
        first = _loan(repo, "loan_1", payment_amount=1438.92, lien_position=1)
        heloc = _loan(repo, "loan_2", payment_amount=300.00, lien_position=2)
        result = properties.compute_pro_forma(prop, [first, heloc])
        assert result["debt_service"] == pytest.approx(1738.92)


class TestReturns:
    def test_cap_rate_uses_noi_and_value(self, repo):
        _property(repo)
        _loan(repo)
        econ = properties.compute_property_economics("prop_1")
        # NOI 2400/mo = 28,800/yr on a $400,000 value.
        assert econ["cap_rate"] == pytest.approx(7.2)

    def test_equity_is_value_minus_debt(self, repo):
        _property(repo)
        _loan(repo)
        econ = properties.compute_property_economics("prop_1")
        assert econ["total_debt"] == 200000.0
        assert econ["equity"] == 200000.0
        assert econ["equity_pct"] == 50.0

    def test_ltv_uses_first_lien_cltv_uses_all(self, repo):
        _property(repo)
        _loan(repo, "loan_1", current_principal=200000, lien_position=1)
        _loan(repo, "loan_2", current_principal=40000, lien_position=2)
        econ = properties.compute_property_economics("prop_1")
        assert econ["ltv"] == 50.0     # 200k / 400k
        assert econ["cltv"] == 60.0    # 240k / 400k

    def test_dscr_is_annual_noi_over_annual_debt_service(self, repo):
        _property(repo)
        _loan(repo)
        econ = properties.compute_property_economics("prop_1")
        assert econ["dscr"] == pytest.approx(2400 * 12 / (1438.92 * 12), abs=0.01)

    def test_dscr_is_none_with_no_debt(self, repo):
        _property(repo)
        assert properties.compute_property_economics("prop_1")["dscr"] is None

    def test_cash_on_cash_is_none_without_purchase_data(self, repo):
        """Don't fabricate a denominator."""
        _property(repo, purchase_price=None)
        _loan(repo)
        econ = properties.compute_property_economics("prop_1")
        assert econ["cash_invested"] is None
        assert econ["cash_on_cash"] is None

    def test_cash_on_cash_computed_from_recorded_purchase(self, repo):
        _property(repo, purchase_price=300000, closing_costs=8000,
                  capital_improvements=2000)
        _loan(repo, original_principal=240000)
        econ = properties.compute_property_economics("prop_1")
        # 300k - 240k down, + 8k closing + 2k improvements = 70k invested.
        assert econ["cash_invested"] == 70000.0
        assert econ["cash_on_cash"] is not None

    def test_metrics_are_none_without_a_valuation(self, repo):
        _property(repo, current_value=None)
        _loan(repo)
        econ = properties.compute_property_economics("prop_1")
        assert econ["equity"] is None
        assert econ["cap_rate"] is None
        assert econ["ltv"] is None

    def test_missing_property_returns_none(self, repo):
        assert properties.compute_property_economics("nope") is None


class TestAssetValueResolution:
    """The precedence that stops two things claiming to know a house's worth."""

    def test_property_valuation_wins(self, repo):
        _property(repo, current_value=400000)
        state.account_details["acct_1"] = {"asset_value": 111111}
        loan = _loan(repo, account_id="acct_1")
        assert properties.resolve_asset_value(loan) == 400000.0

    def test_falls_back_to_account_details_asset_value(self, repo):
        """Keeps auto loans and pre-properties setups working."""
        state.account_details["acct_1"] = {"asset_value": 28000}
        loan = repo.upsert_loan({
            "id": "loan_auto", "name": "Car", "loan_type": "auto",
            "account_id": "acct_1", "original_principal": 25000,
            "interest_rate_pct": 4.9, "term_months": 60,
            "origination_date": date(2024, 1, 1),
        })
        assert properties.resolve_asset_value(loan) == 28000.0

    def test_property_without_valuation_falls_through(self, repo):
        _property(repo, current_value=None)
        state.account_details["acct_1"] = {"asset_value": 28000}
        loan = _loan(repo, account_id="acct_1")
        assert properties.resolve_asset_value(loan) == 28000.0

    def test_returns_none_rather_than_guessing(self, repo):
        _property(repo, current_value=None)
        loan = _loan(repo)
        assert properties.resolve_asset_value(loan) is None


class TestLoanBalanceResolution:
    def test_linked_account_balance_wins_over_stored(self, repo):
        state._manual_accounts["acct_1"] = {
            "id": "acct_1", "ledger": -195000, "available": 0,
        }
        loan = _loan(repo, account_id="acct_1", current_principal=200000)
        # Stored says 200k; the synced account says 195k and is fresher.
        assert properties.resolve_loan_balance(loan) == 195000.0

    def test_balance_is_positive_despite_negative_ledger(self, repo):
        state._manual_accounts["acct_1"] = {"id": "acct_1", "ledger": -195000}
        loan = _loan(repo, account_id="acct_1")
        assert properties.resolve_loan_balance(loan) > 0

    def test_falls_back_to_current_principal(self, repo):
        assert properties.resolve_loan_balance(_loan(repo)) == 200000.0

    def test_falls_back_to_the_amortized_balance_not_the_original(self, repo):
        """Using original_principal here would understate equity by every
        dollar of principal paid to date."""
        loan = _loan(repo, current_principal=None)
        balance = properties.resolve_loan_balance(loan, as_of=date(2026, 8, 15))

        assert balance is not None
        assert balance < 240000.0
        # 79 payments into a $240k / 6% / 30yr loan.
        assert balance == pytest.approx(219_000, rel=0.02)

    def test_amortized_balance_matches_the_current_split(self, repo):
        """The two must agree, or equity and the payment table disagree on
        the same screen."""
        loan = _loan(repo, current_principal=None)
        as_of = date(2026, 8, 15)
        assert properties.resolve_loan_balance(loan, as_of) == pytest.approx(
            properties.loan_current_split(loan, as_of)["balance"]
        )

    def test_falls_back_to_original_when_undateable(self, repo):
        loan = _loan(repo, current_principal=None,
                     origination_date=None, first_payment_date=None)
        assert properties.resolve_loan_balance(loan) == 240000.0

    def test_before_the_first_payment_is_the_full_principal(self, repo):
        loan = _loan(repo, current_principal=None)
        assert properties.resolve_loan_balance(
            loan, as_of=date(2019, 1, 1)
        ) == 240000.0


class TestLoanSplit:
    def test_interest_and_principal_split_for_the_current_payment(self, repo):
        _property(repo)
        loan = _loan(repo)
        split = properties.loan_current_split(loan, as_of=date(2020, 2, 15))

        assert split["period"] == 1
        # Month 1 interest on $240,000 at 6% is exactly 240000 * .06 / 12.
        assert split["interest"] == pytest.approx(1200.0)
        assert split["principal"] == pytest.approx(238.92)
        assert split["escrow"] == 600.0

    def test_principal_share_grows_over_time(self, repo):
        _property(repo)
        loan = _loan(repo)
        early = properties.loan_current_split(loan, as_of=date(2020, 2, 15))
        late = properties.loan_current_split(loan, as_of=date(2045, 2, 15))
        assert late["principal"] > early["principal"]
        assert late["interest"] < early["interest"]

    def test_cumulative_principal_paid_accumulates(self, repo):
        _property(repo)
        loan = _loan(repo)
        early = properties.loan_current_split(loan, as_of=date(2021, 2, 15))
        late = properties.loan_current_split(loan, as_of=date(2031, 2, 15))
        assert late["cumulative_principal_paid"] > early["cumulative_principal_paid"]

    def test_before_the_first_payment_is_all_zeros(self, repo):
        _property(repo)
        loan = _loan(repo)
        split = properties.loan_current_split(loan, as_of=date(2019, 1, 1))
        assert split["period"] == 0
        assert split["interest"] == 0.0

    def test_payment_derived_when_not_stored(self, repo):
        loan = _loan(repo, payment_amount=None)
        # $240,000 at 6% over 360 months.
        assert properties.loan_payment(loan) == pytest.approx(1438.92, abs=0.01)


class TestPerformanceClassification:
    def test_healthy_property_is_strong(self, repo):
        _property(repo)
        _loan(repo)
        econ = properties.compute_property_economics("prop_1")
        assert econ["performance"]["rating"] == "strong"

    def test_negative_cash_flow_is_underperforming(self, repo):
        _property(repo, monthly_rent=1000)
        _loan(repo)
        econ = properties.compute_property_economics("prop_1")
        assert econ["performance"]["rating"] == "underperforming"
        assert any("cash flow" in r.lower() for r in econ["performance"]["reasons"])

    def test_low_dscr_is_underperforming(self, repo):
        _property(repo, monthly_rent=1900)   # NOI 1300 vs 1438.92 debt service
        _loan(repo)
        econ = properties.compute_property_economics("prop_1")
        assert econ["dscr"] < 1.0
        assert econ["performance"]["rating"] == "underperforming"

    def test_marginal_dscr_is_watch(self, repo):
        _property(repo, monthly_rent=2200)   # NOI 1600 -> DSCR ~1.11
        _loan(repo)
        econ = properties.compute_property_economics("prop_1")
        assert 1.0 <= econ["dscr"] < 1.25
        assert econ["performance"]["rating"] == "watch"

    def test_high_expense_ratio_is_watch(self, repo):
        _property(repo, property_tax_annual=24000)   # $2,000/mo of $3,000 rent
        econ = properties.compute_property_economics("prop_1")
        assert econ["performance"]["rating"] == "watch"

    def test_non_rental_is_not_rated(self, repo):
        _property(repo, status="primary_residence")
        econ = properties.compute_property_economics("prop_1")
        assert econ["performance"]["rating"] == "not_rated"

    def test_high_equity_surfaces_as_a_note_not_a_downgrade(self, repo):
        """Lots of equity is an opportunity, not a problem."""
        _property(repo, current_value=400000)
        _loan(repo, current_principal=100000)   # 75% equity
        econ = properties.compute_property_economics("prop_1")
        assert econ["performance"]["rating"] == "strong"
        assert any("equity" in n.lower() for n in econ["performance"]["notes"])

    def test_reasons_are_always_populated(self, repo):
        _property(repo)
        econ = properties.compute_property_economics("prop_1")
        assert econ["performance"]["reasons"]

    def test_never_recommends_selling(self, repo):
        """Flags candidates for a human decision; the call stays the user's."""
        _property(repo, monthly_rent=500)
        _loan(repo)
        econ = properties.compute_property_economics("prop_1")
        joined = " ".join(econ["performance"]["reasons"]).lower()
        assert "sell" not in joined
        assert "get rid" not in joined


class TestActuals:
    def _txn(self, tid, amount, txn_type, day="2026-08-01", pid="prop_1"):
        state.stored_transactions[tid] = {
            "id": tid, "transaction_id": tid, "date": day,
            "description": "RENT" if txn_type == "credit" else "REPAIR",
            "amount": amount, "transaction_type": txn_type,
            "source": "simplefin", "property_id": pid,
        }

    def test_untagged_transactions_are_ignored(self, repo):
        _property(repo)
        self._txn("t1", 3000, "credit", pid=None)
        actual = properties.compute_actuals("prop_1", as_of=date(2026, 8, 15))
        assert actual["total_inflow"] == 0.0
        assert actual["confidence"] == "none"

    def test_inflows_and_outflows_are_separated(self, repo):
        _property(repo)
        self._txn("t1", 3000, "credit")
        self._txn("t2", 450, "debit")
        actual = properties.compute_actuals("prop_1", as_of=date(2026, 8, 15))
        assert actual["total_inflow"] == 3000.0
        assert actual["total_outflow"] == 450.0
        assert actual["avg_monthly_net"] == 2550.0

    def test_confidence_requires_six_months(self, repo):
        _property(repo)
        for i, month in enumerate(range(3, 9)):
            self._txn(f"t{i}", 3000, "credit", day=f"2026-{month:02d}-01")
        actual = properties.compute_actuals("prop_1", as_of=date(2026, 8, 15))
        assert actual["months_of_data"] == 6
        assert actual["confidence"] == "high"

    def test_short_history_is_low_confidence(self, repo):
        _property(repo)
        self._txn("t1", 3000, "credit")
        actual = properties.compute_actuals("prop_1", as_of=date(2026, 8, 15))
        assert actual["confidence"] == "low"

    def test_basis_stays_pro_forma_until_actuals_are_trusted(self, repo):
        _property(repo)
        self._txn("t1", 3000, "credit")
        econ = properties.compute_property_economics("prop_1", as_of=date(2026, 8, 15))
        assert econ["basis"] == "pro_forma"

    def test_basis_switches_once_six_months_exist(self, repo):
        _property(repo)
        for i, month in enumerate(range(3, 9)):
            self._txn(f"t{i}", 3000, "credit", day=f"2026-{month:02d}-01")
        econ = properties.compute_property_economics("prop_1", as_of=date(2026, 8, 15))
        assert econ["basis"] == "actual"

    def test_pro_forma_and_actual_are_never_blended(self, repo):
        """Both blocks always present and independently derived."""
        _property(repo)
        self._txn("t1", 9999, "credit")
        econ = properties.compute_property_economics("prop_1", as_of=date(2026, 8, 15))
        assert econ["pro_forma"]["gross_scheduled_income"] == 3000.0
        assert econ["actual"]["total_inflow"] == 9999.0


class TestPortfolio:
    def test_empty_portfolio(self, repo):
        portfolio = properties.compute_portfolio()
        assert portfolio["count"] == 0
        assert portfolio["total_equity"] == 0.0
        assert portfolio["portfolio_ltv"] is None

    def test_totals_across_properties(self, repo):
        _property(repo, "prop_1", current_value=400000)
        _loan(repo, "loan_1", property_id="prop_1", current_principal=200000)
        _property(repo, "prop_2", name="Oak St", current_value=300000)
        _loan(repo, "loan_2", property_id="prop_2", current_principal=100000)

        portfolio = properties.compute_portfolio()
        assert portfolio["count"] == 2
        assert portfolio["total_value"] == 700000.0
        assert portfolio["total_debt"] == 300000.0
        assert portfolio["total_equity"] == 400000.0
        assert portfolio["portfolio_ltv"] == pytest.approx(42.86, abs=0.01)

    def test_underperformers_are_listed_separately(self, repo):
        _property(repo, "prop_1")
        _loan(repo, "loan_1", property_id="prop_1")
        _property(repo, "prop_2", name="Bad", monthly_rent=500)
        _loan(repo, "loan_2", property_id="prop_2")

        portfolio = properties.compute_portfolio()
        assert [p["name"] for p in portfolio["underperforming"]] == ["Bad"]

    def test_annual_cash_flow_is_twelve_times_monthly(self, repo):
        _property(repo)
        _loan(repo)
        portfolio = properties.compute_portfolio()
        assert portfolio["annual_cash_flow"] == pytest.approx(
            portfolio["monthly_cash_flow"] * 12, abs=0.01
        )
