"""Integration tests for the subscriptions review endpoints."""
from datetime import date, timedelta

import state


def _add_recurring(tid_prefix, description, amount, category="Entertainment", months=3):
    for i in range(months):
        d = (date.today() - timedelta(days=5 + 30 * i)).isoformat()
        tid = f"{tid_prefix}_{i}"
        state.stored_transactions[tid] = {
            "id": tid, "date": d, "description": description, "amount": amount,
            "category": category, "transaction_type": "debit", "source": "teller",
            "direction": "outflow",
        }


class TestListSubscriptions:
    def test_new_merchant_needs_review(self, client):
        _add_recurring("nfx", "NETFLIX MEMBERSHIP", 15.49)
        data = client.get("/api/subscriptions").json()
        assert len(data["subscriptions"]) == 1
        sub = data["subscriptions"][0]
        assert sub["needs_review"] is True
        assert sub["review"] is None
        assert data["summary"]["needs_review_count"] == 1
        assert data["summary"]["active_monthly_cost"] == 15.49

    def test_reviewed_merchant_is_settled(self, client):
        _add_recurring("nfx", "NETFLIX MEMBERSHIP", 15.49)
        r = client.post(
            "/api/subscriptions/netflix membership/review", json={"decision": "keep"}
        )
        assert r.status_code == 200
        assert r.json()["review"]["reviewed_amount"] == 15.49

        data = client.get("/api/subscriptions").json()
        sub = data["subscriptions"][0]
        assert sub["needs_review"] is False
        assert sub["review"]["decision"] == "keep"
        assert data["summary"]["needs_review_count"] == 0

    def test_price_increase_reprompts(self, client):
        _add_recurring("nfx", "NETFLIX MEMBERSHIP", 15.49)
        client.post(
            "/api/subscriptions/netflix membership/review", json={"decision": "keep"}
        )
        # Price jumps >10% on the newest charge.
        newest = (date.today() - timedelta(days=1)).isoformat()
        state.stored_transactions["nfx_new"] = {
            "id": "nfx_new", "date": newest, "description": "NETFLIX MEMBERSHIP",
            "amount": 18.99, "category": "Entertainment",
            "transaction_type": "debit", "source": "teller", "direction": "outflow",
        }
        data = client.get("/api/subscriptions").json()
        sub = data["subscriptions"][0]
        assert sub["needs_review"] is True
        assert sub["price_change_since_review_pct"] > 10

    def test_cancel_moves_cost_to_savings(self, client):
        _add_recurring("hulu", "HULU SUBSCRIPTION", 12.99)
        client.post(
            "/api/subscriptions/hulu subscription/review", json={"decision": "cancel"}
        )
        data = client.get("/api/subscriptions").json()
        assert data["summary"]["cancel_monthly_savings"] == 12.99
        assert data["summary"]["active_monthly_cost"] == 0.0

    def test_overlap_flagged_for_two_streaming_services(self, client):
        _add_recurring("nfx", "NETFLIX MEMBERSHIP", 15.49)
        _add_recurring("hulu", "HULU SUBSCRIPTION", 12.99)
        data = client.get("/api/subscriptions").json()
        groups = {s["merchant_key"]: s["overlap_group"] for s in data["subscriptions"]}
        assert groups["netflix membership"] == "entertainment"
        assert groups["hulu subscription"] == "entertainment"

    def test_ignored_merchant_never_reprompts(self, client):
        _add_recurring("gym", "CITY GYM", 40.0, category="Gym Fees")
        client.post("/api/subscriptions/city gym/review", json={"decision": "ignore"})
        data = client.get("/api/subscriptions").json()
        assert data["subscriptions"][0]["needs_review"] is False


class TestReviewValidation:
    def test_invalid_decision_is_422(self, client):
        r = client.post("/api/subscriptions/whatever/review", json={"decision": "meh"})
        assert r.status_code == 422

    def test_clear_review(self, client):
        _add_recurring("nfx", "NETFLIX MEMBERSHIP", 15.49)
        client.post(
            "/api/subscriptions/netflix membership/review", json={"decision": "keep"}
        )
        r = client.delete("/api/subscriptions/netflix membership/review")
        assert r.status_code == 204
        assert client.get("/api/subscriptions").json()["subscriptions"][0]["review"] is None

    def test_clear_missing_review_is_404(self, client):
        assert client.delete("/api/subscriptions/nope/review").status_code == 404