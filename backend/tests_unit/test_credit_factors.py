"""Credit factors — the levers, never a guessed score.

The one factor this app measures well is utilization, and most tools get it
wrong: a bureau sees the balance on the *statement* date, not today's and not
the post-payment one. Everything here is measured on connected accounts only,
and nothing rolls into a composite number.
"""
from datetime import date, timedelta

import pytest

import credit_factors
import state
from db import accounts_repo_memory


def _set_account_details(account_id, **fields):
    state.account_details[account_id] = {"account_id": account_id, **fields}


def _card(account_id="card1", name="Sapphire", ledger=0.0, subtype=""):
    state._manual_accounts[account_id] = {
        "id": account_id, "institution": "Bank", "name": name,
        "type": "credit", "subtype": subtype,
        "available": 0.0, "ledger": ledger, "manual": True,
    }


def _snapshot(account_id, ledger, captured_at):
    accounts_repo_memory.active().insert_balance_snapshot(
        account_id=account_id, source="manual", available=0.0,
        ledger=ledger, captured_at=captured_at,
    )


def _account_row(account_id, type_="credit", subtype=""):
    accounts_repo_memory.active().upsert_manual_account(
        account_id=account_id, institution="Bank", name=account_id,
        type_=type_, subtype=subtype,
    )


def _inflow(tid, account_id, day, amount=200.0):
    state.stored_transactions[tid] = {
        "id": tid, "date": day, "description": "PAYMENT THANK YOU",
        "amount": amount, "category": "Credit Card Payment",
        "transaction_type": "credit", "direction": "inflow",
        "account_id": account_id, "source": "manual",
    }


class TestReportedUtilization:
    @pytest.mark.asyncio
    async def test_reported_utilization_uses_the_statement_date_snapshot(self):
        # Card with a $10,000 limit, statement cuts on the 14th.
        # Snapshot on the 14th: $5,200 owed. Today (the 25th): $900 owed.
        _card("card1", ledger=900.0)
        _account_row("card1")
        _set_account_details("card1", credit_limit=10000.0, statement_day=14)
        _snapshot("card1", ledger=5200.0, captured_at="2026-08-14T06:00:00")
        _snapshot("card1", ledger=900.0, captured_at="2026-08-25T06:00:00")

        out = await credit_factors.compute(today=date(2026, 8, 25))
        card = out["utilization"]["cards"][0]

        assert card["reported_pct"] == 52.0   # what the bureau sees
        assert card["current_pct"] == 9.0     # what the user sees today
        assert card["as_of"] == "2026-08-14"

    @pytest.mark.asyncio
    async def test_a_snapshot_within_tolerance_still_counts(self):
        """Refreshes don't land on the statement day to the hour."""
        _card("card1", ledger=900.0)
        _account_row("card1")
        _set_account_details("card1", credit_limit=10000.0, statement_day=14)
        _snapshot("card1", ledger=5200.0, captured_at="2026-08-16T06:00:00")

        out = await credit_factors.compute(today=date(2026, 8, 25))

        assert out["utilization"]["cards"][0]["reported_pct"] == 52.0
        assert out["utilization"]["cards"][0]["as_of"] == "2026-08-16"

    @pytest.mark.asyncio
    async def test_no_snapshot_near_the_statement_day_reports_nothing(self):
        """Substituting today's balance would be a different number entirely."""
        _card("card1", ledger=900.0)
        _account_row("card1")
        _set_account_details("card1", credit_limit=10000.0, statement_day=14)
        _snapshot("card1", ledger=900.0, captured_at="2026-08-25T06:00:00")

        out = await credit_factors.compute(today=date(2026, 8, 25))
        card = out["utilization"]["cards"][0]

        assert card["reported_pct"] is None
        assert card["as_of"] is None
        assert card["current_pct"] == 9.0

    @pytest.mark.asyncio
    async def test_the_overall_figures_carry_both_readings(self):
        _card("card1", ledger=900.0)
        _account_row("card1")
        _set_account_details("card1", credit_limit=10000.0, statement_day=14)
        _snapshot("card1", ledger=5200.0, captured_at="2026-08-14T06:00:00")

        util = (await credit_factors.compute(today=date(2026, 8, 25)))["utilization"]

        assert util["overall_reported_pct"] == 52.0
        assert util["overall_current_pct"] == 9.0
        assert util["cards_over_30"] == 1
        assert util["all_cards_at_zero"] is False


class TestUtilizationLever:
    @pytest.mark.asyncio
    async def test_the_lever_says_what_to_pay_and_by_when(self):
        _card("card1", ledger=5200.0)
        _account_row("card1")
        _set_account_details("card1", credit_limit=10000.0, statement_day=14)
        _snapshot("card1", ledger=5200.0, captured_at="2026-08-14T06:00:00")

        card = (await credit_factors.compute(today=date(2026, 8, 25)))["utilization"]["cards"][0]

        # 5200 - 3000 = 2200 to land on 30% of a 10k limit, by the next cut.
        assert card["lever"]["amount"] == 2200.0
        assert card["lever"]["gets_to_pct"] == 30.0
        assert card["lever"]["pay_by"] == "2026-09-14"

    @pytest.mark.asyncio
    async def test_a_card_already_under_thirty_needs_no_lever(self):
        _card("card1", ledger=1000.0)
        _account_row("card1")
        _set_account_details("card1", credit_limit=10000.0, statement_day=14)
        _snapshot("card1", ledger=1000.0, captured_at="2026-08-14T06:00:00")

        card = (await credit_factors.compute(today=date(2026, 8, 25)))["utilization"]["cards"][0]

        assert card["lever"] is None


class TestPaymentTimeliness:
    @pytest.mark.asyncio
    async def test_counts_only_cycles_it_can_see(self):
        _card("card1", ledger=900.0)
        _account_row("card1")
        _set_account_details("card1", credit_limit=10000.0, statement_day=14, due_day=14)
        _inflow("p1", "card1", "2026-07-10")
        _inflow("p2", "card1", "2026-06-30")   # paid after the June due day

        timeliness = (await credit_factors.compute(today=date(2026, 8, 25)))["payment_timeliness"]

        assert timeliness["cycles_observed"] == 2
        assert timeliness["cycles_with_payment_before_due"] == 1
        assert timeliness["latest"][0]["cycle"] == "2026-07"

    @pytest.mark.asyncio
    async def test_no_payments_seen_is_zero_observed_not_a_clean_record(self):
        _card("card1", ledger=900.0)
        _account_row("card1")
        _set_account_details("card1", credit_limit=10000.0, due_day=14)

        timeliness = (await credit_factors.compute(today=date(2026, 8, 25)))["payment_timeliness"]

        assert timeliness["cycles_observed"] == 0
        assert timeliness["cycles_with_payment_before_due"] == 0


class TestHistoryMixAndNewCredit:
    @pytest.mark.asyncio
    async def test_age_is_measured_only_over_accounts_that_have_a_date(self):
        _card("card1", ledger=100.0)
        _card("card2", name="Old Card", ledger=100.0)
        _card("card3", name="Undated", ledger=100.0)
        for aid in ("card1", "card2", "card3"):
            _account_row(aid)
        _set_account_details("card1", credit_limit=1000.0, opened_on="2024-08-25")
        _set_account_details("card2", credit_limit=1000.0, opened_on="2016-08-25")
        _set_account_details("card3", credit_limit=1000.0)

        history = (await credit_factors.compute(today=date(2026, 8, 25)))["history"]

        assert history["average_age_months"] == 72     # (24 + 120) / 2
        assert history["oldest_account_months"] == 120
        assert history["accounts_missing_opened_on"] == 1

    @pytest.mark.asyncio
    async def test_recently_opened_accounts_are_counted(self):
        _card("card1", ledger=100.0)
        _card("card2", name="New Card", ledger=100.0)
        _account_row("card1")
        _account_row("card2")
        recent = (date(2026, 8, 25) - timedelta(days=60)).isoformat()
        _set_account_details("card1", credit_limit=1000.0, opened_on="2016-08-25")
        _set_account_details("card2", credit_limit=1000.0, opened_on=recent)

        out = await credit_factors.compute(today=date(2026, 8, 25))

        assert out["new_credit"]["opened_last_12_months"] == 1

    @pytest.mark.asyncio
    async def test_mix_separates_revolving_from_installment(self):
        _card("card1", ledger=100.0)
        _card("auto", name="Auto Loan", ledger=18000.0, subtype="loan")
        _account_row("card1")
        _account_row("auto", subtype="loan")

        mix = (await credit_factors.compute(today=date(2026, 8, 25)))["mix"]

        assert mix["revolving"] == 1
        assert mix["installment"] == 1


class TestNoScoreIsEverProduced:
    @pytest.mark.asyncio
    async def test_the_payload_carries_no_composite_number(self):
        """A score is a model fit to a bureau file. This is not that file."""
        _card("card1", ledger=900.0)
        _account_row("card1")
        _set_account_details("card1", credit_limit=10000.0, statement_day=14)

        out = await credit_factors.compute(today=date(2026, 8, 25))

        forbidden = {"score", "estimated_score", "score_range", "grade", "rating"}
        assert forbidden.isdisjoint(out)
        assert out["coverage_note"] == "Measured on 1 connected account."


class TestCreditFactorsEndpoint:
    def test_endpoint_returns_the_factor_payload(self, client):
        _card("card1", ledger=900.0)
        _account_row("card1")
        _set_account_details("card1", credit_limit=10000.0, statement_day=14)

        r = client.get("/api/accounts/credit-factors")

        assert r.status_code == 200
        body = r.json()
        assert set(body) == {
            "utilization", "payment_timeliness", "history",
            "new_credit", "mix", "coverage_note",
        }
