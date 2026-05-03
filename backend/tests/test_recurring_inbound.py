"""Recurring inbound-transfer detection — PR4 of the data-gap initiative.

The advisor uses ``recurring_inbound_transfers`` to reconcile actual P2P
flows (Venmo, Zelle, Cash App, PayPal, reimbursements) against the
shared-split owe table. Tests focus on three behaviors:

1. P2P credits are picked up regardless of amount variance up to ±50 %.
2. Paychecks (no P2P keyword) stay in income, never in transfers.
3. P2P credits are *excluded* from income detection so a roommate's rent
   share doesn't double-count as household paycheck.
"""
from datetime import date, timedelta

import pytest

import state


@pytest.fixture(autouse=True)
def _clear_txns():
    state.stored_transactions.clear()
    yield
    state.stored_transactions.clear()


def _add_credit(
    tid: str,
    description: str,
    amount: float,
    days_ago: int,
    account_type: str = "depository",
    source: str = "teller",
) -> None:
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    state.stored_transactions[tid] = {
        "transaction_id": tid,
        "id": tid,
        "date": d,
        "description": description,
        "amount": amount,
        "transaction_type": "credit",
        "account_type": account_type,
        "source": source,
        "is_shared": False,
        "category": "",
        "notes": "",
    }


class TestDetectInboundTransfers:
    def test_recurring_venmo_detected(self):
        for i, days_ago in enumerate([60, 30, 1]):
            _add_credit(f"v{i}", "VENMO PAYMENT FROM ROOMMATE", 850.0, days_ago)

        from analytics import detect_recurring_inbound_transfers
        out = detect_recurring_inbound_transfers()
        assert len(out) == 1
        s = out[0]
        assert s["occurrences"] == 3
        assert s["average_amount"] == 850.0
        assert s["total_received"] == 2550.0
        assert s["cadence_days"] in (29, 30, 31)

    def test_zelle_with_amount_variance_within_tolerance(self):
        # Real rent splits vary because utilities are split too.
        _add_credit("z1", "ZELLE FROM ALICE", 600.0, 60)
        _add_credit("z2", "ZELLE FROM ALICE", 850.0, 30)
        _add_credit("z3", "ZELLE FROM ALICE", 720.0, 1)

        from analytics import detect_recurring_inbound_transfers
        out = detect_recurring_inbound_transfers()
        assert len(out) == 1
        assert out[0]["occurrences"] == 3

    def test_huge_variance_rejected(self):
        # A single $5000 outlier blows past the 50% spread cap.
        _add_credit("v1", "VENMO ANOTHER ROOMMATE", 100.0, 60)
        _add_credit("v2", "VENMO ANOTHER ROOMMATE", 100.0, 30)
        _add_credit("v3", "VENMO ANOTHER ROOMMATE", 5000.0, 1)

        from analytics import detect_recurring_inbound_transfers
        assert detect_recurring_inbound_transfers() == []

    def test_single_occurrence_rejected(self):
        _add_credit("v1", "VENMO ONE TIME", 100.0, 5)
        from analytics import detect_recurring_inbound_transfers
        assert detect_recurring_inbound_transfers() == []

    def test_paycheck_without_p2p_keyword_not_detected(self):
        for i, days_ago in enumerate([60, 46, 32, 18, 4]):
            _add_credit(f"p{i}", "ACH DIRECT DEP ACME PAYROLL", 2000.0, days_ago)
        from analytics import detect_recurring_inbound_transfers
        assert detect_recurring_inbound_transfers() == []


class TestIncomeExcludesP2P:
    def test_recurring_venmo_does_not_count_as_income(self):
        # Without the P2P exclusion, this would hit income detection's
        # tighter spread tolerance and be flagged as a paycheck.
        for i, days_ago in enumerate([60, 30, 1]):
            _add_credit(f"v{i}", "VENMO ROOMMATE RENT", 850.0, days_ago)

        from analytics import compute_income_estimate, detect_recurring_inbound_transfers
        income = compute_income_estimate()
        transfers = detect_recurring_inbound_transfers()

        assert income["confidence"] == "none"
        assert income["monthly_estimate"] == 0.0
        # Same flow shows up as a transfer instead.
        assert len(transfers) == 1

    def test_paycheck_alongside_venmo_only_paycheck_counts_as_income(self):
        for i, days_ago in enumerate([60, 46, 32, 18, 4]):
            _add_credit(f"p{i}", "ACME PAYROLL", 2000.0, days_ago)
        for i, days_ago in enumerate([60, 30, 1]):
            _add_credit(f"v{i}", "VENMO ROOMMATE", 800.0, days_ago)

        from analytics import compute_income_estimate, detect_recurring_inbound_transfers
        income = compute_income_estimate()
        transfers = detect_recurring_inbound_transfers()
        assert income["monthly_estimate"] > 4000      # paycheck only
        assert len(income["sources"]) == 1
        assert "ACME" in income["sources"][0]["sample_description"]
        assert len(transfers) == 1


class TestSnapshotIntegration:
    def test_inbound_transfers_block_in_snapshot(self):
        for i, days_ago in enumerate([60, 30, 1]):
            _add_credit(f"v{i}", "VENMO ROOMMATE RENT", 800.0, days_ago)

        from analytics import build_financial_snapshot
        snap = build_financial_snapshot()
        assert "recurring_inbound_transfers" in snap
        assert len(snap["recurring_inbound_transfers"]) == 1

    def test_block_present_even_with_no_transfers(self):
        from analytics import build_financial_snapshot
        snap = build_financial_snapshot()
        assert snap["recurring_inbound_transfers"] == []
