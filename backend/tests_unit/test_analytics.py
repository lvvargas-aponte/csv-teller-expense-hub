"""Tests for analytics helpers — recurring detection and snapshot enrichment."""
from datetime import date, timedelta

import state
from analytics import (
    build_financial_snapshot,
    detect_recurring_charges,
)


def _add_txn(tid, amount, days_ago, description="NETFLIX MEMBERSHIP", category="Entertainment"):
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    state.stored_transactions[tid] = {
        "id": tid, "date": d, "description": description, "amount": amount,
        "category": category, "transaction_type": "debit", "source": "teller",
    }


class TestRecurringDetection:
    def test_detects_monthly_subscription(self, client):
        _add_txn("a", 15.49, days_ago=5)
        _add_txn("b", 15.49, days_ago=35)
        _add_txn("c", 15.49, days_ago=65)

        out = detect_recurring_charges()
        assert len(out) == 1
        rec = out[0]
        assert rec["occurrences"] == 3
        assert rec["months_seen"] == 3
        assert rec["average_amount"] == 15.49
        assert rec["estimated_monthly_cost"] == 15.49
        assert "netflix" in rec["merchant_key"]

    def test_skips_one_off_charge(self, client):
        _add_txn("a", 200.00, days_ago=5, description="ELECTRONICS STORE")
        out = detect_recurring_charges()
        assert out == []

    def test_skips_highly_variable_amounts(self, client):
        # Same merchant key but amounts vary >25% — not a subscription.
        _add_txn("a", 10.00, days_ago=5, description="GAS STATION")
        _add_txn("b", 50.00, days_ago=35, description="GAS STATION")
        _add_txn("c", 30.00, days_ago=65, description="GAS STATION")
        out = detect_recurring_charges()
        assert out == []

    def test_normalizes_changing_transaction_ids(self, client):
        # Real-world: descriptions often carry changing reference numbers.
        _add_txn("a", 9.99, days_ago=5,  description="SPOTIFY *REF12345")
        _add_txn("b", 9.99, days_ago=35, description="SPOTIFY *REF67890")
        out = detect_recurring_charges()
        assert len(out) == 1
        assert "spotify" in out[0]["merchant_key"]


class TestSnapshotEnrichment:
    def test_snapshot_includes_new_sections(self, client):
        # Seed a budget, a goal, and a recurring charge.
        client.put("/api/budgets/Dining", json={
            "category": "Dining", "monthly_limit": 200.0,
        })
        client.post("/api/goals", json={
            "name": "Vacation", "target_amount": 1000.0, "current_balance": 250.0,
        })
        _add_txn("a", 9.99, days_ago=5,  description="SPOTIFY")
        _add_txn("b", 9.99, days_ago=35, description="SPOTIFY")

        snap = build_financial_snapshot()
        assert "budgets" in snap
        assert "goals" in snap
        assert "recurring_charges" in snap

        assert snap["budgets"][0]["category"] == "Dining"
        assert snap["goals"][0]["name"] == "Vacation"
        assert snap["goals"][0]["progress_pct"] == 25.0
        assert any("spotify" in r["merchant_key"] for r in snap["recurring_charges"])
