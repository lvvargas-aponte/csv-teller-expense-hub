"""Unit-style port of ``tests/test_balance_snapshots.py``.

Same assertions, sourced from ``accounts_repo_memory`` instead of SQL so the
suite runs without Postgres.
"""
from unittest.mock import AsyncMock, patch

import state
from db import accounts_repo_memory


def _fake_teller_account(acct_id="acc_s1"):
    return {
        "id": acct_id,
        "name": "Primary Checking",
        "type": "depository",
        "subtype": "checking",
        "institution": {"name": "Test Bank"},
        "balance": {"available": "250.00", "ledger": "250.00"},
    }


def _snapshots_for(account_id):
    return [s for s in accounts_repo_memory.get_snapshots() if s["account_id"] == account_id]


def _count_snapshots(account_id):
    return len(_snapshots_for(account_id))


class TestTellerSyncWritesSnapshots:
    def _invoke_sync(self, client):
        account = _fake_teller_account()
        list_mock = AsyncMock(return_value=([("tok1", [account])], []))
        txns_mock = AsyncMock(return_value=[])
        bal_mock = AsyncMock(return_value=account["balance"])
        with patch.object(state.teller, "list_accounts_by_token", list_mock), \
             patch.object(state.teller, "fetch_account_transactions", txns_mock), \
             patch.object(state.teller, "fetch_balance_safe", bal_mock), \
             patch.object(state, "TELLER_ACCESS_TOKENS", ["tok1"]):
            return client.post(
                "/api/teller/sync",
                json={"from_date": "2026-03-01", "to_date": "2026-03-31"},
            )

    def test_first_sync_writes_one_snapshot_per_account(self, client):
        response = self._invoke_sync(client)
        assert response.status_code == 200, response.text
        assert _count_snapshots("acc_s1") == 1

    def test_snapshot_captures_available_ledger_source_raw(self, client):
        self._invoke_sync(client)
        snap = _snapshots_for("acc_s1")[0]
        assert snap["source"] == "teller"
        assert float(snap["available"]) == 250.0
        assert float(snap["ledger"]) == 250.0
        assert isinstance(snap["raw"], dict)
        assert snap["raw"].get("available") == "250.00"

    def test_each_sync_appends_a_new_snapshot(self, client):
        """History table: re-running sync does NOT upsert, it appends."""
        self._invoke_sync(client)
        self._invoke_sync(client)
        self._invoke_sync(client)
        assert _count_snapshots("acc_s1") == 3


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
