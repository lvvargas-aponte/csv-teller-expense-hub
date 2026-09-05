"""Dashboard endpoint — chart-friendly aggregations.

Smoke-tests the GET /api/dashboard route that the Dashboard tab consumes.
"""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

import state
from analytics import _last_day_of_month
from db.base import sync_engine


def _insert_account(account_id: str, type_: str = "depository") -> None:
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO accounts (id, source, name, type, manual) "
                "VALUES (:id, 'manual', :id, :type, true) "
                "ON CONFLICT (id) DO UPDATE SET type = EXCLUDED.type"
            ),
            {"id": account_id, "type": type_},
        )


def _insert_snapshot(account_id: str, available: float, days_ago: float) -> None:
    captured = datetime.now(timezone.utc) - timedelta(days=days_ago)
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO balance_snapshots "
                "  (account_id, captured_at, available, ledger, source) "
                "VALUES (:aid, :ts, :avail, NULL, 'simplefin')"
            ),
            {"aid": account_id, "ts": captured, "avail": available},
        )


def _seed_txn(tid: str, date_str: str, category: str, amount: float) -> None:
    state.stored_transactions[tid] = {
        "id": tid,
        "transaction_id": tid,
        "date": date_str,
        "description": f"desc-{tid}",
        "amount": amount,
        "transaction_type": "debit",
        "category": category,
        "source": "simplefin",
        "is_shared": False,
    }


class TestEmptyState:
    def test_returns_empty_collections(self, client):
        r = client.get("/api/dashboard")
        assert r.status_code == 200
        body = r.json()
        assert body["months"] == []
        assert body["spending_by_month"] == {}
        assert body["monthly_totals"] == []
        assert body["net_worth_timeseries"] == []
        assert body["recurring_charges"] == []
        assert body["balance_trend"]["available"] is False


class TestMonthsClamping:
    def test_below_min_clamps_to_three(self, client):
        for i, m in enumerate(["2026-01", "2026-02", "2026-03", "2026-04"]):
            _seed_txn(f"t{i}", f"{m}-15", "Food", 10.0)
        r = client.get("/api/dashboard?months=1")
        assert r.status_code == 200
        assert len(r.json()["months"]) == 3

    def test_above_max_clamps_to_twelve(self, client):
        # 14 distinct months — only the last 12 should come back.
        months = [f"2025-{m:02d}" for m in range(1, 13)] + ["2026-01", "2026-02"]
        for i, m in enumerate(months):
            _seed_txn(f"t{i}", f"{m}-15", "Food", 10.0)
        r = client.get("/api/dashboard?months=99")
        assert r.status_code == 200
        assert len(r.json()["months"]) == 12


class TestSpendingShape:
    def test_spending_keys_are_subset_of_months(self, client):
        _seed_txn("a", "2026-03-15", "Food", 30.0)
        _seed_txn("b", "2026-03-20", "Travel", 70.0)
        _seed_txn("c", "2026-04-01", "Food", 25.0)

        r = client.get("/api/dashboard?months=6")
        body = r.json()
        assert set(body["spending_by_month"].keys()).issubset(set(body["months"]))
        totals_by_month = {row["month"]: row["total"] for row in body["monthly_totals"]}
        assert totals_by_month["2026-03"] == 100.0
        assert totals_by_month["2026-04"] == 25.0


class TestNetWorthTimeseries:
    def test_empty_when_no_snapshots(self, client):
        r = client.get("/api/dashboard?months=6")
        assert r.json()["net_worth_timeseries"] == []

    def test_returns_points_when_snapshots_exist(self, client):
        _insert_account("acc1", "depository")
        _insert_snapshot("acc1", 1000.0, days_ago=45)
        _insert_snapshot("acc1", 1500.0, days_ago=0.1)

        r = client.get("/api/dashboard?months=3")
        ts = r.json()["net_worth_timeseries"]
        assert len(ts) > 0
        # Most recent point should reflect the latest snapshot.
        assert ts[-1]["net_worth"] == 1500.0


class TestPartialMonthComparison:
    def test_dashboard_exposes_spend_comparison(self, client):
        body = client.get("/api/dashboard").json()
        assert "spend_comparison" in body
        comparison = body["spend_comparison"]
        for key in (
            "as_of_day", "current_month", "current_month_to_date",
            "prior_month", "prior_month_same_period", "prior_month_full",
            "delta", "pct_change", "current_month_is_partial",
        ):
            assert key in comparison

    def test_income_rows_flag_the_partial_month(self, client):
        today = date.today()
        current = f"{today.year:04d}-{today.month:02d}"
        prior_last = date(today.year, today.month, 1) - timedelta(days=1)
        prior = f"{prior_last.year:04d}-{prior_last.month:02d}"

        _seed_txn("p", f"{prior}-05", "Food", 40.0)
        _seed_txn("c", f"{current}-01", "Food", 25.0)

        rows = client.get("/api/dashboard/income-vs-expenses").json()["rows"]
        by_month = {row["month"]: row for row in rows}
        assert by_month[prior]["is_partial"] is False
        assert by_month[current]["is_partial"] == (
            today.day < _last_day_of_month(today)
        )


def _seed_inflow(
    tid: str, date_str: str, amount: float, description: str,
    account_type: str = "checking", account_id: str = "", category: str = "",
) -> None:
    state.stored_transactions[tid] = {
        "id": tid,
        "transaction_id": tid,
        "date": date_str,
        "description": description,
        "amount": amount,
        "transaction_type": "credit",
        "account_type": account_type,
        "account_id": account_id,
        "category": category,
        "source": "simplefin",
        "is_shared": False,
    }


def _seed_outflow(tid: str, date_str: str, amount: float, description: str,
                  category: str = "") -> None:
    state.stored_transactions[tid] = {
        "id": tid,
        "transaction_id": tid,
        "date": date_str,
        "description": description,
        "amount": amount,
        "transaction_type": "debit",
        "category": category,
        "source": "simplefin",
        "is_shared": False,
    }


def _prior_month() -> str:
    today = date.today()
    last = date(today.year, today.month, 1) - timedelta(days=1)
    return f"{last.year:04d}-{last.month:02d}"


class TestIncomeIsNotEveryInflow:
    """The endpoint used to define income itself instead of reusing the
    detector's test, and its version asked whether ``account_type`` contained
    the word "credit". SimpleFIN puts the account's *display name* in that
    field, so "Amazon Prime Rewards Visa Signature (5637)" passed and every
    card payment counted as household income — $15,148 reported for a month
    whose real payroll was $8,238.
    """

    def test_a_card_payment_is_not_income(self, client):
        month = _prior_month()
        _seed_inflow("pay", f"{month}-03", 3844.55, "ACME PAYROLL")
        _seed_inflow(
            "cardpmt", f"{month}-15", 2953.03, "ONLINE/MOBILE PAYMENT CONF#z1",
            account_type="Customized Cash Rewards Visa Signature (7473)",
        )

        rows = client.get("/api/dashboard/income-vs-expenses").json()["rows"]
        by_month = {r["month"]: r for r in rows}

        assert by_month[month]["income"] == 3844.55

    def test_a_p2p_transfer_is_not_income(self, client):
        month = _prior_month()
        _seed_inflow("pay", f"{month}-03", 3844.55, "ACME PAYROLL")
        _seed_inflow("p2p", f"{month}-10", 1000.0, "LUZ VARGAS P2P")
        _seed_inflow("zelle", f"{month}-12", 1305.93, "Zelle payment from A B")

        rows = client.get("/api/dashboard/income-vs-expenses").json()["rows"]
        by_month = {r["month"]: r for r in rows}

        assert by_month[month]["income"] == 3844.55


class TestCardPaymentsAreNotSpending:
    """A card payment moves money between the household's own accounts; the
    spending it settles was counted when each purchase posted to the card.
    Counting the payment too reports the same money twice — $3,395 of one
    month's $12,555, which is what drove the savings rate to -50%.
    """

    def test_an_uncategorized_card_payment_is_not_spending(self, client):
        month = _prior_month()
        _seed_outflow("buy", f"{month}-04", 120.0, "GROCERY STORE")
        _seed_outflow("pmt", f"{month}-20", 2953.03, "BANK OF AMERICA PAYMENT z1i7ub")

        rows = client.get("/api/dashboard/income-vs-expenses").json()["rows"]
        by_month = {r["month"]: r for r in rows}

        assert by_month[month]["expenses"] == 120.0

    def test_a_miscategorized_card_payment_is_not_spending(self, client):
        """These rows often carry a wrong category rather than none — the real
        data files "BANK OF AMERICA PAYMENT" under Service — so a category is
        no evidence the row is real spending."""
        month = _prior_month()
        _seed_outflow("buy", f"{month}-04", 120.0, "GROCERY STORE")
        _seed_outflow(
            "pmt", f"{month}-20", 1722.92,
            "Payment to Chase card ending in 5637", category="General",
        )

        rows = client.get("/api/dashboard/income-vs-expenses").json()["rows"]
        by_month = {r["month"]: r for r in rows}

        assert by_month[month]["expenses"] == 120.0

    def test_a_loan_payment_is_still_spending(self, client):
        """Nothing was counted when the mortgage was drawn, so unlike a card
        payment it has no purchase side to double — it must keep counting."""
        month = _prior_month()
        _seed_outflow("mtg", f"{month}-05", 3053.14, "TRUIST MORTG OLB MTGPMT 4008583934 WEB")

        rows = client.get("/api/dashboard/income-vs-expenses").json()["rows"]
        by_month = {r["month"]: r for r in rows}

        assert by_month[month]["expenses"] == 3053.14

    def test_a_real_bill_carrying_the_word_payment_still_counts(self, client):
        month = _prior_month()
        _seed_outflow("ins", f"{month}-06", 86.48, "PROG PREMIER INS PREM XXXXX1773")
        _seed_outflow("util", f"{month}-08", 83.88, "CITYOFRALUTIL BILLPAY PPD ID: 000")

        rows = client.get("/api/dashboard/income-vs-expenses").json()["rows"]
        by_month = {r["month"]: r for r in rows}

        assert by_month[month]["expenses"] == 170.36
