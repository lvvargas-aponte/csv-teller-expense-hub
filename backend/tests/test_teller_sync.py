"""Tests for POST /api/teller/sync.

Phase 4 verifies that a successful sync:
  1. Upserts every returned account into the structured ``accounts`` table
     (via ``persist_teller_balances`` → ``upsert_teller_account``).
  2. Threads ``account_id`` through to every txn persisted in ``json_stores``.

CSV-uploaded transactions intentionally keep ``account_id = None``.
"""
from unittest.mock import AsyncMock, patch

from sqlalchemy import text

import state
from db.base import sync_engine
from state import stored_transactions


def _fake_teller_account():
    return {
        "id": "acc_xyz",
        "name": "Test Checking",
        "type": "depository",
        "subtype": "checking",
        "institution": {"name": "Test Bank"},
        "enrollment": {"id": "enr_abc"},
        "balance": {"available": "100.00", "ledger": "100.00"},
    }


def _fake_teller_txns():
    return [
        {
            "id": "teller_tx_1",
            "date": "2026-03-15",
            "description": "STARBUCKS",
            "amount": "-4.50",
            "details": {"category": "restaurants"},
            "running_balance": "99.50",
        },
        {
            "id": "teller_tx_2",
            "date": "2026-03-16",
            "description": "WALMART",
            "amount": "-20.00",
            "details": {"category": "groceries"},
            "running_balance": "79.50",
        },
    ]


def _invoke_sync(client):
    account = _fake_teller_account()
    list_mock = AsyncMock(return_value=([("tok1", [account])], []))
    txns_mock = AsyncMock(return_value=_fake_teller_txns())
    bal_mock = AsyncMock(return_value=account["balance"])
    with patch.object(state.teller, "list_accounts_by_token", list_mock), \
         patch.object(state.teller, "fetch_account_transactions", txns_mock), \
         patch.object(state.teller, "fetch_balance_safe", bal_mock), \
         patch.object(state, "TELLER_ACCESS_TOKENS", ["tok1"]):
        return client.post(
            "/api/teller/sync",
            json={"from_date": "2026-03-01", "to_date": "2026-03-31"},
        )


class TestTellerSyncAccountFK:
    def test_account_upserted_on_sync(self, client):
        response = _invoke_sync(client)
        assert response.status_code == 200, response.text

        with sync_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT source, institution, name, type, subtype, "
                    "manual, token_enrollment_id "
                    "FROM accounts WHERE id = 'acc_xyz'"
                )
            ).fetchone()

        assert row is not None, "account row missing after sync"
        assert row[0] == "teller"
        assert row[1] == "Test Bank"
        assert row[2] == "Test Checking"
        assert row[3] == "depository"
        assert row[4] == "checking"
        assert row[5] is False
        assert row[6] == "enr_abc"

    def test_synced_txns_carry_account_id(self, client):
        _invoke_sync(client)
        assert "teller_tx_1" in stored_transactions
        assert "teller_tx_2" in stored_transactions
        assert stored_transactions["teller_tx_1"]["account_id"] == "acc_xyz"
        assert stored_transactions["teller_tx_2"]["account_id"] == "acc_xyz"

    def test_sync_is_idempotent_on_account_row(self, client):
        """Second sync updates the same row; no duplicate."""
        _invoke_sync(client)
        _invoke_sync(client)
        with sync_engine.connect() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM accounts WHERE id = 'acc_xyz'")
            ).scalar()
        assert count == 1


class TestCsvUploadHasNoAccountId:
    def test_csv_txns_leave_account_id_null(self, client, sample_discover_csv):
        """Phase 4 explicit policy: CSV-sourced txns don't know their account."""
        response = client.post(
            "/api/upload-csv",
            files={"file": ("test.csv", sample_discover_csv, "text/csv")},
        )
        assert response.status_code == 200, response.text
        assert len(stored_transactions) > 0
        for tid, txn in stored_transactions.items():
            assert txn.get("account_id") is None, (
                f"CSV-sourced txn {tid} should have account_id=None but got {txn.get('account_id')!r}"
            )
