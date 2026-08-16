"""Equity capacity and the deal analyzer.

The assertion that matters most is that pulling equity out reports what it
costs. An extractable figure shown on its own is the most misleading number
in real estate: it looks like free money and is actually a payment increase.
"""
from datetime import date

import pytest

import properties
from db import properties_repo_memory


@pytest.fixture
def repo():
    return properties_repo_memory.install_for_tests()


def _property(repo, pid="prop_1", value=400000, **overrides):
    row = {
        "id": pid, "name": "Maple St", "status": "rental",
        "monthly_rent": 3000, "vacancy_rate_pct": 0,
        "property_tax_annual": 6000, "insurance_annual": 1200,
        "maintenance_pct_of_rent": 0, "capex_reserve_pct_of_rent": 0,
        "current_value": value,
    }
    row.update(overrides)
    return repo.upsert_property(row)


def _loan(repo, lid="loan_1", principal=200000, **overrides):
    row = {
        "id": lid, "name": "Mortgage", "property_id": "prop_1",
        "original_principal": 240000, "current_principal": principal,
        "interest_rate_pct": 4.0, "term_months": 360,
        "origination_date": date(2020, 1, 1),
        "first_payment_date": date(2020, 2, 1),
        "payment_amount": 1145.80, "lien_position": 1,
    }
    row.update(overrides)
    return repo.upsert_loan(row)


class TestCapacityAvailability:
    def test_missing_property(self, repo):
        result = properties.compute_usable_equity("nope")
        assert result["available"] is False
        assert result["reason"] == "not_found"

    def test_no_valuation_explains_itself(self, repo):
        """Without a value there is nothing to borrow against — say so
        rather than reporting zero, which reads as 'no equity'."""
        _property(repo, value=None)
        result = properties.compute_usable_equity("prop_1")
        assert result["available"] is False
        assert result["reason"] == "no_valuation"
        assert "Record a current value" in result["detail"]


class TestCashOutRefi:
    def test_proceeds_are_capped_at_the_ltv_limit(self, repo):
        _property(repo, value=400000)
        _loan(repo, principal=200000)
        refi = properties.compute_usable_equity("prop_1")["cash_out_refi"]
        # 75% of 400k = 300k ceiling, less the 200k already owed.
        assert refi["new_loan_amount"] == 300000.0
        assert refi["gross_proceeds"] == 100000.0

    def test_closing_costs_are_shown_not_silently_netted(self, repo):
        _property(repo, value=400000)
        _loan(repo, principal=200000)
        refi = properties.compute_usable_equity("prop_1")["cash_out_refi"]
        assert refi["estimated_closing_costs"] == pytest.approx(6000.0)   # 2% of 300k
        assert refi["net_proceeds"] == pytest.approx(94000.0)
        assert refi["closing_cost_pct"] == 2.0

    def test_reports_the_payment_increase(self, repo):
        _property(repo, value=400000)
        _loan(repo, principal=200000)
        refi = properties.compute_usable_equity("prop_1")["cash_out_refi"]
        assert refi["new_payment"] > refi["current_payment"]
        assert refi["payment_delta"] == pytest.approx(
            refi["new_payment"] - refi["current_payment"], abs=0.01
        )

    def test_cash_flow_after_reflects_the_higher_payment(self, repo):
        _property(repo, value=400000)
        _loan(repo, principal=200000)
        capacity = properties.compute_usable_equity("prop_1")
        refi = capacity["cash_out_refi"]
        assert refi["cash_flow_after"] == pytest.approx(
            capacity["current_cash_flow"] - refi["payment_delta"], abs=0.01
        )

    def test_flags_when_extracting_equity_kills_cash_flow(self, repo):
        """The whole reason this module exists.

        A property with thin margins can be cash-flow positive today and
        negative the moment you refinance it — the extractable figure looks
        like free money and is a payment increase.
        """
        _property(repo, value=400000, monthly_rent=1900)
        _loan(repo, principal=100000)
        capacity = properties.compute_usable_equity("prop_1")
        assert capacity["current_cash_flow"] > 0
        assert capacity["cash_out_refi"]["cash_flow_after"] < 0
        assert capacity["cash_out_refi"]["kills_cash_flow"] is True

    def test_healthy_property_is_not_flagged(self, repo):
        _property(repo, value=400000, monthly_rent=5000)
        _loan(repo, principal=100000)
        capacity = properties.compute_usable_equity("prop_1")
        assert capacity["cash_out_refi"]["kills_cash_flow"] is False

    def test_already_above_the_limit_yields_nothing(self, repo):
        _property(repo, value=400000)
        _loan(repo, principal=380000)
        refi = properties.compute_usable_equity("prop_1")["cash_out_refi"]
        assert refi["gross_proceeds"] == 0.0
        assert refi["net_proceeds"] == 0.0

    def test_the_ltv_cap_is_a_parameter(self, repo):
        _property(repo, value=400000)
        _loan(repo, principal=200000)
        conservative = properties.compute_usable_equity(
            "prop_1", max_ltv_pct=65
        )["cash_out_refi"]
        assert conservative["gross_proceeds"] == pytest.approx(60000.0)


class TestHeloc:
    def test_line_is_capped_at_the_cltv_limit(self, repo):
        _property(repo, value=400000)
        _loan(repo, principal=200000)
        heloc = properties.compute_usable_equity("prop_1")["heloc"]
        # 85% of 400k = 340k, less 200k owed.
        assert heloc["max_line"] == 140000.0

    def test_draw_cost_is_interest_only(self, repo):
        _property(repo, value=400000)
        _loan(repo, principal=200000)
        heloc = properties.compute_usable_equity("prop_1")["heloc"]
        assert heloc["interest_only_payment"] == pytest.approx(
            140000 * 8.5 / 100 / 12, abs=0.01
        )

    def test_variable_rate_is_labelled(self, repo):
        """A fixed-looking payment on a floating rate is a trap."""
        _property(repo, value=400000)
        _loan(repo, principal=200000)
        heloc = properties.compute_usable_equity("prop_1")["heloc"]
        assert heloc["rate_type"] == "variable"
        assert "float" in heloc["note"].lower()

    def test_heloc_reaches_further_than_a_refi(self, repo):
        _property(repo, value=400000)
        _loan(repo, principal=200000)
        capacity = properties.compute_usable_equity("prop_1")
        assert capacity["heloc"]["max_line"] > capacity["cash_out_refi"]["gross_proceeds"]


class TestPortfolioEquity:
    def test_empty(self, repo):
        portfolio = properties.compute_portfolio_equity()
        assert portfolio["count"] == 0
        assert portfolio["total_cash_out_available"] == 0.0

    def test_totals_across_properties(self, repo):
        _property(repo, "prop_1", value=400000)
        _loan(repo, "loan_1", principal=200000)
        _property(repo, "prop_2", name="Oak St", value=300000)

        portfolio = properties.compute_portfolio_equity()
        assert portfolio["count"] == 2
        assert portfolio["total_equity"] == pytest.approx(500000.0)

    def test_properties_without_a_valuation_are_named_not_dropped(self, repo):
        """Silently excluding them would just lower the total unexplained."""
        _property(repo, "prop_1", value=400000)
        _property(repo, "prop_2", name="Unvalued", value=None)

        portfolio = properties.compute_portfolio_equity()
        assert portfolio["count"] == 1
        assert [p["name"] for p in portfolio["needs_valuation"]] == ["Unvalued"]


class TestDealAnalyzer:
    BASE = {
        "purchase_price": 300000, "down_pct": 25, "rate_pct": 7.0,
        "term_months": 360, "monthly_rent": 2800, "vacancy_pct": 5,
        "opex_pct": 35, "closing_pct": 3,
    }

    def test_requires_a_price(self, repo):
        assert properties.analyze_deal({"purchase_price": 0})["available"] is False

    def test_cash_needed_sums_down_closing_and_rehab(self, repo):
        result = properties.analyze_deal({**self.BASE, "rehab": 15000})
        financing = result["financing"]
        assert financing["down_payment"] == 75000.0
        assert financing["closing_costs"] == 9000.0
        assert financing["total_cash_needed"] == 99000.0

    def test_economics_chain(self, repo):
        result = properties.analyze_deal(self.BASE)["economics"]
        assert result["effective_gross_income"] == pytest.approx(2660.0)   # 2800 × 0.95
        assert result["operating_expenses"] == pytest.approx(931.0)        # 35%
        assert result["noi"] == pytest.approx(1729.0)

    def test_returns_are_reported(self, repo):
        returns = properties.analyze_deal(self.BASE)["returns"]
        assert returns["cap_rate"] is not None
        assert returns["cash_on_cash"] is not None
        assert returns["dscr"] is not None

    def test_break_even_rent_makes_cash_flow_zero(self, repo):
        result = properties.analyze_deal(self.BASE)
        at_break_even = properties.analyze_deal({
            **self.BASE, "monthly_rent": result["returns"]["break_even_rent"],
        })
        assert at_break_even["economics"]["cash_flow"] == pytest.approx(0.0, abs=1.0)

    def test_an_all_cash_deal_has_no_borrowing_cost(self, repo):
        result = properties.analyze_deal(self.BASE)
        assert result["net_effect"]["borrowing_cost"] == 0.0
        assert result["net_effect"]["portfolio_cash_flow_delta"] == (
            result["net_effect"]["deal_cash_flow"]
        )


class TestDealFundedFromEquity:
    """The leverage question, framed honestly."""

    def _source_property(self, repo):
        _property(repo, value=400000, monthly_rent=5000)
        _loan(repo, principal=100000)

    def test_heloc_funding_carries_a_cost(self, repo):
        self._source_property(repo)
        result = properties.analyze_deal({
            "purchase_price": 300000, "down_pct": 25, "monthly_rent": 2800,
            "funded_from": "heloc", "source_property_id": "prop_1",
        })
        assert result["net_effect"]["borrowing_cost"] > 0
        assert result["net_effect"]["portfolio_cash_flow_delta"] < (
            result["net_effect"]["deal_cash_flow"]
        )

    def test_funding_note_names_the_source(self, repo):
        self._source_property(repo)
        result = properties.analyze_deal({
            "purchase_price": 300000, "monthly_rent": 2800,
            "funded_from": "heloc", "source_property_id": "prop_1",
        })
        assert "Maple St" in result["net_effect"]["funding_note"]

    def test_a_standalone_positive_deal_can_still_hurt_the_portfolio(self, repo):
        """The failure mode this whole framing exists to catch."""
        self._source_property(repo)
        result = properties.analyze_deal({
            "purchase_price": 300000, "down_pct": 25, "rate_pct": 7.0,
            "monthly_rent": 2350, "opex_pct": 30,
            "funded_from": "heloc", "source_property_id": "prop_1",
        })
        if result["net_effect"]["deal_cash_flow"] > 0:
            assert result["net_effect"]["portfolio_cash_flow_delta"] < (
                result["net_effect"]["deal_cash_flow"]
            )

    def test_refi_funding_uses_the_payment_delta(self, repo):
        self._source_property(repo)
        capacity = properties.compute_usable_equity("prop_1")
        result = properties.analyze_deal({
            "purchase_price": 300000, "monthly_rent": 2800,
            "funded_from": "cash_out_refi", "source_property_id": "prop_1",
        })
        assert result["net_effect"]["borrowing_cost"] == pytest.approx(
            capacity["cash_out_refi"]["payment_delta"], abs=0.01
        )


class TestSensitivity:
    def test_three_scenarios_are_returned(self, repo):
        result = properties.analyze_deal(TestDealAnalyzer.BASE)
        assert len(result["sensitivity"]) == 3

    def test_each_scenario_is_worse_than_the_base_case(self, repo):
        result = properties.analyze_deal(TestDealAnalyzer.BASE)
        base = result["economics"]["cash_flow"]
        assert all(s["cash_flow"] < base for s in result["sensitivity"])


class TestWarnings:
    def test_a_loss_making_deal_is_called_out(self, repo):
        result = properties.analyze_deal({
            **TestDealAnalyzer.BASE, "monthly_rent": 1200,
        })
        assert any("loses" in w for w in result["warnings"])

    def test_thin_dscr_is_called_out(self, repo):
        result = properties.analyze_deal({
            **TestDealAnalyzer.BASE, "monthly_rent": 2100,
        })
        assert any("DSCR" in w for w in result["warnings"])

    def test_fragility_under_sensitivity_is_called_out(self, repo):
        result = properties.analyze_deal({
            **TestDealAnalyzer.BASE, "monthly_rent": 2450,
        })
        assert any("negative" in w for w in result["warnings"])

    def test_a_solid_deal_produces_no_warnings(self, repo):
        result = properties.analyze_deal({
            **TestDealAnalyzer.BASE, "monthly_rent": 4200,
        })
        assert result["warnings"] == []


class TestEndpoints:
    def test_portfolio_capacity(self, client, repo):
        _property(repo, value=400000)
        _loan(repo, principal=200000)
        response = client.get("/api/equity/capacity")
        assert response.status_code == 200
        assert response.json()["count"] == 1

    def test_single_property_capacity(self, client, repo):
        _property(repo, value=400000)
        _loan(repo, principal=200000)
        response = client.get("/api/equity/capacity/prop_1")
        assert response.json()["cash_out_refi"]["gross_proceeds"] == 100000.0

    def test_missing_property_is_404(self, client, repo):
        assert client.get("/api/equity/capacity/nope").status_code == 404

    def test_ltv_cap_can_be_overridden(self, client, repo):
        _property(repo, value=400000)
        _loan(repo, principal=200000)
        response = client.get("/api/equity/capacity", params={"max_ltv_pct": 65})
        assert response.json()["total_cash_out_available"] < 100000

    def test_analyze_deal(self, client, repo):
        response = client.post("/api/equity/analyze-deal", json={
            "purchase_price": 300000, "monthly_rent": 2800,
        })
        assert response.status_code == 200
        assert response.json()["returns"]["cap_rate"] is not None

    def test_zero_price_rejected(self, client, repo):
        assert client.post(
            "/api/equity/analyze-deal", json={"purchase_price": 0}
        ).status_code == 422

    def test_equity_funding_requires_a_source(self, client, repo):
        response = client.post("/api/equity/analyze-deal", json={
            "purchase_price": 300000, "funded_from": "heloc",
        })
        assert response.status_code == 422
        assert "source_property_id" in response.json()["detail"]
