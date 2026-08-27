"""Tests for the budgets router and budget-status computation."""
from datetime import date

import pytest

import analytics
from routers import alerts as alerts_router
import state


def _seed_current_month_spending(client, monkeypatch):
    """Insert two expense transactions in the current month for category 'Dining'."""
    today = date.today().isoformat()
    state.stored_transactions["t1"] = {
        "id": "t1", "date": today, "description": "RESTAURANT", "amount": 30.0,
        "category": "Dining", "transaction_type": "debit", "source": "simplefin",
    }
    state.stored_transactions["t2"] = {
        "id": "t2", "date": today, "description": "CAFE", "amount": 15.0,
        "category": "Dining", "transaction_type": "debit", "source": "simplefin",
    }


class TestUpsertBudget:
    def test_create_budget(self, client):
        r = client.put("/api/budgets/Dining", json={
            "category": "Dining", "monthly_limit": 200.0, "notes": "weekday lunches"
        })
        assert r.status_code == 200
        body = r.json()
        assert body["category"] == "Dining"
        assert body["monthly_limit"] == 200.0
        assert body["current_month_spent"] == 0.0
        assert body["over_budget"] is False
        assert "Dining" in state.budgets

    def test_update_budget_preserves_created_timestamp(self, client):
        client.put("/api/budgets/Groceries", json={"category": "Groceries", "monthly_limit": 400.0})
        original_created = state.budgets["Groceries"]["created"]

        client.put("/api/budgets/Groceries", json={"category": "Groceries", "monthly_limit": 500.0})
        assert state.budgets["Groceries"]["created"] == original_created
        assert state.budgets["Groceries"]["monthly_limit"] == 500.0

    def test_negative_limit_rejected(self, client):
        r = client.put("/api/budgets/X", json={"category": "X", "monthly_limit": -1.0})
        assert r.status_code == 422

    def test_empty_category_rejected(self, client):
        # FastAPI strips trailing slash but a whitespace category should fail validation.
        r = client.put("/api/budgets/%20", json={"category": " ", "monthly_limit": 10.0})
        assert r.status_code == 422


class TestListBudgets:
    def test_empty_list(self, client):
        r = client.get("/api/budgets")
        assert r.status_code == 200
        assert r.json() == []

    def test_status_includes_current_spend_and_over_flag(self, client, monkeypatch):
        _seed_current_month_spending(client, monkeypatch)
        client.put("/api/budgets/Dining", json={"category": "Dining", "monthly_limit": 40.0})

        r = client.get("/api/budgets")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["category"] == "Dining"
        assert body[0]["current_month_spent"] == 45.0
        assert body[0]["over_budget"] is True
        assert body[0]["percent_used"] > 100

    def test_category_match_is_case_insensitive(self, client, monkeypatch):
        _seed_current_month_spending(client, monkeypatch)
        # User configures budget as 'dining' (lowercase) but data uses 'Dining'
        client.put("/api/budgets/dining", json={"category": "dining", "monthly_limit": 100.0})

        r = client.get("/api/budgets")
        assert r.json()[0]["current_month_spent"] == 45.0


class TestDeleteBudget:
    def test_delete_existing(self, client):
        client.put("/api/budgets/X", json={"category": "X", "monthly_limit": 10.0})
        r = client.delete("/api/budgets/X")
        assert r.status_code == 204
        assert "X" not in state.budgets

    def test_404_for_unknown(self, client):
        r = client.delete("/api/budgets/Nope")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Pacing — spend against the elapsed month, not against a full-month cap
# ---------------------------------------------------------------------------

def _set_budget(category: str, monthly_limit: float) -> None:
    state.budgets[category] = {
        "category": category, "monthly_limit": monthly_limit, "notes": "",
    }


def _seed_txn(tid: str, day: str, amount: float, category: str) -> None:
    state.stored_transactions[tid] = {
        "id": tid, "date": day, "description": "MERCHANT", "amount": amount,
        "category": category, "transaction_type": "debit",
        "direction": "outflow", "source": "simplefin",
    }


class TestBudgetPacing:
    def test_budget_over_pace_before_it_is_over_budget(self):
        """$300 of a $500 cap by the 10th projects to $930 — the warning has to
        arrive while the month can still be changed."""
        _set_budget("Dining", 500.0)
        _seed_txn("a", "2026-08-05", 300.0, "Dining")

        status = analytics.compute_budget_statuses(today=date(2026, 8, 10))[0]

        assert status["percent_used"] == 60.0
        assert status["month_progress_pct"] == pytest.approx(32.3, abs=0.1)
        assert status["projected_month_end"] == pytest.approx(930.0, abs=1.0)
        assert status["pace_status"] == "over_pace"
        assert status["projected_overage"] == pytest.approx(430.0, abs=1.0)
        assert status["over_budget"] is False

    def test_spending_in_line_with_the_month_is_on_track(self):
        _set_budget("Dining", 500.0)
        _seed_txn("a", "2026-08-05", 160.0, "Dining")

        status = analytics.compute_budget_statuses(today=date(2026, 8, 10))[0]

        assert status["pace_status"] == "on_track"
        assert status["projected_overage"] is None

    def test_a_quiet_month_reads_as_under(self):
        _set_budget("Dining", 500.0)
        _seed_txn("a", "2026-08-05", 50.0, "Dining")

        status = analytics.compute_budget_statuses(today=date(2026, 8, 10))[0]

        assert status["projected_month_end"] == pytest.approx(155.0, abs=1.0)
        assert status["pace_status"] == "under"

    def test_already_past_the_cap_reads_as_over_budget(self):
        _set_budget("Dining", 500.0)
        _seed_txn("a", "2026-08-05", 600.0, "Dining")

        status = analytics.compute_budget_statuses(today=date(2026, 8, 10))[0]

        assert status["over_budget"] is True
        assert status["pace_status"] == "over_budget"

    def test_the_last_day_projects_to_what_was_actually_spent(self):
        _set_budget("Dining", 500.0)
        _seed_txn("a", "2026-08-05", 300.0, "Dining")

        status = analytics.compute_budget_statuses(today=date(2026, 8, 31))[0]

        assert status["month_progress_pct"] == 100.0
        assert status["projected_month_end"] == 300.0
        assert status["pace_status"] == "under"

    def test_defaults_to_today_for_existing_callers(self):
        _set_budget("Dining", 500.0)

        status = analytics.compute_budget_statuses()[0]

        assert status["month_progress_pct"] > 0
        assert status["pace_status"] in {"under", "on_track", "over_pace", "over_budget"}


class TestPaceAlert:
    """The feed's job here is to say the projection out loud; the pace
    arithmetic itself is pinned above. Statuses are stubbed so the assertion
    doesn't depend on which day of the month the suite runs."""

    def _stub_status(self, monkeypatch, **over):
        status = {
            "category": "Dining", "monthly_limit": 500.0, "notes": "",
            "current_month_spent": 300.0, "percent_used": 60.0,
            "over_budget": False, "month_progress_pct": 32.3,
            "projected_month_end": 930.0, "pace_status": "over_pace",
            "projected_overage": 430.0,
        }
        status.update(over)
        monkeypatch.setattr(alerts_router, "compute_budget_statuses", lambda: [status])

    def test_over_pace_raises_a_warning_with_the_projection(self, client, monkeypatch):
        self._stub_status(monkeypatch)

        feed = client.get("/api/alerts").json()["alerts"]
        budget_alerts = [a for a in feed if a["category"] == "budget"]

        assert len(budget_alerts) == 1
        assert budget_alerts[0]["severity"] == "warn"
        assert budget_alerts[0]["message"] == (
            "Dining is pacing to $930 against a $500 cap"
        )

    def test_no_pace_alert_when_on_track(self, client, monkeypatch):
        self._stub_status(
            monkeypatch, pace_status="on_track",
            projected_month_end=480.0, projected_overage=None,
        )

        feed = client.get("/api/alerts").json()["alerts"]

        assert [a for a in feed if a["category"] == "budget"] == []

    def test_an_over_budget_category_still_reports_as_an_error(self, client, monkeypatch):
        self._stub_status(
            monkeypatch, over_budget=True, pace_status="over_budget",
            current_month_spent=600.0, percent_used=120.0,
        )

        feed = client.get("/api/alerts").json()["alerts"]
        budget_alerts = [a for a in feed if a["category"] == "budget"]

        assert len(budget_alerts) == 1
        assert budget_alerts[0]["severity"] == "error"
        assert "over budget" in budget_alerts[0]["message"]


class TestAlertTargets:
    """Alerts pointed at /finances/plan, a route that does not exist, and the
    card never rendered the field — every alert was unactionable. They now
    carry the tab id the sidebar uses."""

    def test_budget_alerts_target_the_budgets_tab(self, client, monkeypatch):
        monkeypatch.setattr(alerts_router, "compute_budget_statuses", lambda: [{
            "category": "Dining", "monthly_limit": 500.0, "notes": "",
            "current_month_spent": 600.0, "percent_used": 120.0,
            "over_budget": True, "month_progress_pct": 50.0,
            "projected_month_end": 1200.0, "pace_status": "over_budget",
            "projected_overage": 700.0,
        }])

        alert = client.get("/api/alerts").json()["alerts"][0]

        assert alert["tab"] == "budgets"
        assert "link" not in alert

    def test_utilization_alerts_target_the_debt_tab(self, client):
        state._manual_accounts["c1"] = {
            "id": "c1", "institution": "Bank", "name": "Card", "type": "credit",
            "subtype": "", "available": 0.0, "ledger": 900.0, "manual": True,
        }
        state.account_details["c1"] = {"credit_limit": 1000.0}

        alert = [
            a for a in client.get("/api/alerts").json()["alerts"]
            if a["category"] == "credit"
        ][0]

        assert alert["tab"] == "debt"
