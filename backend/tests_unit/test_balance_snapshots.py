"""Unit-style port of ``tests/test_balance_snapshots.py``.

Same assertions, sourced from ``accounts_repo_memory`` instead of SQL so the
suite runs without Postgres.
"""
from db import accounts_repo_memory


def _snapshots_for(account_id):
    return [s for s in accounts_repo_memory.get_snapshots() if s["account_id"] == account_id]


def _count_snapshots(account_id):
    return len(_snapshots_for(account_id))


class TestManualAccountSnapshots:
    _payload = {
        "institution": "Credit Union",
        "name": "Savings",
        "type": "depository",
        "subtype": "savings",
        "available": 1500.0,
        "ledger": 1500.0,
    }

    def test_post_creates_account_and_snapshot(self, client):
        response = client.post("/api/balances/manual", json=self._payload)
        assert response.status_code == 201, response.text
        acct_id = response.json()["id"]

        record = accounts_repo_memory.get_accounts()[acct_id]
        assert record["source"] == "manual"
        assert record["manual"] is True
        assert record["institution"] == "Credit Union"

        assert _count_snapshots(acct_id) == 1

    def test_delete_cascades_snapshots(self, client):
        created = client.post("/api/balances/manual", json=self._payload)
        acct_id = created.json()["id"]
        assert _count_snapshots(acct_id) == 1

        response = client.delete(f"/api/balances/manual/{acct_id}")
        assert response.status_code == 204

        assert acct_id not in accounts_repo_memory.get_accounts()
        assert _count_snapshots(acct_id) == 0


class TestManualAccountEdit:
    _payload = {
        "institution": "Credit Union",
        "name": "Savings",
        "type": "depository",
        "subtype": "savings",
        "available": 1500.0,
        "ledger": 1500.0,
    }

    def test_put_updates_balance_and_appends_snapshot(self, client):
        created = client.post("/api/balances/manual", json=self._payload)
        acct_id = created.json()["id"]
        assert _count_snapshots(acct_id) == 1

        response = client.put(
            f"/api/balances/manual/{acct_id}",
            json={"available": 1800.0, "ledger": 1800.0},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["available"] == 1800.0
        assert body["ledger"] == 1800.0
        assert body["manual"] is True

        # POST + PUT → 2 snapshots
        assert _count_snapshots(acct_id) == 2

        # Summary reflects the new balance
        summary = client.get("/api/balances/summary").json()
        acct = next(a for a in summary["accounts"] if a["id"] == acct_id)
        assert acct["available"] == 1800.0

    def test_put_partial_leaves_other_field_untouched(self, client):
        created = client.post("/api/balances/manual", json=self._payload)
        acct_id = created.json()["id"]

        response = client.put(
            f"/api/balances/manual/{acct_id}",
            json={"available": 999.0},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["available"] == 999.0
        assert body["ledger"] == 1500.0  # untouched

    def test_put_422_when_both_fields_missing(self, client):
        created = client.post("/api/balances/manual", json=self._payload)
        acct_id = created.json()["id"]

        response = client.put(f"/api/balances/manual/{acct_id}", json={})
        assert response.status_code == 422

    def test_put_404_for_unknown_id(self, client):
        response = client.put(
            "/api/balances/manual/nonexistent",
            json={"available": 100.0},
        )
        assert response.status_code == 404
