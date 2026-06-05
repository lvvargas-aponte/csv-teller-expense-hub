"""Integration tests for the /api/user-facts router."""
from db import user_facts_repo


_BASE = "/api/user-facts"


class TestList:
    def test_empty(self, client):
        r = client.get(_BASE)
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_facts_with_filters(self, client):
        user_facts_repo.create_fact(fact="g", category="goal", status="confirmed")
        user_facts_repo.create_fact(fact="p", category="preference", status="proposed")
        all_rows = client.get(_BASE).json()
        assert len(all_rows) == 2
        confirmed = client.get(_BASE, params={"status": "confirmed"}).json()
        assert len(confirmed) == 1 and confirmed[0]["fact"] == "g"
        goals = client.get(_BASE, params={"category": "goal"}).json()
        assert len(goals) == 1 and goals[0]["category"] == "goal"


class TestCreate:
    def test_manual_add_lands_as_confirmed(self, client):
        r = client.post(_BASE, json={
            "fact": "User has two kids in college",
            "category": "life_event",
            "tags": ["family"],
        })
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "confirmed"
        assert body["category"] == "life_event"
        assert body["tags"] == ["family"]

    def test_invalid_category_rejected(self, client):
        r = client.post(_BASE, json={"fact": "x", "category": "bogus"})
        assert r.status_code == 400

    def test_empty_fact_rejected_by_validator(self, client):
        r = client.post(_BASE, json={"fact": "", "category": "goal"})
        assert r.status_code == 422


class TestUpdate:
    def test_patch_fact_text(self, client):
        created = user_facts_repo.create_fact(fact="orig", category="goal")
        r = client.put(f"{_BASE}/{created['id']}", json={"fact": "updated"})
        assert r.status_code == 200
        assert r.json()["fact"] == "updated"

    def test_patch_sensitive_only(self, client):
        created = user_facts_repo.create_fact(fact="x", category="goal")
        r = client.put(f"{_BASE}/{created['id']}", json={"sensitive": True})
        assert r.status_code == 200
        body = r.json()
        assert body["sensitive"] is True
        assert body["fact"] == "x"

    def test_404(self, client):
        r = client.put(f"{_BASE}/999999", json={"fact": "x"})
        assert r.status_code == 404


class TestStatusTransitions:
    def test_confirm(self, client):
        created = user_facts_repo.create_fact(fact="x", category="goal")
        r = client.post(f"{_BASE}/{created['id']}/confirm")
        assert r.status_code == 200
        assert r.json()["status"] == "confirmed"

    def test_reject(self, client):
        created = user_facts_repo.create_fact(fact="x", category="goal")
        r = client.post(f"{_BASE}/{created['id']}/reject")
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

    def test_confirm_404(self, client):
        assert client.post(f"{_BASE}/999999/confirm").status_code == 404

    def test_reject_404(self, client):
        assert client.post(f"{_BASE}/999999/reject").status_code == 404


class TestDelete:
    def test_delete(self, client):
        created = user_facts_repo.create_fact(fact="x", category="goal")
        r = client.delete(f"{_BASE}/{created['id']}")
        assert r.status_code == 204
        assert user_facts_repo.get_fact(created["id"]) is None

    def test_delete_404(self, client):
        assert client.delete(f"{_BASE}/999999").status_code == 404
