"""Income / paycheck detection — PR2 of the data-gap initiative.

Pins the heuristic that turns recurring inbound credits on depository
accounts into an ``income`` block on the financial snapshot. The advisor
relies on this block to stop asking "what's your income?" on every chat.

Tests construct ``state.stored_transactions`` directly — no DB reads, no
SimpleFIN calls — so the suite stays fast and deterministic.
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
    source: str = "simplefin",
    category: str = "",
    account_id: str = "",
) -> None:
    # Every field is set here rather than patched onto the row afterwards: a
    # PgStore item read returns a SNAPSHOT, so `state.stored_transactions[t]
    # ["category"] = x` looks like it worked and changes nothing.
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    state.stored_transactions[tid] = {
        "transaction_id": tid,
        "id": tid,
        "date": d,
        "description": description,
        "amount": amount,
        "transaction_type": "credit",
        "account_type": account_type,
        "account_id": account_id,
        "source": source,
        "is_shared": False,
        "category": category,
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
        "source": "simplefin",
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


class TestOutlierDepositsAreTrimmedNotFatal:
    """A salary is a stream with the occasional odd deposit in it.

    The predecessor rule judged a group by ``(max - min) / mean`` and threw the
    whole thing away above 0.15 — the most outlier-sensitive statistic
    available for the job. One $872.21 adjustment beside a normal $3,889.73
    took a real 18-paycheque salary to a 0.91 spread and disqualified it,
    after which the only stream regular enough to survive was a $1,000
    recurring P2P transfer. Income read a quarter of its true value at "high"
    confidence, and fed the savings rate, DTI, the health score and the
    advisor's snapshot.
    """

    def test_one_odd_deposit_does_not_disqualify_a_salary(self):
        for i, days_ago in enumerate([88, 74, 60, 46, 32, 18, 4]):
            _add_credit(f"p{i}", "NATERA INC PAYROLL", 3844.55, days_ago)
        # Same day as a normal cheque: an adjustment, not a pay period.
        _add_credit("odd", "NATERA INC PAYROLL", 872.21, 60)

        from analytics import detect_recurring_income
        sources = detect_recurring_income()

        assert len(sources) == 1
        assert sources[0]["cadence_days"] == 14
        assert sources[0]["monthly_estimate"] == pytest.approx(8238.32, rel=0.01)

    def test_the_odd_deposit_is_reported_rather_than_hidden(self):
        for i, days_ago in enumerate([60, 46, 32, 18, 4]):
            _add_credit(f"p{i}", "NATERA INC PAYROLL", 3844.55, days_ago)
        _add_credit("odd", "NATERA INC PAYROLL", 872.21, 60)

        from analytics import detect_recurring_income
        source = detect_recurring_income()[0]

        # The average is taken over the paycheques, not dragged down by the
        # stray, and the count reflects what the estimate was built from.
        assert source["average_amount"] == 3844.55
        assert source["occurrences"] == 5
        assert source["deposits_ignored"] == 1

    def test_a_raise_mid_stream_still_reads_as_one_salary(self):
        """3752 → 3889 → 4225 is a real progression, all inside the band."""
        for i, days_ago in enumerate([74, 60]):
            _add_credit(f"a{i}", "ACME PAYROLL", 3752.20, days_ago)
        for i, days_ago in enumerate([46, 32]):
            _add_credit(f"b{i}", "ACME PAYROLL", 3889.73, days_ago)
        for i, days_ago in enumerate([18, 4]):
            _add_credit(f"c{i}", "ACME PAYROLL", 4225.24, days_ago)

        from analytics import detect_recurring_income
        sources = detect_recurring_income()

        assert len(sources) == 1
        assert sources[0]["occurrences"] == 6
        assert sources[0]["deposits_ignored"] == 0

    def test_a_genuinely_lumpy_stream_still_fails(self):
        """Trimming must not turn irregular work into a salary: once the
        strays are dropped too few rows are left to call it recurring."""
        _add_credit("g1", "FREELANCE DEPOSIT", 300.0, 74)
        _add_credit("g2", "FREELANCE DEPOSIT", 1500.0, 60)
        _add_credit("g3", "FREELANCE DEPOSIT", 800.0, 46)
        _add_credit("g4", "FREELANCE DEPOSIT", 2400.0, 32)

        from analytics import detect_recurring_income
        assert detect_recurring_income() == []


class TestCardPaymentsAreNotIncome:
    """A payment posts to the card as an inflow, and is not a paycheque.

    ``account_type`` alone could not catch it: Teller sets ``credit_card``,
    but SimpleFIN puts the account's display name there — "Amazon Prime
    Rewards Visa Signature (5637)" contains no "credit", so a substring test
    let every SimpleFIN card payment through.
    """

    def test_a_simplefin_card_payment_is_excluded_by_account_id(self):
        state._manual_accounts["cardacct"] = {
            "id": "cardacct", "institution": "Chase",
            "name": "Amazon Prime Rewards Visa Signature (5637)",
            "type": "credit", "subtype": "credit_card",
            "available": 0.0, "ledger": 438.68, "manual": True,
        }
        for i, days_ago in enumerate([60, 30, 1]):
            _add_credit(
                f"cp{i}", "AUTOMATIC PAYMENT - THANK", 344.21, days_ago,
                account_type="Amazon Prime Rewards Visa Signature (5637)",
                account_id="cardacct",
            )

        from analytics import detect_recurring_income
        assert detect_recurring_income() == []

    def test_a_categorized_card_payment_is_excluded_without_an_account(self):
        for i, days_ago in enumerate([60, 30, 1]):
            _add_credit(
                f"cp{i}", "ONLINE/MOBILE PAYMENT", 500.0, days_ago,
                category="CC Payment",
            )

        from analytics import detect_recurring_income
        assert detect_recurring_income() == []


class TestBareP2PIsNotIncome:
    def test_a_p2p_transfer_is_excluded(self):
        """The exclusion listed the platforms — venmo, zelle, cashapp,
        paypal — so a description saying "P2P" outright walked past it."""
        for i, days_ago in enumerate([60, 46, 32, 18, 4]):
            _add_credit(f"t{i}", "LUZ VARGAS P2P", 1000.0, days_ago)

        from analytics import detect_recurring_income
        assert detect_recurring_income() == []
