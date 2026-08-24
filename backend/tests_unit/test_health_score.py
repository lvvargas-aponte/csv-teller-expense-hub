"""Financial health score v2 — the signals an advisor actually assesses.

v1 weighted month-over-month spending noise at 40% and had no emergency-fund
coverage, no savings rate and no debt-to-income in it at all. Each signal here
is pinned at both endpoints of its curve, so a change to the model shows up as
a failing number rather than a silent drift in a score users anchor on.
"""
from datetime import datetime, timedelta, timezone

import pytest

import health_service
import state
from db import accounts_repo_memory


def _ratios(**over):
    """The compute_ratios payload, with every signal available by default."""
    base = {
        "income": {
            "monthly": 8000.0, "source": "profile", "confidence": "high",
            "detected_monthly": None, "profile_monthly": 8000.0,
        },
        "savings_rate_pct": 20.0,
        "monthly_expenses": 6000.0,
        "emergency_fund": {
            "cash": 36000.0, "months_covered": 6.0, "target_months": 6, "gap": 0.0,
        },
        "monthly_debt_payments": 0.0,
        "dti_pct": 0.0,
        "as_of": "2026-08-24",
    }
    base.update(over)
    return base


def _fund(months_covered, target_months=6):
    return _ratios(emergency_fund={
        "cash": 0.0, "months_covered": months_covered,
        "target_months": target_months, "gap": None,
    })


def _credit(pct):
    return {
        "accounts": [{"account_id": "c1"}] if pct is not None else [],
        "total_balance": 0.0, "total_limit": 10000.0,
        "overall_utilization_pct": pct, "overall_status": "good",
    }


def _trend(delta_90d, net_worth=100000.0):
    if delta_90d is None:
        return {"available": False, "reason": "no balance snapshots yet"}
    return {
        "available": True, "current_net_worth": net_worth,
        "delta_90d": delta_90d, "label": "stable",
    }


class TestRunwaySignal:
    def test_full_target_scores_one(self):
        assert health_service._runway_signal(_fund(6.0))["sub_score"] == 1.0

    def test_beyond_target_is_capped(self):
        assert health_service._runway_signal(_fund(11.0))["sub_score"] == 1.0

    def test_no_cushion_scores_zero(self):
        assert health_service._runway_signal(_fund(0.0))["sub_score"] == 0.0

    def test_half_the_target_scores_half(self):
        assert health_service._runway_signal(_fund(3.0))["sub_score"] == 0.5

    def test_unavailable_without_spending_history(self):
        signal = health_service._runway_signal(_fund(None))
        assert signal["available"] is False
        assert signal["weight"] == 25


class TestSavingsRateSignal:
    def test_twenty_percent_scores_one(self):
        assert health_service._savings_signal(_ratios(savings_rate_pct=20.0))["sub_score"] == 1.0

    def test_saving_nothing_scores_zero(self):
        assert health_service._savings_signal(_ratios(savings_rate_pct=0.0))["sub_score"] == 0.0

    def test_spending_more_than_earned_scores_zero_not_negative(self):
        assert health_service._savings_signal(_ratios(savings_rate_pct=-30.0))["sub_score"] == 0.0

    def test_ten_percent_scores_half(self):
        assert health_service._savings_signal(_ratios(savings_rate_pct=10.0))["sub_score"] == 0.5

    def test_unavailable_without_income(self):
        signal = health_service._savings_signal(_ratios(savings_rate_pct=None))
        assert signal["available"] is False
        assert signal["weight"] == 25


class TestUtilizationSignal:
    def test_nothing_owed_scores_one(self):
        assert health_service._utilization_signal(_credit(0.0))["sub_score"] == 1.0

    def test_eighty_percent_scores_zero(self):
        assert health_service._utilization_signal(_credit(80.0))["sub_score"] == 0.0

    def test_beyond_eighty_stays_zero(self):
        assert health_service._utilization_signal(_credit(140.0))["sub_score"] == 0.0

    def test_forty_percent_scores_half(self):
        assert health_service._utilization_signal(_credit(40.0))["sub_score"] == 0.5

    def test_unavailable_without_a_rated_card(self):
        signal = health_service._utilization_signal(_credit(None))
        assert signal["available"] is False
        assert signal["weight"] == 20


class TestDebtToIncomeSignal:
    def test_fifteen_percent_scores_one(self):
        assert health_service._dti_signal(_ratios(dti_pct=15.0))["sub_score"] == 1.0

    def test_no_debt_scores_one(self):
        assert health_service._dti_signal(_ratios(dti_pct=0.0))["sub_score"] == 1.0

    def test_the_lending_ceiling_scores_zero(self):
        assert health_service._dti_signal(_ratios(dti_pct=43.0))["sub_score"] == 0.0

    def test_beyond_the_ceiling_stays_zero(self):
        assert health_service._dti_signal(_ratios(dti_pct=60.0))["sub_score"] == 0.0

    def test_midway_scores_half(self):
        assert health_service._dti_signal(_ratios(dti_pct=29.0))["sub_score"] == 0.5

    def test_unavailable_without_income(self):
        signal = health_service._dti_signal(_ratios(dti_pct=None))
        assert signal["available"] is False
        assert signal["weight"] == 15


class TestNetWorthTrendSignal:
    def test_growing_five_percent_scores_one(self):
        assert health_service._trend_signal(_trend(5000.0))["sub_score"] == 1.0

    def test_shrinking_five_percent_scores_zero(self):
        assert health_service._trend_signal(_trend(-5000.0))["sub_score"] == 0.0

    def test_flat_scores_half(self):
        assert health_service._trend_signal(_trend(0.0))["sub_score"] == 0.5

    def test_reads_the_ninety_day_window(self):
        """30-day deltas on a household balance sheet are mostly paycheck timing."""
        trend = {"available": True, "current_net_worth": 100000.0,
                 "delta_30d": 5000.0, "label": "rising"}
        assert health_service._trend_signal(trend)["available"] is False

    def test_unavailable_without_snapshots(self):
        signal = health_service._trend_signal(_trend(None))
        assert signal["available"] is False
        assert signal["weight"] == 15


class TestComposedScore:
    @pytest.fixture(autouse=True)
    def _stub_inputs(self, monkeypatch):
        """Each input has its own tests above; compose them here."""
        self.ratios = _ratios()
        self.credit = _credit(0.0)
        self.trend = _trend(0.0)

        async def fake_ratios(today=None):
            return self.ratios

        async def fake_credit():
            return self.credit

        monkeypatch.setattr(health_service, "compute_ratios", fake_ratios)
        monkeypatch.setattr(health_service.credit_health_service, "build", fake_credit)
        monkeypatch.setattr(
            health_service.analytics, "compute_balance_trend", lambda: self.trend
        )

    @pytest.mark.asyncio
    async def test_a_solid_household_scores_well(self):
        """Target runway, a 20% savings rate and no debt."""
        self.ratios = _ratios()          # runway 6/6, savings 20%, DTI 0%
        self.credit = _credit(0.0)
        self.trend = _trend(0.0)         # flat net worth — the only middling signal

        out = await health_service.compute_health_score()

        assert out["version"] == 2
        assert out["score"] >= 85
        assert out["coverage_pct"] == 100.0
        assert out["missing_signals"] == []

    @pytest.mark.asyncio
    async def test_weights_are_renormalized_over_available_signals(self):
        self.credit = _credit(None)      # no rated card — 20 weight drops out
        self.trend = _trend(None)        # no snapshots — 15 drops out

        out = await health_service.compute_health_score()

        assert out["coverage_pct"] == 65.0
        assert set(out["missing_signals"]) == {"credit_utilization", "net_worth_trend"}
        # runway 1.0*25 + savings 1.0*25 + dti 1.0*15, all over 65.
        assert out["score"] == 100

    @pytest.mark.asyncio
    async def test_a_thin_household_scores_badly(self):
        self.ratios = _ratios(
            savings_rate_pct=0.0, dti_pct=43.0,
            emergency_fund={"cash": 0.0, "months_covered": 0.0,
                            "target_months": 6, "gap": 36000.0},
        )
        self.credit = _credit(80.0)
        self.trend = _trend(-5000.0)

        out = await health_service.compute_health_score()

        assert out["score"] == 0
        assert out["coverage_pct"] == 100.0

    @pytest.mark.asyncio
    async def test_no_score_below_half_coverage(self):
        """One input is not a household assessment — say what is missing instead."""
        self.ratios = _ratios(
            savings_rate_pct=None, dti_pct=None,
            emergency_fund={"cash": 0.0, "months_covered": None,
                            "target_months": 3, "gap": None},
        )
        self.credit = _credit(10.0)      # 20 of 100 weight
        self.trend = _trend(None)

        out = await health_service.compute_health_score()

        assert out["score"] is None
        assert out["coverage_pct"] == 20.0
        assert set(out["missing_signals"]) == {
            "emergency_runway", "savings_rate", "debt_to_income", "net_worth_trend",
        }

    @pytest.mark.asyncio
    async def test_every_signal_carries_a_readable_detail(self):
        out = await health_service.compute_health_score()
        for signal in out["signals"]:
            assert signal["detail"]
            assert signal["label"]


class TestScoreEndpoint:
    def test_endpoint_returns_the_service_payload(self, client):
        repo = accounts_repo_memory.active()
        repo.upsert_manual_account(
            account_id="a1", institution="Bank", name="Checking", type_="depository",
        )
        now = datetime.now(timezone.utc)
        repo.insert_balance_snapshot(
            account_id="a1", source="manual", available=1000.0,
            captured_at=(now - timedelta(days=100)).isoformat(),
        )
        repo.insert_balance_snapshot(
            account_id="a1", source="manual", available=1010.0,
            captured_at=now.isoformat(),
        )
        state.stored_transactions.clear()

        r = client.get("/api/health/score")

        assert r.status_code == 200
        body = r.json()
        assert body["version"] == 2
        assert {s["key"] for s in body["signals"]} == {
            "emergency_runway", "savings_rate", "credit_utilization",
            "debt_to_income", "net_worth_trend",
        }
        assert "coverage_pct" in body
