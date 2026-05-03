"""Tests for the budgets router and budget-status computation."""
from datetime import date

import state


def _seed_current_month_spending(client, monkeypatch):
    """Insert two expense transactions in the current month for category 'Dining'."""
    today = date.today().isoformat()
    state.stored_transactions["t1"] = {
        "id": "t1", "date": today, "description": "RESTAURANT", "amount": 30.0,
        "category": "Dining", "transaction_type": "debit", "source": "teller",
    }
    state.stored_transactions["t2"] = {
        "id": "t2", "date": today, "description": "CAFE", "amount": 15.0,
        "category": "Dining", "transaction_type": "debit", "source": "teller",
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
