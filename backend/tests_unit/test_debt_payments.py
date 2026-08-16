"""Tests for matching transactions to a debt's payoff progress."""
from debt_payments import debt_payment_progress, match_keywords

DEBT_ID = "acct_synchrony"
TRUIST_ID = "acct_truist"

CARD_META = {
    "name": "Credit Cards CARECREDIT / SYNCHRONY BANK (0742)",
    "institution": "Synchrony",
    "type": "credit",
    "ledger": -15465.0,
}

DETAILS = {
    "payoff_start_balance": 15985.0,
    "payoff_start_date": "2026-08-01",
    "payment_account_id": TRUIST_ID,
}


def _txn(tid, account_id, amount, ttype, date, description, institution=""):
    return {
        "transaction_id": tid,
        "id": tid,
        "account_id": account_id,
        "amount": amount,
        "transaction_type": ttype,
        "date": date,
        "description": description,
        "institution": institution,
    }


class TestMatchKeywords:
    def test_picks_distinctive_tokens_and_drops_generic_ones(self):
        kws = match_keywords(CARD_META["name"], CARD_META["institution"])
        assert "CARECREDIT" in kws
        assert "SYNCHRONY" in kws
        # These would match half the ledger.
        assert "CREDIT" not in kws
        assert "BANK" not in kws
        assert "CARDS" not in kws

    def test_short_tokens_are_ignored(self):
        assert "AND" not in match_keywords("Bob and Co", "")

    def test_no_duplicates(self):
        kws = match_keywords("SYNCHRONY SYNCHRONY", "Synchrony")
        assert kws.count("SYNCHRONY") == 1


class TestProgress:
    def test_reports_progress_from_balances_not_payment_sum(self):
        # One $520 payment, but the balance only moved $520 — interest would
        # show up as a gap between the two figures.
        txns = [_txn("t1", TRUIST_ID, 520.0, "debit", "2026-08-06",
                     "CARECREDIT/SYNCB PAYMENT", "Truist")]
        out = debt_payment_progress(DEBT_ID, DETAILS, CARD_META, txns)

        assert out["start_balance"] == 15985.0
        assert out["current_balance"] == 15465.0
        assert out["paid_down"] == 520.0
        assert out["percent_paid"] == 3.25
        assert out["total_payments"] == 520.0

    def test_matches_funding_side_debit_by_description(self):
        txns = [
            _txn("t1", TRUIST_ID, 520.0, "debit", "2026-08-06",
                 "CARECREDIT/SYNCB PAYMENT", "Truist"),
            _txn("t2", TRUIST_ID, 82.0, "debit", "2026-08-07", "STARBUCKS", "Truist"),
        ]
        out = debt_payment_progress(DEBT_ID, DETAILS, CARD_META, txns)
        assert out["payment_count"] == 1
        assert out["payments"][0]["transaction_id"] == "t1"

    def test_card_side_credit_counts_as_a_payment(self):
        txns = [_txn("c1", DEBT_ID, 520.0, "credit", "2026-08-08", "PAYMENT THANK YOU")]
        out = debt_payment_progress(DEBT_ID, DETAILS, CARD_META, txns)
        assert out["payment_count"] == 1
        assert out["payments"][0]["source"] == "account"

    def test_both_sides_of_one_payment_reconcile_to_a_single_row(self):
        txns = [
            _txn("t1", TRUIST_ID, 520.0, "debit", "2026-08-06",
                 "CARECREDIT/SYNCB PAYMENT", "Truist"),
            _txn("c1", DEBT_ID, 520.0, "credit", "2026-08-08", "PAYMENT THANK YOU"),
        ]
        out = debt_payment_progress(DEBT_ID, DETAILS, CARD_META, txns)
        assert out["payment_count"] == 1
        assert out["total_payments"] == 520.0
        payment = out["payments"][0]
        assert payment["source"] == "both"
        # The funding-side row is the one the user recognises.
        assert payment["transaction_id"] == "t1"
        assert payment["posted_date"] == "2026-08-08"

    def test_far_apart_sides_are_not_reconciled(self):
        txns = [
            _txn("t1", TRUIST_ID, 520.0, "debit", "2026-08-06",
                 "CARECREDIT/SYNCB PAYMENT", "Truist"),
            _txn("c1", DEBT_ID, 520.0, "credit", "2026-09-20", "PAYMENT THANK YOU"),
        ]
        out = debt_payment_progress(DEBT_ID, DETAILS, CARD_META, txns)
        assert out["payment_count"] == 2

    def test_two_identical_payments_stay_two(self):
        txns = [
            _txn("t1", TRUIST_ID, 520.0, "debit", "2026-08-06", "CARECREDIT", "Truist"),
            _txn("t2", TRUIST_ID, 520.0, "debit", "2026-08-07", "CARECREDIT", "Truist"),
            _txn("c1", DEBT_ID, 520.0, "credit", "2026-08-08", "PAYMENT"),
            _txn("c2", DEBT_ID, 520.0, "credit", "2026-08-09", "PAYMENT"),
        ]
        out = debt_payment_progress(DEBT_ID, DETAILS, CARD_META, txns)
        assert out["payment_count"] == 2
        assert out["total_payments"] == 1040.0
        assert all(p["source"] == "both" for p in out["payments"])

    def test_payments_before_the_start_date_are_excluded(self):
        txns = [
            _txn("old", TRUIST_ID, 300.0, "debit", "2026-07-01", "CARECREDIT", "Truist"),
            _txn("t1", TRUIST_ID, 520.0, "debit", "2026-08-06", "CARECREDIT", "Truist"),
        ]
        out = debt_payment_progress(DEBT_ID, DETAILS, CARD_META, txns)
        assert out["payment_count"] == 1
        assert out["total_payments"] == 520.0

    def test_spending_on_the_card_is_not_a_payment(self):
        txns = [_txn("d1", DEBT_ID, 200.0, "debit", "2026-08-10", "DENTIST VISIT")]
        out = debt_payment_progress(DEBT_ID, DETAILS, CARD_META, txns)
        assert out["payment_count"] == 0

    def test_unrelated_funding_account_debits_are_ignored(self):
        txns = [_txn("x", "acct_other", 520.0, "debit", "2026-08-06", "CARECREDIT")]
        out = debt_payment_progress(DEBT_ID, DETAILS, CARD_META, txns)
        assert out["payment_count"] == 0

    def test_works_with_no_details_configured(self):
        txns = [_txn("c1", DEBT_ID, 520.0, "credit", "2026-08-08", "PAYMENT")]
        out = debt_payment_progress(DEBT_ID, None, CARD_META, txns)
        assert out["start_balance"] is None
        assert out["paid_down"] is None
        assert out["percent_paid"] is None
        # The card side still works without a configured funding account.
        assert out["payment_count"] == 1

    def test_unparseable_dates_are_skipped_not_fatal(self):
        txns = [
            _txn("bad", DEBT_ID, 100.0, "credit", "not-a-date", "PAYMENT"),
            _txn("c1", DEBT_ID, 520.0, "credit", "2026-08-08", "PAYMENT"),
        ]
        out = debt_payment_progress(DEBT_ID, DETAILS, CARD_META, txns)
        assert out["payment_count"] == 1

    def test_percent_paid_clamps_when_balance_exceeds_start(self):
        meta = {**CARD_META, "ledger": -20000.0}
        out = debt_payment_progress(DEBT_ID, DETAILS, meta, [])
        assert out["paid_down"] == -4015.0
        assert out["percent_paid"] == 0.0
