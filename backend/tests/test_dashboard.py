"""Dashboard endpoint — chart-friendly aggregations.

Smoke-tests the GET /api/dashboard route that the Dashboard tab consumes.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

import state
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
                "VALUES (:aid, :ts, :avail, NULL, 'teller')"
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
        "source": "teller",
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
