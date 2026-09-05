"""Tests for analytics helpers — recurring detection and snapshot enrichment."""
import calendar
from datetime import date, timedelta

import pytest

import credit_health_service
import state
import analytics
from db import accounts_repo_memory
from analytics import (
    _normalize_merchant,
    build_financial_snapshot,
    detect_recurring_charges,
    group_debit_spending,
)


# Offsets are measured from mid-month, not from the real clock. Counted back
# from `date.today()`, `days_ago=5` and `days_ago=35` both land in the previous
# month on the 5th of any month — `months_seen` collapses to 1 and every
# "≥ 2 distinct months" gate in the detector fails. The suite went red every
# month for a reason that had nothing to do with the code under test. Anchoring
# at the 15th keeps 30-day steps one month apart whatever the date is.
_ANCHOR = date.today().replace(day=15)


def _add_txn(tid, amount, days_ago, description="NETFLIX MEMBERSHIP", category="Entertainment"):
    d = (_ANCHOR - timedelta(days=days_ago)).isoformat()
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


class TestCommitmentClassification:
    """The bucket each recurring merchant lands in, and the stricter gates a
    merchant faces when neither its category nor its description vouches for
    it. Consumers filter on ``commitment_type``; nothing re-derives it.
    """

    def test_subscription_category_becomes_subscription(self, client):
        _add_txn("a", 15.49, days_ago=5, category="Subscriptions")
        _add_txn("b", 15.49, days_ago=35, category="Subscriptions")
        assert detect_recurring_charges()[0]["commitment_type"] == "subscription"

    def test_utility_category_becomes_bill(self, client):
        _add_txn("a", 89.90, days_ago=5, description="DUKE ENERGY", category="Utilities")
        _add_txn("b", 96.10, days_ago=35, description="DUKE ENERGY", category="Utilities")
        assert detect_recurring_charges()[0]["commitment_type"] == "bill"

    def test_uncategorized_mortgage_becomes_bill(self, client):
        # The real-world case: a mortgage nobody ever categorized must not be
        # offered up for cancellation on the subscriptions list.
        _add_txn("a", 3053.14, days_ago=5,
                 description="TRUIST MORTG OLB MTGPMT 4008583934 WEB", category="")
        _add_txn("b", 3053.14, days_ago=35,
                 description="TRUIST MORTG OLB MTGPMT 4008583934 WEB", category="")
        assert detect_recurring_charges()[0]["commitment_type"] == "bill"

    def test_uncategorized_card_payment_dropped(self, client):
        # Escapes the non_spending role precisely because it has no
        # category — the description is the only signal left.
        _add_txn("a", 35.00, days_ago=5,
                 description="DISCOVER E-PAYMENT 6712 WEB ID: 351002", category="")
        _add_txn("b", 35.00, days_ago=35,
                 description="DISCOVER E-PAYMENT 6712 WEB ID: 351002", category="")
        assert detect_recurring_charges() == []

    def test_interest_charge_is_not_a_commitment(self, client):
        _add_txn("a", 5.85, days_ago=5, description="INTEREST CHARGE-PURCHASE",
                 category="Interest")
        _add_txn("b", 5.85, days_ago=35, description="INTEREST CHARGE-PURCHASE",
                 category="Interest")
        assert detect_recurring_charges() == []

    def test_untrusted_merchant_needs_three_months(self, client):
        # Two grocery runs a month apart are not a subscription.
        _add_txn("a", 81.00, days_ago=5, description="PUBLIX #1551 RALEIGH", category="")
        _add_txn("b", 79.00, days_ago=35, description="PUBLIX #1551 RALEIGH", category="")
        assert detect_recurring_charges() == []

    def test_untrusted_merchant_kept_with_three_steady_months(self, client):
        _add_txn("a", 280.00, days_ago=5, description="RISING SUN POOLS", category="")
        _add_txn("b", 280.00, days_ago=35, description="RISING SUN POOLS", category="")
        _add_txn("c", 280.00, days_ago=65, description="RISING SUN POOLS", category="")
        out = detect_recurring_charges()
        assert len(out) == 1
        assert out[0]["commitment_type"] == "recurring_spend"

    def test_untrusted_merchant_needs_a_regular_cadence(self, client):
        # Three months of history and steady amounts, but 20-day gaps fit no
        # billing band — takeout, not a subscription.
        _add_txn("a", 36.00, days_ago=5,  description="UBER EATS", category="")
        _add_txn("b", 36.00, days_ago=25, description="UBER EATS", category="")
        _add_txn("c", 36.00, days_ago=45, description="UBER EATS", category="")
        _add_txn("d", 36.00, days_ago=90, description="UBER EATS", category="")
        assert detect_recurring_charges() == []

    def test_untrusted_merchant_needs_steady_amounts(self, client):
        # Regular monthly cadence, three months, but a 50% swing — inside the
        # 0.60 gate a categorized bill gets, outside the 0.35 an anonymous
        # merchant must clear.
        _add_txn("a", 40.00, days_ago=5,  description="CORNER SHOP", category="")
        _add_txn("b", 60.00, days_ago=35, description="CORNER SHOP", category="")
        _add_txn("c", 50.00, days_ago=65, description="CORNER SHOP", category="")
        assert detect_recurring_charges() == []

    def test_trusted_category_survives_two_irregular_months(self, client):
        # Claude.AI: a real subscription with only two charges and an uneven
        # gap. The category is what saves it from the cadence gate.
        # 45 days apart: two distinct months, but a gap that fits no billing
        # band, so cadence lands on "irregular".
        _add_txn("a", 107.39, days_ago=5,  description="CLAUDE.AI SUBSCRIPTION",
                 category="Subscriptions")
        _add_txn("b", 107.39, days_ago=50, description="CLAUDE.AI SUBSCRIPTION",
                 category="Subscriptions")
        out = detect_recurring_charges()
        assert len(out) == 1
        assert out[0]["cadence"] == "irregular"
        assert out[0]["commitment_type"] == "subscription"


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


def _card_txn(tid, account_id, day, amount, description, category=None,
              transaction_type="debit"):
    txn = {
        "id": tid, "date": day, "description": description, "amount": amount,
        "transaction_type": transaction_type, "account_id": account_id,
        "source": "simplefin",
    }
    if category is not None:
        txn["category"] = category
    state.stored_transactions[tid] = txn


class TestCardActivity:
    """What a month actually did to a card, read off the posted transactions.

    ``compute_carry_cost`` models a cost from today's balance and the APR.
    This reads the ``INTEREST CHARGE`` line the issuer actually posted, which
    already knows about the grace period and any mid-cycle payment. The two
    are expected to disagree.
    """

    @pytest.mark.asyncio
    async def test_a_month_splits_into_spend_payments_and_interest(self):
        _seed_debt("c1", "Sapphire", 900.0, apr=20.0)
        _card_txn("t1", "c1", "2026-07-04", 400.0, "GROCERY STORE")
        _card_txn("t2", "c1", "2026-07-09", 19.01, "INTEREST CHARGE-PURCHASES")
        _card_txn("t3", "c1", "2026-07-20", 50.0, "Payment Received",
                  transaction_type="credit")

        month = (await analytics.compute_card_activity(
            today=date(2026, 8, 15)
        ))["by_account"]["c1"]["latest"]

        assert month["spend"] == 400.0
        assert month["interest"] == 19.01
        assert month["payments"] == 50.0
        # Spend and interest add to what is owed, a payment subtracts.
        assert month["net_change"] == 369.01

    @pytest.mark.asyncio
    async def test_interest_is_matched_by_category_or_by_description(self):
        """Teller categorizes the line; SimpleFIN sends it bare."""
        _seed_debt("c1", "Sapphire", 900.0, apr=20.0)
        _card_txn("t1", "c1", "2026-07-09", 26.38,
                  "INTEREST CHARGED ON PURCHASES", category="Interest")
        _card_txn("t2", "c1", "2026-07-10", 12.24, "INTEREST CHARGE ON PURCHASES")

        month = (await analytics.compute_card_activity(
            today=date(2026, 8, 15)
        ))["by_account"]["c1"]["latest"]

        assert month["interest"] == 38.62
        # Counting either as spending would both inflate spend and bury the
        # one figure this exists to surface.
        assert month["spend"] == 0.0

    @pytest.mark.asyncio
    async def test_a_payment_is_recognized_on_both_feed_shapes(self):
        """SimpleFIN posts a payment to the card as an inflow; Teller posts it
        as a debit categorized CC Payment. Both are payments."""
        _seed_debt("c1", "Sapphire", 900.0, apr=20.0)
        _card_txn("t1", "c1", "2026-07-20", 40.0, "Payment Received",
                  transaction_type="credit")
        _card_txn("t2", "c1", "2026-07-25", 60.0, "BA ELECTRONIC PAYMENT",
                  category="CC Payment")

        month = (await analytics.compute_card_activity(
            today=date(2026, 8, 15)
        ))["by_account"]["c1"]["latest"]

        assert month["payments"] == 100.0
        assert month["spend"] == 0.0

    @pytest.mark.asyncio
    async def test_interest_earned_on_a_savings_account_is_not_card_interest(self):
        """A deposit account posts its own interest as an inflow. Scoping to
        credit accounts is what keeps it out of the card's cost."""
        _seed_debt("c1", "Sapphire", 900.0, apr=20.0)
        state._manual_accounts["s1"] = {
            "id": "s1", "institution": "Bank", "name": "Savings",
            "type": "depository", "subtype": "savings",
            "available": 5000.0, "ledger": 5000.0, "manual": True,
        }
        _card_txn("t1", "s1", "2026-07-01", 34.88, "June interest",
                  transaction_type="credit")

        out = await analytics.compute_card_activity(today=date(2026, 8, 15))

        assert "s1" not in out["by_account"]
        assert out["by_account"] == {}

    @pytest.mark.asyncio
    async def test_the_running_month_is_excluded(self):
        """Half a cycle set beside a whole one reads as a collapse in spending."""
        _seed_debt("c1", "Sapphire", 900.0, apr=20.0)
        _card_txn("t1", "c1", "2026-07-04", 400.0, "GROCERY STORE")
        _card_txn("t2", "c1", "2026-08-02", 25.0, "COFFEE")

        out = await analytics.compute_card_activity(today=date(2026, 8, 15))

        assert out["months"] == ["2026-07"]
        assert out["latest_month"] == "2026-07"

    @pytest.mark.asyncio
    async def test_the_largest_purchase_of_the_month_is_named(self):
        """One booking can be the whole reason a card crossed a threshold."""
        _seed_debt("c1", "Sapphire", 900.0, apr=20.0)
        _card_txn("t1", "c1", "2026-07-04", 40.0, "GROCERY STORE")
        _card_txn("t2", "c1", "2026-07-28", 5398.0, "PRINCESS CRUISE RES")
        _card_txn("t3", "c1", "2026-07-29", 6000.0, "Payment Received",
                  transaction_type="credit")

        latest = (await analytics.compute_card_activity(
            today=date(2026, 8, 15)
        ))["by_account"]["c1"]["latest"]

        # The payment is larger than any purchase here and must not win.
        assert latest["largest_purchase"]["description"] == "PRINCESS CRUISE RES"
        assert latest["largest_purchase"]["amount"] == 5398.0

    @pytest.mark.asyncio
    async def test_a_card_with_no_transactions_is_absent_not_zeroed(self):
        """Rendering zeros would claim a month of no spending we never saw."""
        _seed_debt("c1", "Sapphire", 900.0, apr=20.0)

        out = await analytics.compute_card_activity(today=date(2026, 8, 15))

        assert out["by_account"] == {}
        assert out["latest_month"] is None

    @pytest.mark.asyncio
    async def test_an_installment_loan_is_not_a_card(self):
        _seed_debt("auto", "Auto Loan", 18000.0, apr=6.0, subtype="loan")
        _card_txn("t1", "auto", "2026-07-09", 90.0, "INTEREST CHARGE")

        out = await analytics.compute_card_activity(today=date(2026, 8, 15))

        assert out["by_account"] == {}

    @pytest.mark.asyncio
    async def test_only_the_most_recent_months_are_kept(self):
        _seed_debt("c1", "Sapphire", 900.0, apr=20.0)
        for i, month in enumerate(("04", "05", "06", "07")):
            _card_txn(f"t{i}", "c1", f"2026-{month}-10", 100.0, "GROCERY STORE")

        out = await analytics.compute_card_activity(
            months=3, today=date(2026, 8, 15)
        )

        assert out["months"] == ["2026-05", "2026-06", "2026-07"]
        assert len(out["by_account"]["c1"]["months"]) == 3


class TestUtilizationLevers:
    """The pay-down amounts, computed from today's balance.

    A statement-date balance would be the figure a bureau
    actually reads — but that needs a statement day and a snapshot near it. An
    amount that is right today beats a blank where the right one would go.
    """

    @pytest.mark.asyncio
    async def test_a_card_over_thirty_gets_both_levers(self):
        _seed_debt("c1", "Sapphire", 4630.0)
        state.account_details["c1"] = {"credit_limit": 10000.0}

        card = (await credit_health_service.build())["accounts"][0]

        assert card["levers"] == [
            {"gets_to_pct": 30.0, "amount": 1630.0},
            {"gets_to_pct": 10.0, "amount": 3630.0},
        ]
        assert card["headroom"] == 5370.0

    @pytest.mark.asyncio
    async def test_a_card_between_the_thresholds_gets_only_the_nearer_one(self):
        _seed_debt("c1", "Sapphire", 2500.0)
        state.account_details["c1"] = {"credit_limit": 10000.0}

        card = (await credit_health_service.build())["accounts"][0]

        assert card["levers"] == [{"gets_to_pct": 10.0, "amount": 1500.0}]

    @pytest.mark.asyncio
    async def test_a_cleared_card_needs_no_lever(self):
        _seed_debt("c1", "Paid Off", 0.0)
        state.account_details["c1"] = {"credit_limit": 10000.0}

        card = (await credit_health_service.build())["accounts"][0]

        assert card["levers"] == []
        assert card["projection"] is None

    @pytest.mark.asyncio
    async def test_the_totals_name_how_many_cards_break_the_shelf(self):
        """The aggregate can read good while one card sits well over it."""
        _seed_debt("c1", "Sapphire", 4630.0)
        _seed_debt("c2", "Quiet Card", 0.0)
        state.account_details["c1"] = {"credit_limit": 10000.0}
        state.account_details["c2"] = {"credit_limit": 10000.0}

        out = await credit_health_service.build()

        assert out["overall_utilization_pct"] == 23.2
        assert out["overall_status"] == "good"
        assert out["cards_over_30"] == 1
        assert out["to_30_total"] == 1630.0
        assert out["to_10_total"] == 3630.0

    @pytest.mark.asyncio
    async def test_an_installment_loan_is_not_listed(self):
        """A mortgage rendered as a row with no percentage and an empty bar."""
        _seed_debt("c1", "Sapphire", 900.0)
        _seed_debt("m1", "Mortgage", 419391.99, subtype="loan")
        state.account_details["c1"] = {"credit_limit": 10000.0}

        out = await credit_health_service.build()

        assert [c["account_id"] for c in out["accounts"]] == ["c1"]



class TestBalanceProjection:
    @pytest.mark.asyncio
    async def test_a_growing_card_names_the_threshold_it_will_cross(self):
        # A manual account's stored ledger is its *starting* balance, so these
        # two transactions also carry it to 4600 — the figure the projection
        # is taken from.
        _seed_debt("c1", "Sapphire", 3000.0)
        state.account_details["c1"] = {"credit_limit": 10000.0}
        _card_txn("t1", "c1", "2026-07-04", 1700.0, "PRINCESS CRUISE RES")
        _card_txn("t2", "c1", "2026-07-20", 100.0, "Payment Received",
                  transaction_type="credit")

        card = (await credit_health_service.build())["accounts"][0]

        assert card["balance"] == 4600.0
        assert card["projection"]["net_change"] == 1600.0
        assert card["projection"]["projected_pct"] == 62.0
        assert card["projection"]["crosses"] == 50.0
        assert card["projection"]["months_to_limit"] == 3

    @pytest.mark.asyncio
    async def test_a_shrinking_card_gets_no_projection(self):
        """Nothing to warn about, and one month of history is far too thin to
        put a payoff date on."""
        _seed_debt("c1", "Sapphire", 4630.0)
        state.account_details["c1"] = {"credit_limit": 10000.0}
        _card_txn("t1", "c1", "2026-07-04", 100.0, "GROCERY STORE")
        _card_txn("t2", "c1", "2026-07-20", 2000.0, "Payment Received",
                  transaction_type="credit")

        card = (await credit_health_service.build())["accounts"][0]

        assert card["projection"] is None
        assert card["activity"]["latest"]["net_change"] == -1900.0

    @pytest.mark.asyncio
    async def test_growth_inside_the_current_band_crosses_nothing(self):
        _seed_debt("c1", "Sapphire", 500.0)
        state.account_details["c1"] = {"credit_limit": 10000.0}
        _card_txn("t1", "c1", "2026-07-04", 500.0, "GROCERY STORE")

        card = (await credit_health_service.build())["accounts"][0]

        # 10% today, 15% next month — still short of the 30% shelf.
        assert card["projection"]["crosses"] is None
        assert card["projection"]["projected_pct"] == 15.0



class TestCostBasisOverrides:
    """A user-entered average cost is joined into summarize_holdings at read
    time and stamped so a gain figure never hides where its basis came from."""

    def _holdings(self, avg):
        return [{
            "account_id": "a1", "symbol": "VTI", "asset_type": "etf",
            "quantity": 100.0, "average_purchase_price": avg,
            "market_value": 30000.0,
        }]

    def test_override_supplies_a_missing_provider_basis(self):
        repo = accounts_repo_memory.active()
        repo.set_cost_override("a1", "VTI", 210.0)

        row = analytics.summarize_holdings(self._holdings(None))["holdings"][0]

        assert row["cost_basis"] == 21000.0
        assert row["unrealized_gain"] == 9000.0
        assert row["cost_basis_source"] == "user"

    def test_override_wins_over_the_provider_value(self):
        repo = accounts_repo_memory.active()
        repo.set_cost_override("a1", "VTI", 210.0)

        summary = analytics.summarize_holdings(self._holdings(100.0))

        assert summary["holdings"][0]["cost_basis"] == 21000.0
        assert summary["total_cost"] == 21000.0
        assert summary["total_gain"] == 9000.0

    def test_provider_basis_is_labelled_provider(self):
        row = analytics.summarize_holdings(self._holdings(100.0))["holdings"][0]
        assert row["cost_basis_source"] == "provider"

    def test_no_basis_anywhere_leaves_the_source_unset(self):
        row = analytics.summarize_holdings(self._holdings(None))["holdings"][0]
        assert row["cost_basis"] is None
        assert row["cost_basis_source"] is None


def _month_start(months_back: int) -> date:
    d = date.today().replace(day=1)
    for _ in range(months_back):
        d = (d - timedelta(days=1)).replace(day=1)
    return d


def _seed_income(monthly: float) -> None:
    for i in range(1, 5):
        tid = f"pay_{i}"
        state.stored_transactions[tid] = {
            "id": tid, "date": (date.today() - timedelta(days=30 * i)).isoformat(),
            "description": "ACME PAYROLL DIRECT DEP", "amount": monthly,
            "category": "Income", "transaction_type": "credit",
            "direction": "inflow", "source": "simplefin",
        }


def _bill_date(months_back: int, day: int) -> date:
    start = _month_start(months_back)
    return start.replace(day=min(day, calendar.monthrange(start.year, start.month)[1]))


def _seed_recurring_charge(name: str, amount: float, day: int, months: int = 3) -> None:
    for m in range(1, months + 1):
        tid = f"rec_{name}_{m}"
        state.stored_transactions[tid] = {
            "id": tid, "date": _bill_date(m, day).isoformat(),
            "description": f"{name} PROPERTY MGMT", "amount": amount,
            "category": name, "transaction_type": "debit",
            "direction": "outflow", "source": "simplefin",
        }


_DISCRETIONARY_MERCHANTS = [
    ["CORNER DINER", "FUEL DEPOT", "GREEN GROCER"],
    ["RAMEN HOUSE", "HARDWARE BARN", "PET SUPPLY"],
    ["TAQUERIA SOL", "BOOK NOOK", "CINEMA WEST"],
    ["NOODLE BAR", "PAINT SHOP", "FLOWER CART"],
]


def _seed_one_off_spending(months: int, monthly: float) -> None:
    """One-off, non-recurring spend spread over ``months`` complete months.

    Each merchant appears exactly once so the recurring detector never claims
    any of it — this is the discretionary pool.
    """
    for m in range(1, months + 1):
        start = _month_start(m)
        for j, merchant in enumerate(_DISCRETIONARY_MERCHANTS[m - 1]):
            tid = f"disc_{m}_{j}"
            state.stored_transactions[tid] = {
                "id": tid, "date": (start + timedelta(days=5 + j * 5)).isoformat(),
                "description": merchant, "amount": round(monthly / 3.0, 2),
                "category": "Groceries", "transaction_type": "debit",
                "direction": "outflow", "source": "simplefin",
            }


class TestCashflowProjectionDiscretionary:
    def test_projection_subtracts_discretionary_spend(self, client):
        _seed_income(5000.0)
        _seed_recurring_charge("Rent", 1500.0, day=1)
        _seed_one_off_spending(months=3, monthly=1200.0)

        out = analytics.project_cashflow(horizon_days=30)

        assert out["expected_income"] == pytest.approx(5000.0, abs=1)
        assert out["expected_recurring_outflow"] == pytest.approx(1500.0, abs=1)
        assert out["expected_discretionary_outflow"] == pytest.approx(1200.0, abs=1)
        assert out["net"] == pytest.approx(2300.0, abs=1)   # not 3500
        assert out["discretionary_basis"]["confidence"] == "high"
        assert out["discretionary_basis"]["months"] == 3
        assert out["discretionary_basis"]["method"] == "median_of_complete_months"

    def test_recurring_spend_is_never_counted_twice(self, client):
        _seed_recurring_charge("Rent", 1500.0, day=1)

        out = analytics.project_cashflow(horizon_days=30)

        assert out["expected_discretionary_outflow"] == 0.0
        assert out["expected_recurring_outflow"] == pytest.approx(1500.0, abs=1)

    def test_median_ignores_one_holiday_month(self, client):
        _seed_one_off_spending(months=3, monthly=1200.0)
        # Blow out the oldest complete month; the median should not move.
        state.stored_transactions["blowout"] = {
            "id": "blowout", "date": (_month_start(3) + timedelta(days=20)).isoformat(),
            "description": "GIFT EMPORIUM", "amount": 4000.0,
            "category": "Shopping", "transaction_type": "debit",
            "direction": "outflow", "source": "simplefin",
        }

        out = analytics.project_cashflow(horizon_days=30)

        assert out["expected_discretionary_outflow"] == pytest.approx(1200.0, abs=1)

    def test_two_months_of_history_is_low_confidence(self, client):
        _seed_one_off_spending(months=2, monthly=900.0)

        basis = analytics.project_cashflow(horizon_days=30)["discretionary_basis"]

        assert basis["confidence"] == "low"
        assert basis["months"] == 2

    def test_one_month_omits_the_figure_and_flags_the_projection(self, client):
        _seed_one_off_spending(months=1, monthly=900.0)

        out = analytics.project_cashflow(horizon_days=30)

        assert out["discretionary_basis"]["confidence"] == "none"
        assert out["discretionary_basis"]["monthly"] is None
        assert out["projection_incomplete"] is True

    def test_horizon_scales_the_discretionary_figure(self, client):
        _seed_one_off_spending(months=3, monthly=1200.0)

        out = analytics.project_cashflow(horizon_days=60)

        assert out["expected_discretionary_outflow"] == pytest.approx(2400.0, abs=1)

    def test_bill_on_the_thirtieth_is_projected_on_the_thirtieth(self, client):
        _seed_recurring_charge("Storage", 60.0, day=30, months=3)

        bills = analytics.project_cashflow(horizon_days=60)["upcoming_bills"]

        assert bills
        assert all(b["estimated_date"][-2:] in ("28", "29", "30") for b in bills)
        assert any(b["estimated_date"].endswith("30") for b in bills)


class TestCashflowProjectionEndpoint:
    def test_endpoint_serves_the_waterfall(self, client):
        _seed_income(5000.0)
        _seed_recurring_charge("Rent", 1500.0, day=1)
        _seed_one_off_spending(months=3, monthly=1200.0)

        body = client.get("/api/cashflow/projection").json()

        assert body["horizon_days"] == 30
        assert body["expected_income"] == pytest.approx(5000.0, abs=1)
        assert body["expected_recurring_outflow"] == pytest.approx(1500.0, abs=1)
        assert body["expected_discretionary_outflow"] == pytest.approx(1200.0, abs=1)
        assert body["net"] == pytest.approx(2300.0, abs=1)
        assert body["discretionary_basis"]["confidence"] == "high"
        assert body["projection_incomplete"] is False

    def test_horizon_days_is_honoured(self, client):
        _seed_one_off_spending(months=3, monthly=1200.0)

        body = client.get("/api/cashflow/projection?horizon_days=60").json()

        assert body["horizon_days"] == 60
        assert body["expected_discretionary_outflow"] == pytest.approx(2400.0, abs=1)

    def test_horizon_days_outside_the_range_is_rejected(self, client):
        assert client.get("/api/cashflow/projection?horizon_days=0").status_code == 422
        assert client.get("/api/cashflow/projection?horizon_days=500").status_code == 422


class TestNegativeProjectionAlert:
    def test_negative_net_raises_a_hedged_alert(self, client):
        _seed_income(2000.0)
        _seed_recurring_charge("Rent", 1500.0, day=1)
        _seed_one_off_spending(months=3, monthly=840.0)

        feed = client.get("/api/alerts").json()["alerts"]
        alert = next(a for a in feed if a["category"] == "cashflow")

        assert "projected to exceed income by about $340" in alert["message"]
        assert "next 30 days" in alert["message"]
        assert alert["tab"] == "dashboard"

    def test_a_positive_projection_says_nothing(self, client):
        _seed_income(5000.0)
        _seed_recurring_charge("Rent", 1500.0, day=1)
        _seed_one_off_spending(months=3, monthly=1200.0)

        feed = client.get("/api/alerts").json()["alerts"]

        assert [a for a in feed if a["category"] == "cashflow"] == []


def _interest_row(tid, account_id, day, amount, description="INTEREST CHARGE-PURCHASES",
                  category=None, transaction_type="debit"):
    txn = {
        "id": tid, "date": day, "description": description, "amount": amount,
        "transaction_type": transaction_type, "account_id": account_id,
        "source": "simplefin",
    }
    if category is not None:
        txn["category"] = category
    state.stored_transactions[tid] = txn


class TestInterestHistory:
    """What carrying a balance has actually cost, month by month.

    Scoped by the transaction rather than the account. ``compute_card_activity``
    joins to the cards linked *now*, which is right for a per-card row and
    wrong for a history: the household replaced its Teller cards with SimpleFIN
    ones mid-year, and reading interest through the live account list threw
    away six months and made the cost look like it appeared from nowhere.
    """

    def test_interest_is_summed_per_month(self, client):
        _interest_row("i1", "cardA", "2026-06-09", 20.0)
        _interest_row("i2", "cardB", "2026-06-14", 12.5)
        _interest_row("i3", "cardA", "2026-07-09", 30.0)

        out = analytics.compute_interest_history(today=date(2026, 8, 15))

        assert out["months"] == [
            {"month": "2026-06", "interest": 32.5},
            {"month": "2026-07", "interest": 30.0},
        ]
        assert out["total_paid"] == 62.5

    def test_a_card_no_longer_linked_still_counts(self, client):
        """The money left the account whether or not the card is connected."""
        _interest_row("old", "acc_teller_gone", "2026-06-09", 26.38)
        _interest_row("new", "ACT-simplefin", "2026-07-03", 19.01)

        out = analytics.compute_interest_history(today=date(2026, 8, 15))

        assert [m["month"] for m in out["months"]] == ["2026-06", "2026-07"]
        assert out["total_paid"] == 45.39

    def test_a_csv_row_with_no_account_still_counts(self, client):
        _interest_row("csv", "", "05/04/2026", 6.50)

        out = analytics.compute_interest_history(today=date(2026, 8, 15))

        assert out["months"] == [{"month": "2026-05", "interest": 6.5}]

    def test_interest_earned_on_savings_is_not_interest_paid(self, client):
        """A deposit account posts its interest as an inflow. The direction
        guard is the whole defence — the description reads the same."""
        _interest_row("paid", "cardA", "2026-06-09", 20.0)
        _interest_row(
            "earned", "savings", "2026-06-01", 34.88,
            description="June interest charge", transaction_type="credit",
        )

        out = analytics.compute_interest_history(today=date(2026, 8, 15))

        assert out["total_paid"] == 20.0

    def test_the_running_month_is_excluded(self, client):
        """Most cards bill once, so a partial month is usually a zero that
        would read as the cost collapsing."""
        _interest_row("i1", "cardA", "2026-07-09", 30.0)
        _interest_row("i2", "cardA", "2026-08-09", 45.0)

        out = analytics.compute_interest_history(today=date(2026, 8, 20))

        assert [m["month"] for m in out["months"]] == ["2026-07"]

    def test_a_categorized_row_counts_without_the_description(self, client):
        _interest_row(
            "i1", "cardA", "2026-06-09", 26.38,
            description="FINANCE FEE", category="Interest",
        )

        out = analytics.compute_interest_history(today=date(2026, 8, 15))

        assert out["total_paid"] == 26.38

    def test_the_trend_reads_the_latest_against_the_months_before_it(self, client):
        _interest_row("i1", "cardA", "2026-05-09", 20.0)
        _interest_row("i2", "cardA", "2026-06-09", 20.0)
        _interest_row("i3", "cardA", "2026-07-09", 60.0)

        out = analytics.compute_interest_history(today=date(2026, 8, 15))

        assert out["trend"] == "rising"
        assert out["latest"] == 60.0
        assert out["highest"] == 60.0

    def test_one_quiet_month_does_not_make_the_next_a_rise(self, client):
        """A card cleared inside its grace period bills nothing; comparing only
        against that month would call every recovery a surge."""
        _interest_row("i1", "cardA", "2026-04-09", 40.0)
        _interest_row("i2", "cardA", "2026-05-09", 42.0)
        _interest_row("i3", "cardA", "2026-06-09", 1.0)
        _interest_row("i4", "cardA", "2026-07-09", 41.0)

        out = analytics.compute_interest_history(today=date(2026, 8, 15))

        assert out["trend"] == "steady"

    def test_a_falling_run_is_named(self, client):
        _interest_row("i1", "cardA", "2026-05-09", 60.0)
        _interest_row("i2", "cardA", "2026-06-09", 55.0)
        _interest_row("i3", "cardA", "2026-07-09", 10.0)

        assert analytics.compute_interest_history(
            today=date(2026, 8, 15)
        )["trend"] == "falling"

    def test_no_interest_anywhere_reports_nothing_rather_than_zero(self, client):
        out = analytics.compute_interest_history(today=date(2026, 8, 15))

        assert out["months"] == []
        assert out["total_paid"] == 0.0
        assert out["trend"] is None

    def test_only_the_most_recent_months_are_kept(self, client):
        for i, month in enumerate(("02", "03", "04", "05")):
            _interest_row(f"i{i}", "cardA", f"2026-{month}-09", 10.0)

        out = analytics.compute_interest_history(months=3, today=date(2026, 8, 15))

        assert [m["month"] for m in out["months"]] == ["2026-03", "2026-04", "2026-05"]
