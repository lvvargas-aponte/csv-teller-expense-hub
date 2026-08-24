"""Tests for analytics helpers — recurring detection and snapshot enrichment."""
from datetime import date, timedelta

import pytest

import state
import analytics
from analytics import (
    _normalize_merchant,
    build_financial_snapshot,
    detect_recurring_charges,
    group_debit_spending,
)


def _add_txn(tid, amount, days_ago, description="NETFLIX MEMBERSHIP", category="Entertainment"):
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    state.stored_transactions[tid] = {
        "id": tid, "date": d, "description": description, "amount": amount,
        "category": category, "transaction_type": "debit", "source": "simplefin",
    }


class TestRecurringDetection:
    def test_detects_monthly_subscription(self, client):
        _add_txn("a", 15.49, days_ago=5)
        _add_txn("b", 15.49, days_ago=35)
        _add_txn("c", 15.49, days_ago=65)

        out = detect_recurring_charges()
        assert len(out) == 1
        rec = out[0]
        assert rec["occurrences"] == 3
        assert rec["months_seen"] == 3
        assert rec["average_amount"] == 15.49
        assert rec["estimated_monthly_cost"] == 15.49
        assert "netflix" in rec["merchant_key"]

    def test_skips_one_off_charge(self, client):
        _add_txn("a", 200.00, days_ago=5, description="ELECTRONICS STORE")
        out = detect_recurring_charges()
        assert out == []

    def test_skips_highly_variable_amounts(self, client):
        # Same merchant key but amounts vary far beyond the 60% spread gate — not a subscription.
        _add_txn("a", 10.00, days_ago=5, description="GAS STATION")
        _add_txn("b", 50.00, days_ago=35, description="GAS STATION")
        _add_txn("c", 30.00, days_ago=65, description="GAS STATION")
        out = detect_recurring_charges()
        assert out == []

    def test_normalizes_changing_transaction_ids(self, client):
        # Real-world: descriptions often carry changing reference numbers.
        _add_txn("a", 9.99, days_ago=5,  description="SPOTIFY *REF12345")
        _add_txn("b", 9.99, days_ago=35, description="SPOTIFY *REF67890")
        out = detect_recurring_charges()
        assert len(out) == 1
        assert "spotify" in out[0]["merchant_key"]

    def test_detects_variable_utility_under_60pct_spread(self, client):
        # Real utility bills swing 30-50% month to month; old 25% gate dropped them.
        _add_txn("a", 89.90,  days_ago=5,  description="DUKE ENERGY 0413", category="Utilities")
        _add_txn("b", 136.41, days_ago=35, description="DUKE-ENERGY PAYMENT WEB ID: 1234", category="Utilities")
        out = detect_recurring_charges()
        assert len(out) == 1
        assert "duke" in out[0]["merchant_key"]

    def test_excludes_cc_payment_category(self, client):
        # Same merchant in 2 months but flagged as CC Payment — not real spend.
        _add_txn("a", 322.18, days_ago=5,
                 description="AMERICAN EXPRESS ACH PMT W3826 WEB ID: 2005032111",
                 category="CC Payment")
        _add_txn("b", 322.18, days_ago=35,
                 description="AMERICAN EXPRESS ACH PMT W4400 WEB ID: 2005032111",
                 category="CC Payment")
        assert detect_recurring_charges() == []

    def test_excludes_tagged_transfer(self, client):
        # Synchrony transfer to HYSA — tagged, must drop from spending + recurring.
        _add_txn("a", 1000.0, days_ago=5,  description="SYNCHRONY BANK TRANSFER 1234")
        _add_txn("b", 1000.0, days_ago=35, description="SYNCHRONY BANK TRANSFER 9876")
        for tid in ("a", "b"):
            t = state.stored_transactions[tid]
            t["transfer_to_account_id"] = "manual_hysa"
            state.stored_transactions[tid] = t
        assert detect_recurring_charges() == []
        # And must not be counted as spending.
        spending = group_debit_spending()
        for month in spending.values():
            assert "Entertainment" not in month or month["Entertainment"] == 0


class TestCadenceAwareDetection:
    def test_monthly_cadence_classified(self, client):
        _add_txn("a", 15.49, days_ago=5)
        _add_txn("b", 15.49, days_ago=35)
        _add_txn("c", 15.49, days_ago=65)
        out = detect_recurring_charges()
        assert out[0]["cadence"] == "monthly"
        assert out[0]["interval_days"] == 30
        assert out[0]["estimated_monthly_cost"] == 15.49

    def test_annual_renewal_costs_one_twelfth(self, client):
        _add_txn("a", 139.00, days_ago=10, description="AMAZON PRIME RENEWAL")
        _add_txn("b", 139.00, days_ago=375, description="AMAZON PRIME RENEWAL")
        out = detect_recurring_charges()
        assert len(out) == 1
        assert out[0]["cadence"] == "annual"
        assert out[0]["estimated_monthly_cost"] == round(139.00 / 12, 2)

    def test_weekly_charge_costs_four_point_three_x(self, client):
        for i in range(8):
            _add_txn(f"t{i}", 12.00, days_ago=3 + 7 * i, description="WEEKLY CLEANER")
        out = detect_recurring_charges()
        assert len(out) == 1
        assert out[0]["cadence"] == "weekly"
        assert out[0]["estimated_monthly_cost"] == round(12.00 * 52 / 12, 2)

    def test_price_increase_reported_on_latest_charge(self, client):
        _add_txn("a", 15.49, days_ago=65)
        _add_txn("b", 15.49, days_ago=35)
        _add_txn("c", 17.99, days_ago=5)
        rec = detect_recurring_charges()[0]
        assert rec["latest_amount"] == 17.99
        assert rec["price_change_pct"] == round((17.99 - 15.49) / 15.49 * 100, 1)

    def test_category_comes_from_latest_charge(self, client):
        _add_txn("a", 15.49, days_ago=65, category="Entertainment")
        _add_txn("b", 15.49, days_ago=5, category="Subscriptions")
        _add_txn("c", 15.49, days_ago=35, category="Entertainment")
        assert detect_recurring_charges()[0]["category"] == "Subscriptions"


class TestNormalizeMerchant:
    def test_strips_web_id_tail(self):
        assert _normalize_merchant(
            "AMERICAN EXPRESS ACH PMT W3826 WEB ID: 2005032111"
        ) == _normalize_merchant(
            "AMERICAN EXPRESS ACH PMT W4400 WEB ID: 2005032111"
        )

    def test_strips_state_code_tail(self):
        a = _normalize_merchant("SQ *AZZURRA HEALTH CARE Doral FL")
        b = _normalize_merchant("SQ *AZZURRA HEALTH CARE Doral")
        assert a == b
        assert "azzurra" in a
        assert " fl" not in a

    def test_strips_processor_prefix(self):
        assert "starbucks" in _normalize_merchant("SQ *STARBUCKS 123")
        assert "starbucks" in _normalize_merchant("TST* STARBUCKS")

    def test_gas_station_still_rejected_by_spread(self, client):
        # Spread filter still blocks volatile categories (sanity check).
        _add_txn("a", 10.00, days_ago=5,  description="GAS STATION")
        _add_txn("b", 50.00, days_ago=35, description="GAS STATION")
        assert detect_recurring_charges() == []


class TestSnapshotEnrichment:
    def test_snapshot_includes_new_sections(self, client):
        # Seed a budget, a goal, and a recurring charge.
        client.put("/api/budgets/Dining", json={
            "category": "Dining", "monthly_limit": 200.0,
        })
        client.post("/api/goals", json={
            "name": "Vacation", "target_amount": 1000.0, "current_balance": 250.0,
        })
        _add_txn("a", 9.99, days_ago=5,  description="SPOTIFY")
        _add_txn("b", 9.99, days_ago=35, description="SPOTIFY")

        snap = build_financial_snapshot()
        assert "budgets" in snap
        assert "goals" in snap
        assert "recurring_charges" in snap

        assert snap["budgets"][0]["category"] == "Dining"
        assert snap["goals"][0]["name"] == "Vacation"
        assert snap["goals"][0]["progress_pct"] == 25.0
        assert any("spotify" in r["merchant_key"] for r in snap["recurring_charges"])


def _seed_dated_txn(tid, date_str, amount, category="Dining"):
    """Seed an outflow on an explicit calendar date (no days_ago drift)."""
    state.stored_transactions[tid] = {
        "id": tid, "date": date_str, "description": "MERCHANT", "amount": amount,
        "category": category, "transaction_type": "debit", "direction": "outflow",
        "source": "simplefin",
    }


class TestMonthToDateComparison:
    def test_month_to_date_compares_the_same_period(self):
        _seed_dated_txn("a", "2026-07-05", 100.0)
        _seed_dated_txn("b", "2026-07-20", 400.0)   # after the cutoff day
        _seed_dated_txn("c", "2026-08-05", 120.0)

        out = analytics.compute_month_to_date_comparison(date(2026, 8, 10))

        assert out["as_of_day"] == 10
        assert out["current_month"] == "2026-08"
        assert out["prior_month"] == "2026-07"
        assert out["current_month_to_date"] == 120.0
        assert out["prior_month_same_period"] == 100.0   # NOT 500.0
        assert out["prior_month_full"] == 500.0
        assert out["delta"] == 20.0
        assert out["pct_change"] == 20.0
        assert out["current_month_is_partial"] is True

    def test_cutoff_is_clamped_to_the_prior_months_length(self):
        """Oct 31 has no counterpart in September; the whole month counts."""
        _seed_dated_txn("a", "2026-09-30", 50.0)
        _seed_dated_txn("b", "2026-10-31", 10.0)

        out = analytics.compute_month_to_date_comparison(date(2026, 10, 31))

        assert out["prior_month_same_period"] == 50.0
        assert out["current_month_is_partial"] is False


# ---------------------------------------------------------------------------
# Carry cost — what the outstanding debt costs per month
# ---------------------------------------------------------------------------

def _seed_debt(account_id, name, balance, apr=None, subtype=""):
    state._manual_accounts[account_id] = {
        "id": account_id, "institution": "Bank", "name": name,
        "type": "credit", "subtype": subtype,
        "available": 0.0, "ledger": balance, "manual": True,
    }
    if apr is not None:
        state.account_details[account_id] = {"apr": apr}


class TestCarryCost:
    @pytest.mark.asyncio
    async def test_monthly_interest_is_balance_times_apr_over_twelve(self):
        _seed_debt("c1", "Sapphire", 4200.0, apr=24.99)

        out = await analytics.compute_carry_cost()

        assert out["by_account"][0]["monthly_interest"] == 87.47
        assert out["by_account"][0]["name"] == "Sapphire"
        assert out["by_account"][0]["balance"] == 4200.0
        assert out["monthly_interest"] == 87.47
        assert out["annual_interest"] == 1049.64
        assert out["accounts_missing_apr"] == 0

    @pytest.mark.asyncio
    async def test_a_card_with_no_apr_costs_nothing_and_is_counted(self):
        _seed_debt("c1", "Sapphire", 4200.0, apr=24.99)
        _seed_debt("c2", "Store Card", 900.0)
        _seed_debt("c3", "Airline Card", 300.0)

        out = await analytics.compute_carry_cost()

        assert out["monthly_interest"] == 87.47
        assert out["accounts_missing_apr"] == 2
        assert [a["account_id"] for a in out["by_account"]] == ["c1"]

    @pytest.mark.asyncio
    async def test_installment_debt_carries_a_cost_too(self):
        """Utilization ignores a car loan; its interest is still real money."""
        _seed_debt("auto", "Auto Loan", 18000.0, apr=6.0, subtype="loan")

        out = await analytics.compute_carry_cost()

        assert out["monthly_interest"] == 90.0

    @pytest.mark.asyncio
    async def test_a_cleared_card_is_neither_charged_nor_counted_as_missing(self):
        _seed_debt("c1", "Paid Off", 0.0)

        out = await analytics.compute_carry_cost()

        assert out["monthly_interest"] == 0.0
        assert out["accounts_missing_apr"] == 0
        assert out["by_account"] == []

    @pytest.mark.asyncio
    async def test_cash_accounts_are_not_debt(self):
        state._manual_accounts["s1"] = {
            "id": "s1", "institution": "Bank", "name": "Savings",
            "type": "depository", "subtype": "savings",
            "available": 5000.0, "ledger": 5000.0, "manual": True,
        }
        state.account_details["s1"] = {"apr": 4.0}

        out = await analytics.compute_carry_cost()

        assert out["by_account"] == []
        assert out["monthly_interest"] == 0.0


class TestCarryCostEndpoint:
    def test_credit_health_carries_the_cost(self, client):
        _seed_debt("c1", "Sapphire", 4200.0, apr=24.99)

        body = client.get("/api/accounts/credit-health").json()

        assert body["carry_cost"]["monthly_interest"] == 87.47
        assert body["carry_cost"]["accounts_missing_apr"] == 0
        # The utilization composition is untouched.
        assert body["accounts"][0]["account_id"] == "c1"
