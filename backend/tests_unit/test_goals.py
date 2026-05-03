"""Tests for the goals router and goal-status computation."""
from datetime import date, timedelta

import state


class TestCreateGoal:
    def test_create_basic_goal(self, client):
        r = client.post("/api/goals", json={
            "name": "Vacation",
            "target_amount": 3000.0,
            "current_balance": 500.0,
        })
        assert r.status_code == 201
        body = r.json()
        assert body["id"].startswith("goal_")
        assert body["name"] == "Vacation"
        assert body["current_balance"] == 500.0
        assert body["progress_pct"] == round(500 / 3000 * 100, 1)
        assert body["id"] in state.goals

    def test_target_amount_must_be_positive(self, client):
        r = client.post("/api/goals", json={"name": "X", "target_amount": 0})
        assert r.status_code == 422

    def test_invalid_kind_rejected(self, client):
        r = client.post("/api/goals", json={
            "name": "X", "target_amount": 100, "kind": "retirement"
        })
        assert r.status_code == 422

    def test_target_date_drives_monthly_required(self, client):
        target = (date.today().replace(day=1) + timedelta(days=400)).isoformat()
        r = client.post("/api/goals", json={
            "name": "House", "target_amount": 12000.0,
            "current_balance": 0.0, "target_date": target,
        })
        body = r.json()
        assert body["months_remaining"] is not None
        assert body["months_remaining"] > 0
        assert body["monthly_required"] is not None
        assert body["monthly_required"] > 0

    def test_linked_account_overrides_current_balance(self, client):
        # Add a manual depository account, then link it.
        m = client.post("/api/balances/manual", json={
            "institution": "Local CU", "name": "Savings",
            "type": "depository", "available": 750.0, "ledger": 750.0,
        }).json()

        r = client.post("/api/goals", json={
            "name": "Emergency", "target_amount": 3000.0,
            "current_balance": 0.0,            # should be overridden
            "linked_account_id": m["id"],
            "kind": "emergency_fund",
        })
        body = r.json()
        assert body["current_balance"] == 750.0


class TestUpdateGoal:
    def test_update_preserves_created(self, client):
        created = client.post("/api/goals", json={
            "name": "X", "target_amount": 100.0,
        }).json()
        goal_id = created["id"]
        original_created = state.goals[goal_id]["created"]

        r = client.put(f"/api/goals/{goal_id}", json={
            "name": "X-renamed", "target_amount": 200.0, "current_balance": 50.0,
        })
        assert r.status_code == 200
        assert state.goals[goal_id]["created"] == original_created
        assert state.goals[goal_id]["name"] == "X-renamed"
        assert r.json()["progress_pct"] == 25.0

    def test_404_for_unknown_id(self, client):
        r = client.put("/api/goals/goal_nope", json={
            "name": "X", "target_amount": 100.0,
        })
        assert r.status_code == 404


class TestListGoals:
    def test_empty_list(self, client):
        r = client.get("/api/goals")
        assert r.status_code == 200
        assert r.json() == []

    def test_emergency_fund_sorted_first(self, client):
        client.post("/api/goals", json={
            "name": "Vacation", "target_amount": 1000.0, "kind": "savings",
        })
        client.post("/api/goals", json={
            "name": "Rainy day", "target_amount": 5000.0, "kind": "emergency_fund",
        })

        r = client.get("/api/goals")
        names = [g["name"] for g in r.json()]
        assert names[0] == "Rainy day"


class TestDeleteGoal:
    def test_deletes(self, client):
        created = client.post("/api/goals", json={
            "name": "X", "target_amount": 100.0,
        }).json()
        r = client.delete(f"/api/goals/{created['id']}")
        assert r.status_code == 204
        assert created["id"] not in state.goals

    def test_404_for_unknown(self, client):
        r = client.delete("/api/goals/goal_nope")
        assert r.status_code == 404
