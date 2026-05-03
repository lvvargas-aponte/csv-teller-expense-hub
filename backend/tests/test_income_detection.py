"""Income / paycheck detection — PR2 of the data-gap initiative.

Pins the heuristic that turns recurring inbound credits on depository
accounts into an ``income`` block on the financial snapshot. The advisor
relies on this block to stop asking "what's your income?" on every chat.

Tests construct ``state.stored_transactions`` directly — no DB reads, no
Teller calls — so the suite stays fast and deterministic.
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


def _add_debit(tid: str, description: str, amount: float, days_ago: int) -> None:
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    state.stored_transactions[tid] = {
        "transaction_id": tid,
        "id": tid,
        "date": d,
        "description": description,
        "amount": amount,
        "transaction_type": "debit",
        "account_type": "depository",
        "source": "teller",
        "is_shared": False,
        "category": "",
        "notes": "",
    }


class TestDetectRecurringIncome:
    def test_biweekly_paycheck_detected_with_correct_cadence(self):
        # 4 paychecks across ~6 weeks, 14-day cadence, $2000 each.
        for i, days_ago in enumerate([60, 46, 32, 18, 4]):
            _add_credit(f"p{i}", "EMPLOYER ACME PAYROLL", 2000.0, days_ago)

        from analytics import detect_recurring_income
        sources = detect_recurring_income()
        assert len(sources) == 1
        s = sources[0]
        assert s["average_amount"] == 2000.0
        assert s["occurrences"] == 5
        assert s["cadence_days"] == 14
        # 30 / 14 * 2000 ≈ 4285.71
        assert s["monthly_estimate"] == pytest.approx(4285.71, rel=0.01)

    def test_monthly_paycheck_collapses_to_average(self):
        for i, days_ago in enumerate([90, 60, 30, 1]):
            _add_credit(f"p{i}", "ACME CORP DIRECT DEP", 5000.0, days_ago)

        from analytics import detect_recurring_income
        sources = detect_recurring_income()
        assert len(sources) == 1
        assert sources[0]["cadence_days"] in (29, 30, 31)
        assert sources[0]["monthly_estimate"] == pytest.approx(5000.0, rel=0.05)

    def test_high_variance_inbound_is_rejected(self):
        # Side-gig deposits that swing $300–$1500 are not stable income.
        _add_credit("g1", "FREELANCE TRANSFER", 300.0, 60)
        _add_credit("g2", "FREELANCE TRANSFER", 1500.0, 30)
        _add_credit("g3", "FREELANCE TRANSFER", 800.0, 5)

        from analytics import detect_recurring_income
        assert detect_recurring_income() == []

    def test_single_occurrence_is_rejected(self):
        _add_credit("once", "ONE-OFF GIFT", 500.0, 10)
        from analytics import detect_recurring_income
        assert detect_recurring_income() == []

    def test_credit_card_payments_are_excluded(self):
        # A credit-card account receiving payments would look like a paycheck
        # without the account_type filter.
        _add_credit(
            "cc1", "PAYMENT THANK YOU", 1500.0, 30,
            account_type="credit_card",
        )
        _add_credit(
            "cc2", "PAYMENT THANK YOU", 1500.0, 5,
            account_type="credit_card",
        )
        from analytics import detect_recurring_income
        assert detect_recurring_income() == []

    def test_discover_credits_are_excluded(self):
        # Discover CSVs use transaction_type='credit' for purchases — the
        # filter rejects the source outright.
        _add_credit("d1", "STARBUCKS", 4.50, 30, source="discover")
        _add_credit("d2", "STARBUCKS", 4.50, 5, source="discover")
        from analytics import detect_recurring_income
        assert detect_recurring_income() == []

    def test_debits_are_ignored(self):
        _add_debit("e1", "EMPLOYER ACME", 2000.0, 30)
        _add_debit("e2", "EMPLOYER ACME", 2000.0, 5)
        from analytics import detect_recurring_income
        assert detect_recurring_income() == []


class TestComputeIncomeEstimate:
    def test_no_sources_returns_none_confidence(self):
        from analytics import compute_income_estimate
        out = compute_income_estimate()
        assert out["monthly_estimate"] == 0.0
        assert out["sources"] == []
        assert out["confidence"] == "none"

    def test_high_confidence_when_three_plus_occurrences_two_months(self):
        for i, days_ago in enumerate([60, 46, 32, 18, 4]):
            _add_credit(f"p{i}", "ACME PAYROLL", 2000.0, days_ago)

        from analytics import compute_income_estimate
        out = compute_income_estimate()
        assert out["confidence"] == "high"
        assert out["monthly_estimate"] > 0
        assert len(out["sources"]) == 1

    def test_low_confidence_with_only_two_recent_paychecks(self):
        # Both within the same calendar month → only 1 month_seen, only 2
        # occurrences → low confidence.
        _add_credit("p1", "NEW JOB PAYROLL", 3000.0, 14)
        _add_credit("p2", "NEW JOB PAYROLL", 3000.0, 0)
        from analytics import compute_income_estimate
        out = compute_income_estimate()
        assert out["confidence"] == "low"
        assert out["monthly_estimate"] > 0

    def test_sources_capped_at_top_three(self):
        # Five distinct stable income streams; only the top 3 are returned.
        for n, label in enumerate(["A", "B", "C", "D", "E"]):
            for i, days_ago in enumerate([60, 32, 4]):
                _add_credit(
                    f"{label}{i}",
                    f"EMPLOYER {label} PAYROLL",
                    1000.0 + n * 500,
                    days_ago,
                )

        from analytics import compute_income_estimate
        out = compute_income_estimate()
        assert len(out["sources"]) == 3
        # Sources ordered by monthly_estimate desc.
        amounts = [s["monthly_estimate"] for s in out["sources"]]
        assert amounts == sorted(amounts, reverse=True)


class TestSnapshotIntegration:
    def test_income_block_present_in_snapshot(self):
        from analytics import build_financial_snapshot
        snap = build_financial_snapshot()
        assert "income" in snap
        assert snap["income"]["confidence"] == "none"
        assert snap["income"]["monthly_estimate"] == 0.0

    def test_income_block_populated_when_paychecks_seeded(self):
        for i, days_ago in enumerate([60, 46, 32, 18, 4]):
            _add_credit(f"p{i}", "ACME PAYROLL", 2000.0, days_ago)

        from analytics import build_financial_snapshot
        snap = build_financial_snapshot()
        assert snap["income"]["confidence"] == "high"
        assert snap["income"]["monthly_estimate"] > 4000
        assert len(snap["income"]["sources"]) == 1
