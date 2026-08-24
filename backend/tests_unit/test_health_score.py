"""Financial health score — parity with the JS that used to live in FinancesPage.

Every expectation here is hand-computed from the old ``computeHealthScore``
weights (30 net worth / 30 utilization / 40 spending, renormalized over the
signals that have data), so a change in the arithmetic shows up as a failing
number rather than a silent drift.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

import health_service
import state
from db import accounts_repo_memory


def _seed_net_worth_signal():
    """1000 → 1010 over 45 days: delta_30d = 10 on a 1010 base.

    sub = 0.5 + (10 / 1010) * 5 = 0.549505
    """
    repo = accounts_repo_memory.active()
    repo.upsert_manual_account(
        account_id="a1", institution="Bank", name="Checking", type_="depository",
    )
    now = datetime.now(timezone.utc)
    repo.insert_balance_snapshot(
        account_id="a1", source="manual", available=1000.0,
        captured_at=(now - timedelta(days=45)).isoformat(),
    )
    repo.insert_balance_snapshot(
        account_id="a1", source="manual", available=1010.0,
        captured_at=now.isoformat(),
    )


def _seed_maxed_out_card():
    """A card at 100% utilization — sub_score 0.0 on a 30-weight signal."""
    state._manual_accounts["c1"] = {
        "id": "c1", "name": "Card", "institution": "Bank",
        "type": "credit", "ledger": 500.0, "available": 0.0, "manual": True,
    }
    state.account_details["c1"] = {"credit_limit": 500.0}


def _seed_spending_signal():
    """$100 in the prior month vs. $120 so far this one → sub = 0.5 - 0.2."""
    today = date.today()
    prior_last = date(today.year, today.month, 1) - timedelta(days=1)
    for tid, day, amount in (
        ("p", f"{prior_last.year:04d}-{prior_last.month:02d}-01", 100.0),
        ("c", f"{today.year:04d}-{today.month:02d}-01", 120.0),
    ):
        state.stored_transactions[tid] = {
            "id": tid, "date": day, "description": "MERCHANT", "amount": amount,
            "category": "Dining", "transaction_type": "debit",
            "direction": "outflow", "source": "simplefin",
        }


class TestScoreParity:
    @pytest.mark.asyncio
    async def test_score_is_none_when_no_signals_available(self):
        out = await health_service.compute_health_score()
        assert out["score"] is None
        assert set(out["missing_signals"]) == {
            "net_worth_trend", "credit_utilization", "spending_trend",
        }

    @pytest.mark.asyncio
    async def test_net_worth_only(self):
        _seed_net_worth_signal()

        out = await health_service.compute_health_score()

        assert out["score"] == 55          # 0.549505 * 30 / 30 * 100
        assert out["version"] == 1
        assert set(out["missing_signals"]) == {"credit_utilization", "spending_trend"}
        signal = next(s for s in out["signals"] if s["key"] == "net_worth_trend")
        assert signal["weight"] == 30
        assert signal["available"] is True
        assert round(signal["sub_score"], 6) == 0.549505

    @pytest.mark.asyncio
    async def test_net_worth_plus_utilization(self):
        _seed_net_worth_signal()
        _seed_maxed_out_card()

        out = await health_service.compute_health_score()

        # (0.549505 * 30 + 0.0 * 30) / 60 * 100
        assert out["score"] == 27
        assert out["missing_signals"] == ["spending_trend"]
        util = next(s for s in out["signals"] if s["key"] == "credit_utilization")
        assert util["sub_score"] == 0.0
        assert util["weight"] == 30

    @pytest.mark.asyncio
    async def test_all_three_signals(self):
        _seed_net_worth_signal()
        _seed_maxed_out_card()
        _seed_spending_signal()

        out = await health_service.compute_health_score()

        # (0.549505 * 30 + 0.0 * 30 + 0.3 * 40) / 100 * 100
        assert out["score"] == 28
        assert out["missing_signals"] == []
        spend = next(s for s in out["signals"] if s["key"] == "spending_trend")
        assert round(spend["sub_score"], 6) == 0.3
        assert spend["weight"] == 40


class TestScoreEndpoint:
    def test_endpoint_returns_the_service_payload(self, client):
        _seed_net_worth_signal()

        r = client.get("/api/health/score")

        assert r.status_code == 200
        body = r.json()
        assert body["score"] == 55
        assert body["version"] == 1
        assert {s["key"] for s in body["signals"]} == {
            "net_worth_trend", "credit_utilization", "spending_trend",
        }
