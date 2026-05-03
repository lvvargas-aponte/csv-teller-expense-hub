"""Phase 5 — ``balance_snapshots`` timeseries.

Every call into ``persist_teller_balances`` (via ``/teller/sync`` or
``/balances/summary?force=true``) should append one snapshot per account.
Every manual-balance POST should append exactly one snapshot and register
the account row. Manual-balance DELETE should cascade-drop snapshots.
"""
from unittest.mock import AsyncMock, patch

from sqlalchemy import text

import state
from db.base import sync_engine


def _fake_teller_account(acct_id="acc_s1"):
    return {
        "id": acct_id,
        "name": "Primary Checking",
        "type": "depository",
        "subtype": "checking",
        "institution": {"name": "Test Bank"},
        "balance": {"available": "250.00", "ledger": "250.00"},
    }


def _count_snapshots(account_id: str | None = None) -> int:
    sql = "SELECT COUNT(*) FROM balance_snapshots"
    params: dict = {}
    if account_id is not None:
        sql += " WHERE account_id = :id"
        params["id"] = account_id
    with sync_engine.connect() as conn:
        return int(conn.execute(text(sql), params).scalar() or 0)


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
        with sync_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT source, available, ledger, raw "
                    "FROM balance_snapshots WHERE account_id = 'acc_s1'"
                )
            ).fetchone()
        assert row is not None
        assert row[0] == "teller"
        assert float(row[1]) == 250.0
        assert float(row[2]) == 250.0
        # raw is the Teller balance dict; pgvector coercion returns a Python dict
        assert isinstance(row[3], dict)
        assert row[3].get("available") == "250.00"

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

        with sync_engine.connect() as conn:
            acct_row = conn.execute(
                text(
                    "SELECT source, manual, institution, name FROM accounts WHERE id = :id"
                ),
                {"id": acct_id},
            ).fetchone()
        assert acct_row is not None
        assert acct_row[0] == "manual"
        assert acct_row[1] is True
        assert acct_row[2] == "Credit Union"

        assert _count_snapshots(acct_id) == 1

    def test_delete_cascades_snapshots(self, client):
        created = client.post("/api/balances/manual", json=self._payload)
        acct_id = created.json()["id"]
        assert _count_snapshots(acct_id) == 1

        response = client.delete(f"/api/balances/manual/{acct_id}")
        assert response.status_code == 204

        # Account row gone + snapshots cascade-dropped
        with sync_engine.connect() as conn:
            assert (
                conn.execute(
                    text("SELECT COUNT(*) FROM accounts WHERE id = :id"),
                    {"id": acct_id},
                ).scalar()
                == 0
            )
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
