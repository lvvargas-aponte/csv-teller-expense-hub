"""Retirement contribution detection and the projection built on it."""
from datetime import datetime, timedelta, timezone

import pytest

import retirement
import state
from db import accounts_repo_memory


def _seed_investment(account_id, name, value, subtype="ira"):
    state._manual_accounts[account_id] = {
        "id": account_id, "institution": "Fidelity", "name": name,
        "type": "investment", "subtype": subtype,
        "available": value, "ledger": value, "manual": True,
    }
    accounts_repo_memory.active().upsert_manual_account(
        account_id=account_id, institution="Fidelity", name=name,
        type_="investment", subtype=subtype,
    )


def _seed_checking(account_id="chk", value=5000.0):
    state._manual_accounts[account_id] = {
        "id": account_id, "institution": "Bank", "name": "Checking",
        "type": "depository", "subtype": "checking",
        "available": value, "ledger": value, "manual": True,
    }


def _tagged_transfer(txn_id, date_str, amount, destination, source_account="chk"):
    state.stored_transactions[txn_id] = {
        "id": txn_id, "date": date_str, "description": "FIDELITY ROTH CONTRIB",
        "amount": amount, "account_id": source_account,
        "account_type": "depository", "direction": "outflow",
        "transfer_to_account_id": destination,
    }


def _snapshot(account_id, value, days_ago):
    accounts_repo_memory.active().insert_balance_snapshot(
        account_id=account_id, source="simplefin", available=value,
        ledger=value,
        captured_at=(datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
    )


class TestEstimateContributions:
    @pytest.mark.asyncio
    async def test_tagged_recurring_transfer_into_a_roth_is_a_contribution(self):
        _seed_checking()
        _seed_investment("roth1", "Fidelity Roth IRA", 42000.0, subtype="roth_ira")
        _tagged_transfer("t1", "2026-06-01", 500.0, "roth1")
        _tagged_transfer("t2", "2026-07-01", 500.0, "roth1")
        _tagged_transfer("t3", "2026-08-01", 500.0, "roth1")

        out = await retirement.estimate_contributions()

        row = next(r for r in out["by_account"] if r["account_id"] == "roth1")
        assert row["method"] == "recurring_transfer"
        assert row["confidence"] == "high"
        assert row["monthly"] == pytest.approx(500.0, rel=0.05)
        assert out["monthly_total"] == pytest.approx(500.0, rel=0.05)
        assert out["confidence"] == "high"

    @pytest.mark.asyncio
    async def test_rising_snapshots_with_no_transactions_are_caught_by_velocity(self):
        _seed_investment("k401", "Employer 401(k)", 130000.0, subtype="401k")
        _snapshot("k401", 124000.0, days_ago=60)
        _snapshot("k401", 130000.0, days_ago=1)

        out = await retirement.estimate_contributions()

        row = next(r for r in out["by_account"] if r["account_id"] == "k401")
        assert row["method"] == "snapshot_velocity"
        assert row["confidence"] == "low"
        assert row["monthly"] > 0
        assert out["confidence"] == "low"
        assert "market movement" in out["caveat"].lower()

    @pytest.mark.asyncio
    async def test_one_snapshot_yields_no_estimate_rather_than_zero(self):
        _seed_investment("k401", "Employer 401(k)", 130000.0, subtype="401k")
        _snapshot("k401", 130000.0, days_ago=1)

        out = await retirement.estimate_contributions()

        assert out["by_account"] == []
        assert out["monthly_total"] == 0.0
        assert out["confidence"] == "none"

    @pytest.mark.asyncio
    async def test_transfers_win_over_velocity_for_the_same_account(self):
        """Both signals describe the same dollars; summing them double-counts."""
        _seed_checking()
        _seed_investment("roth1", "Fidelity Roth IRA", 42000.0, subtype="roth_ira")
        _tagged_transfer("t1", "2026-06-01", 500.0, "roth1")
        _tagged_transfer("t2", "2026-07-01", 500.0, "roth1")
        _snapshot("roth1", 40000.0, days_ago=60)
        _snapshot("roth1", 42000.0, days_ago=1)

        out = await retirement.estimate_contributions()

        rows = [r for r in out["by_account"] if r["account_id"] == "roth1"]
        assert len(rows) == 1
        assert rows[0]["method"] == "recurring_transfer"
        assert out["monthly_total"] == pytest.approx(500.0, rel=0.05)
