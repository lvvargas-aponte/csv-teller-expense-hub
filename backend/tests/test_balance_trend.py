"""Balance trajectory in the financial snapshot.

PR1 of the data-gap initiative: surfaces 30/60/90-day net-worth deltas
plus a short trend label so the advisor can frame answers around
direction, not just the current scalar.

Tests seed real ``balance_snapshots`` rows (via the live Postgres test
DB) so the SQL ``get_snapshots_since`` window logic is exercised
end-to-end.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

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


def _insert_snapshot(
    account_id: str,
    available: float | None,
    ledger: float | None,
    days_ago: float,
) -> None:
    captured = datetime.now(timezone.utc) - timedelta(days=days_ago)
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO balance_snapshots "
                "  (account_id, captured_at, available, ledger, source) "
                "VALUES (:aid, :ts, :avail, :ledger, 'teller')"
            ),
            {
                "aid": account_id,
                "ts": captured,
                "avail": available,
                "ledger": ledger,
            },
        )


class TestEmptyHistory:
    def test_no_snapshots_returns_unavailable(self):
        from analytics import compute_balance_trend
        out = compute_balance_trend()
        assert out["available"] is False
        assert "reason" in out


class TestDeltas:
    def test_thirty_day_delta_against_single_account(self):
        _insert_account("acc1", "depository")
        _insert_snapshot("acc1", available=10000.0, ledger=None, days_ago=45)
        _insert_snapshot("acc1", available=10500.0, ledger=None, days_ago=15)
        _insert_snapshot("acc1", available=11000.0, ledger=None, days_ago=0.1)

        from analytics import compute_balance_trend
        out = compute_balance_trend()
        assert out["available"] is True
        assert out["current_net_worth"] == 11000.0
        # Latest snapshot at-or-before "30 days ago" is the 45-days-ago row.
        assert out["net_worth_30d_ago"] == 10000.0
        assert out["delta_30d"] == 1000.0
        # 90 days ago precedes any snapshot we have → key omitted, not zero.
        assert "net_worth_90d_ago" not in out

    def test_combines_cash_and_credit(self):
        _insert_account("cash1", "depository")
        _insert_account("card1", "credit")
        # 45 days ago: cash 5000, credit owed 1000 → net 4000
        _insert_snapshot("cash1", available=5000.0, ledger=None, days_ago=45)
        _insert_snapshot("card1", available=None, ledger=1000.0, days_ago=45)
        # Today: cash 6000, credit owed 800 → net 5200
        _insert_snapshot("cash1", available=6000.0, ledger=None, days_ago=0.1)
        _insert_snapshot("card1", available=None, ledger=800.0, days_ago=0.1)

        from analytics import compute_balance_trend
        out = compute_balance_trend()
        assert out["current_net_worth"] == 5200.0
        assert out["net_worth_30d_ago"] == 4000.0
        assert out["delta_30d"] == 1200.0


class TestLabel:
    def test_rising_label_when_delta_is_positive(self):
        _insert_account("acc1", "depository")
        _insert_snapshot("acc1", available=10000.0, ledger=None, days_ago=45)
        _insert_snapshot("acc1", available=10800.0, ledger=None, days_ago=0.1)

        from analytics import compute_balance_trend
        out = compute_balance_trend()
        # +800 / 10800 ≈ 7.4 % → "rising fast"
        assert out["label"] == "rising fast"

    def test_declining_label_when_delta_is_negative(self):
        _insert_account("acc1", "depository")
        _insert_snapshot("acc1", available=10000.0, ledger=None, days_ago=45)
        _insert_snapshot("acc1", available=9000.0, ledger=None, days_ago=0.1)

        from analytics import compute_balance_trend
        out = compute_balance_trend()
        # -1000 / 9000 ≈ -11 % → "declining fast"
        assert out["label"] == "declining fast"

    def test_stable_label_within_one_percent(self):
        _insert_account("acc1", "depository")
        _insert_snapshot("acc1", available=10000.0, ledger=None, days_ago=45)
        _insert_snapshot("acc1", available=10050.0, ledger=None, days_ago=0.1)

        from analytics import compute_balance_trend
        out = compute_balance_trend()
        # +50 / 10050 ≈ 0.5 % → "stable"
        assert out["label"] == "stable"


class TestSnapshotIntegration:
    def test_balance_trend_appears_in_full_snapshot(self):
        _insert_account("acc1", "depository")
        _insert_snapshot("acc1", available=10000.0, ledger=None, days_ago=45)
        _insert_snapshot("acc1", available=10500.0, ledger=None, days_ago=0.1)

        from analytics import build_financial_snapshot
        snap = build_financial_snapshot()
        assert "balance_trend" in snap
        assert snap["balance_trend"]["available"] is True
        assert snap["balance_trend"]["current_net_worth"] == 10500.0

    def test_balance_trend_block_present_even_with_no_history(self):
        from analytics import build_financial_snapshot
        snap = build_financial_snapshot()
        assert "balance_trend" in snap
        assert snap["balance_trend"]["available"] is False


class TestSinceWindowFiltering:
    @pytest.mark.asyncio
    async def test_repo_only_returns_recent_snapshots(self):
        _insert_account("acc1", "depository")
        _insert_snapshot("acc1", available=1.0, ledger=None, days_ago=200)
        _insert_snapshot("acc1", available=2.0, ledger=None, days_ago=15)

        from db.accounts_repo import get_repo
        rows = get_repo().get_snapshots_since(91)
        # Only the 15-day-old row falls within the 91-day window.
        assert len(rows) == 1
        assert rows[0]["available"] == 2.0
