"""Integration tests for the weekly digest endpoints."""
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import state
from db import digests_repo


def _add_txn(tid, amount, days_ago, description="COFFEE SHOP", category="Dining"):
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    state.stored_transactions[tid] = {
        "id": tid, "date": d, "description": description, "amount": amount,
        "category": category, "transaction_type": "debit", "source": "teller",
        "direction": "outflow",
    }


def _mock_ollama_down():
    return patch(
        "digest.ask_ollama",
        new=AsyncMock(return_value={"ai_available": False, "text": None}),
    )


class TestDigestGeneration:
    def test_first_call_generates_and_stores(self, client):
        _add_txn("a", 25.0, days_ago=2)
        _add_txn("b", 40.0, days_ago=10)
        with _mock_ollama_down():
            r = client.get("/api/digest/latest")
        assert r.status_code == 200
        body = r.json()
        assert body["read"] is False
        assert body["payload"]["spending"]["this_week"] == 25.0
        assert body["payload"]["spending"]["prior_week"] == 40.0
        assert body["payload"]["narrative"] is None
        assert digests_repo.latest()["id"] == body["id"]

    def test_second_call_reuses_fresh_digest(self, client):
        with _mock_ollama_down():
            first = client.get("/api/digest/latest").json()
            second = client.get("/api/digest/latest").json()
        assert first["id"] == second["id"]

    def test_force_regenerates(self, client):
        with _mock_ollama_down():
            first = client.get("/api/digest/latest").json()
            second = client.get("/api/digest/latest?force=true").json()
        assert second["id"] != first["id"]

    def test_narrative_included_when_ollama_up(self, client):
        _add_txn("a", 25.0, days_ago=2)
        with patch(
            "digest.ask_ollama",
            new=AsyncMock(return_value={"ai_available": True, "text": "Nice week!"}),
        ):
            body = client.get("/api/digest/latest").json()
        assert body["payload"]["narrative"] == "Nice week!"
        assert body["payload"]["ai_available"] is True

    def test_subscription_flags_surface(self, client):
        for i in range(3):
            _add_txn(f"nfx_{i}", 15.49, days_ago=5 + 30 * i,
                     description="NETFLIX MEMBERSHIP", category="Entertainment")
        with _mock_ollama_down():
            body = client.get("/api/digest/latest").json()
        assert body["payload"]["subscriptions"]["needs_review_count"] == 1


class TestMarkRead:
    def test_mark_read_flips_flag(self, client):
        with _mock_ollama_down():
            body = client.get("/api/digest/latest").json()
        assert client.post(f"/api/digest/{body['id']}/read").status_code == 204
        assert client.get("/api/digest/latest").json()["read"] is True

    def test_mark_read_is_idempotent(self, client):
        with _mock_ollama_down():
            body = client.get("/api/digest/latest").json()
        client.post(f"/api/digest/{body['id']}/read")
        assert client.post(f"/api/digest/{body['id']}/read").status_code == 204

    def test_unknown_digest_is_404(self, client):
        assert client.post("/api/digest/999999/read").status_code == 404