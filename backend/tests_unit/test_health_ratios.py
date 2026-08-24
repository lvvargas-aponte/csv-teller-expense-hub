"""The three ratios an advisor leads with: savings rate, runway, DTI.

Every input already existed — ``profile.monthly_income`` was read only by the
LLM, ``compute_income_estimate`` returned a confidence nothing rendered — and
none of them reached a screen. These tests pin the arithmetic and, more
importantly, the reconciliation rule: a number the user stated wins, detection
fills in, and the two are never silently averaged.
"""
from datetime import date, timedelta

import pytest

import analytics
import health_service
import state


def _month_key(months_back: int) -> str:
    """YYYY-MM for a month N before the current one."""
    cursor = date.today().replace(day=1)
    for _ in range(months_back):
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    return f"{cursor.year:04d}-{cursor.month:02d}"


def _seed_expense(tid: str, month_key: str, amount: float, day: str = "05") -> None:
    state.stored_transactions[tid] = {
        "id": tid, "date": f"{month_key}-{day}", "description": "MERCHANT",
        "amount": amount, "category": "Dining", "transaction_type": "debit",
        "direction": "outflow", "source": "simplefin",
    }


def _seed_monthly_expenses(*amounts: float) -> None:
    """One expense per complete month, most recent last."""
    for i, amount in enumerate(reversed(amounts), start=1):
        _seed_expense(f"e{i}", _month_key(i), amount)


def _seed_cash(amount: float) -> None:
    state._manual_accounts["cash1"] = {
        "id": "cash1", "institution": "Bank", "name": "Savings",
        "type": "depository", "subtype": "savings",
        "available": amount, "ledger": amount, "manual": True,
    }


def _seed_card_with_minimum(account_id: str, balance: float, minimum: float) -> None:
    state._manual_accounts[account_id] = {
        "id": account_id, "institution": "Bank", "name": f"Card {account_id}",
        "type": "credit", "subtype": "", "available": 0.0, "ledger": balance,
        "manual": True,
    }
    state.account_details[account_id] = {"minimum_payment": minimum}


def _set_profile(monkeypatch, **fields):
    monkeypatch.setattr(analytics, "_load_user_profile", lambda: fields or None)


def _set_detected_income(monkeypatch, monthly, confidence="high"):
    monkeypatch.setattr(
        analytics, "compute_income_estimate",
        lambda: {"monthly_estimate": monthly, "sources": [], "confidence": confidence},
    )


@pytest.fixture(autouse=True)
def _no_detected_income(monkeypatch):
    """Detection is off unless a test asks for it — keeps the seam explicit."""
    _set_detected_income(monkeypatch, 0.0, "none")


class TestSavingsRate:
    @pytest.mark.asyncio
    async def test_savings_rate_uses_profile_income_when_set(self, monkeypatch):
        _set_profile(monkeypatch, monthly_income=8000.0)
        _seed_monthly_expenses(6000.0, 6000.0, 6000.0)

        out = await health_service.compute_ratios()

        assert out["income"]["source"] == "profile"
        assert out["income"]["monthly"] == 8000.0
        assert out["monthly_expenses"] == 6000.0
        assert out["savings_rate_pct"] == 25.0

    @pytest.mark.asyncio
    async def test_expenses_are_the_median_of_three_complete_months(self, monkeypatch):
        """A mean would let one holiday month distort every ratio below it."""
        _set_profile(monkeypatch, monthly_income=8000.0)
        _seed_monthly_expenses(5000.0, 6000.0, 9000.0)
        _seed_expense("partial", _month_key(0), 99999.0, day="01")

        out = await health_service.compute_ratios()

        assert out["monthly_expenses"] == 6000.0   # not the 6666.67 mean


class TestIncomeReconciliation:
    @pytest.mark.asyncio
    async def test_stated_income_wins_but_detection_is_still_reported(self, monkeypatch):
        _set_profile(monkeypatch, monthly_income=7250.0)
        _set_detected_income(monkeypatch, 7100.0)

        income = (await health_service.compute_ratios())["income"]

        assert income["source"] == "profile"
        assert income["monthly"] == 7250.0
        assert income["profile_monthly"] == 7250.0
        assert income["detected_monthly"] == 7100.0   # never averaged

    @pytest.mark.asyncio
    async def test_detection_fills_in_when_the_profile_is_blank(self, monkeypatch):
        _set_profile(monkeypatch)
        _set_detected_income(monkeypatch, 7100.0, "low")

        income = (await health_service.compute_ratios())["income"]

        assert income["source"] == "detected"
        assert income["monthly"] == 7100.0
        assert income["profile_monthly"] is None
        assert income["confidence"] == "low"


class TestEmergencyRunway:
    @pytest.mark.asyncio
    async def test_runway_is_cash_over_median_expenses(self, monkeypatch):
        _set_profile(monkeypatch, monthly_income=8000.0)
        _seed_monthly_expenses(6000.0, 6000.0, 6000.0)
        _seed_cash(14000.0)

        fund = (await health_service.compute_ratios())["emergency_fund"]

        assert fund["cash"] == 14000.0
        assert fund["months_covered"] == 2.3      # 14000 / 6000
        assert fund["target_months"] == 3         # no dependents stated
        assert fund["gap"] == 4000.0              # 3 * 6000 - 14000

    @pytest.mark.asyncio
    async def test_target_is_six_months_with_dependents(self, monkeypatch):
        _set_profile(monkeypatch, dependents=2)
        _seed_monthly_expenses(6000.0, 6000.0, 6000.0)
        _seed_cash(14000.0)

        fund = (await health_service.compute_ratios())["emergency_fund"]

        assert fund["target_months"] == 6
        assert fund["gap"] == 22000.0             # 6 * 6000 - 14000

    @pytest.mark.asyncio
    async def test_a_stated_target_wins_over_the_dependents_default(self, monkeypatch):
        _set_profile(monkeypatch, dependents=2, emergency_fund_months=4)
        _seed_monthly_expenses(6000.0, 6000.0, 6000.0)
        _seed_cash(14000.0)

        fund = (await health_service.compute_ratios())["emergency_fund"]

        assert fund["target_months"] == 4
        assert fund["gap"] == 10000.0


class TestDebtToIncome:
    @pytest.mark.asyncio
    async def test_dti_is_summed_minimum_payments_over_income(self, monkeypatch):
        _set_profile(monkeypatch, monthly_income=8000.0)
        _seed_card_with_minimum("c1", balance=2000.0, minimum=400.0)
        _seed_card_with_minimum("c2", balance=1000.0, minimum=200.0)

        out = await health_service.compute_ratios()

        assert out["monthly_debt_payments"] == 600.0
        assert out["dti_pct"] == 7.5


class TestMissingInputs:
    @pytest.mark.asyncio
    async def test_ratios_are_null_when_income_is_unknown(self, monkeypatch):
        _set_profile(monkeypatch)

        out = await health_service.compute_ratios()

        assert out["income"]["monthly"] is None
        assert out["income"]["source"] == "none"
        assert out["savings_rate_pct"] is None
        assert out["dti_pct"] is None

    @pytest.mark.asyncio
    async def test_runway_is_null_without_spending_history(self, monkeypatch):
        _set_profile(monkeypatch, monthly_income=8000.0)
        _seed_cash(14000.0)

        out = await health_service.compute_ratios()

        assert out["monthly_expenses"] is None
        assert out["emergency_fund"]["months_covered"] is None
        assert out["emergency_fund"]["gap"] is None
        assert out["savings_rate_pct"] is None
        assert out["as_of"] == date.today().isoformat()


class TestRatiosEndpoint:
    def test_endpoint_returns_the_service_payload(self, client, monkeypatch):
        _set_profile(monkeypatch, monthly_income=8000.0)
        _seed_monthly_expenses(6000.0, 6000.0, 6000.0)

        r = client.get("/api/health/ratios")

        assert r.status_code == 200
        body = r.json()
        assert body["savings_rate_pct"] == 25.0
        assert body["income"]["source"] == "profile"
        assert set(body) >= {
            "income", "savings_rate_pct", "monthly_expenses",
            "emergency_fund", "dti_pct", "monthly_debt_payments", "as_of",
        }
