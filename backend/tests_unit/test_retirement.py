"""Retirement contribution detection and the projection built on it."""
from datetime import date, datetime, timedelta, timezone

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


def _fake_contributions(monthly):
    async def _f():
        return {
            "monthly_total": monthly, "by_account": [],
            "confidence": "high" if monthly else "none", "caveat": None,
        }
    return _f


def _set_profile(monkeypatch, **fields):
    monkeypatch.setattr(retirement, "_load_profile", lambda: fields or None)


def _seed_real_asset(account_id, value):
    state._manual_accounts[account_id] = {
        "id": account_id, "institution": "-", "name": "House",
        "type": "asset", "subtype": "residence",
        "available": value, "ledger": value, "manual": True,
    }


class TestProjection:
    @pytest.mark.asyncio
    async def test_projection_compounds_in_real_terms(self, monkeypatch):
        # $100k now, $1,000/mo, 24 years, 6% nominal - 2.5% inflation = 3.5% real
        # FV = 100000*(1.035^24) + 1000*12*[(1.035^24 - 1)/0.035]  ~= 665,000
        _set_profile(
            monkeypatch, birth_year=1990, target_retirement_age=60,
            annual_retirement_spend=60000.0, risk_tolerance="balanced",
        )
        _seed_investment("k401", "Employer 401(k)", 100000.0, subtype="401k")
        monkeypatch.setattr(
            retirement, "estimate_contributions", _fake_contributions(1000.0)
        )

        out = await retirement.project(today=date(2026, 1, 1))

        assert out["available"] is True
        assert out["years_to_retirement"] == 24
        assert out["current_balance"] == 100000.0
        assert out["scenarios"]["base"] == pytest.approx(665_000, rel=0.01)
        assert out["target_pot"] == 1_500_000.0
        assert out["assumptions"]["real_return_pct"] == 3.5
        assert out["assumptions"]["nominal_return_pct"] == 6.0
        assert out["assumptions"]["inflation_pct"] == 2.5
        assert out["assumptions"]["withdrawal_rate_pct"] == 4.0
        assert out["assumptions"]["source"] == "risk_tolerance"
        assert out["missing"] == []

    @pytest.mark.asyncio
    async def test_three_scenarios_bracket_the_base_case(self, monkeypatch):
        _set_profile(
            monkeypatch, birth_year=1990, target_retirement_age=60,
            annual_retirement_spend=60000.0, risk_tolerance="balanced",
        )
        _seed_investment("k401", "Employer 401(k)", 100000.0, subtype="401k")
        monkeypatch.setattr(
            retirement, "estimate_contributions", _fake_contributions(1000.0)
        )

        out = await retirement.project(today=date(2026, 1, 1))

        assert out["scenarios"]["low"] < out["scenarios"]["base"]
        assert out["scenarios"]["base"] < out["scenarios"]["high"]
        assert out["base_shortfall"] == pytest.approx(
            1_500_000 - out["scenarios"]["base"], abs=1
        )
        assert out["low_shortfall"] > out["base_shortfall"]

    @pytest.mark.asyncio
    async def test_required_monthly_closes_the_base_case_gap(self, monkeypatch):
        _set_profile(
            monkeypatch, birth_year=1990, target_retirement_age=60,
            annual_retirement_spend=60000.0, risk_tolerance="balanced",
        )
        _seed_investment("k401", "Employer 401(k)", 100000.0, subtype="401k")
        monkeypatch.setattr(
            retirement, "estimate_contributions", _fake_contributions(1000.0)
        )

        out = await retirement.project(today=date(2026, 1, 1))
        required = out["required_monthly_for_target"]

        monkeypatch.setattr(
            retirement, "estimate_contributions", _fake_contributions(required)
        )
        rerun = await retirement.project(today=date(2026, 1, 1))
        assert rerun["scenarios"]["base"] == pytest.approx(1_500_000, rel=0.001)

    @pytest.mark.asyncio
    async def test_expected_return_override_wins_over_risk_tolerance(self, monkeypatch):
        _set_profile(
            monkeypatch, birth_year=1990, target_retirement_age=60,
            annual_retirement_spend=60000.0, risk_tolerance="balanced",
            expected_return_pct=8.0,
        )
        _seed_investment("k401", "Employer 401(k)", 100000.0, subtype="401k")
        monkeypatch.setattr(
            retirement, "estimate_contributions", _fake_contributions(1000.0)
        )

        out = await retirement.project(today=date(2026, 1, 1))

        assert out["assumptions"]["nominal_return_pct"] == 8.0
        assert out["assumptions"]["real_return_pct"] == 5.5
        assert out["assumptions"]["source"] == "profile"

    @pytest.mark.asyncio
    async def test_real_assets_are_not_part_of_the_starting_balance(self, monkeypatch):
        _set_profile(
            monkeypatch, birth_year=1990, target_retirement_age=60,
            annual_retirement_spend=60000.0, risk_tolerance="balanced",
        )
        _seed_investment("k401", "Employer 401(k)", 100000.0, subtype="401k")
        _seed_real_asset("house", 450000.0)
        monkeypatch.setattr(
            retirement, "estimate_contributions", _fake_contributions(0.0)
        )

        out = await retirement.project(today=date(2026, 1, 1))

        assert out["current_balance"] == 100000.0

    @pytest.mark.asyncio
    async def test_projection_unavailable_without_birth_year(self, monkeypatch):
        _set_profile(monkeypatch)

        out = await retirement.project()

        assert out["available"] is False
        assert "birth_year" in out["missing"]

    @pytest.mark.asyncio
    async def test_missing_risk_tolerance_names_itself(self, monkeypatch):
        _set_profile(
            monkeypatch, birth_year=1990, target_retirement_age=60,
            annual_retirement_spend=60000.0,
        )

        out = await retirement.project(today=date(2026, 1, 1))

        assert out["available"] is False
        assert "risk_tolerance" in out["missing"]

    @pytest.mark.asyncio
    async def test_target_spend_falls_back_to_a_share_of_current_expenses(
        self, monkeypatch
    ):
        _set_profile(
            monkeypatch, birth_year=1990, target_retirement_age=60,
            risk_tolerance="balanced",
        )
        monkeypatch.setattr(
            retirement.health_service, "_median_monthly_expenses", lambda today: 5000.0
        )
        monkeypatch.setattr(
            retirement, "estimate_contributions", _fake_contributions(0.0)
        )

        out = await retirement.project(today=date(2026, 1, 1))

        assert out["available"] is True
        assert out["target_annual_spend"] == 48000.0
        assert out["assumptions"]["target_spend_source"] == "estimated_from_expenses"

    @pytest.mark.asyncio
    async def test_no_spend_and_no_expense_history_is_reported_missing(
        self, monkeypatch
    ):
        _set_profile(
            monkeypatch, birth_year=1990, target_retirement_age=60,
            risk_tolerance="balanced",
        )
        monkeypatch.setattr(
            retirement.health_service, "_median_monthly_expenses", lambda today: None
        )

        out = await retirement.project(today=date(2026, 1, 1))

        assert out["available"] is False
        assert "annual_retirement_spend" in out["missing"]


class TestProjectionRoute:
    def test_route_reports_what_is_missing(self, client):
        r = client.get("/api/retirement/projection")
        assert r.status_code == 200
        body = r.json()
        assert body["available"] is False
        assert "birth_year" in body["missing"]
