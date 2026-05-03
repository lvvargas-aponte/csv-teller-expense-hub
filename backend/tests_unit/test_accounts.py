"""Tests for the accounts router — list, fetch transactions, delete, account details."""
from unittest.mock import AsyncMock, patch

import state


class TestListAccounts:
    def test_returns_empty_when_no_tokens(self, client, monkeypatch):
        # Force no tokens for this test regardless of what's in the env
        monkeypatch.setattr(state, "TELLER_ACCESS_TOKENS", [])
        r = client.get("/api/accounts")
        assert r.status_code == 200
        assert r.json() == []


class TestGetTransactionsPersists:
    """Regression test for the bug where clicking an account to view its
    transactions wrote to `state.stored_transactions` but never flushed to
    `transactions.json` — so the data was lost on restart.
    """
    def test_fetched_transactions_are_saved_to_store(self, client, monkeypatch):
        monkeypatch.setattr(state, "TELLER_ACCESS_TOKENS", ["tok_fake"])

        fake_txns = [
            {"id": "teller_tx_1", "date": "2026-04-10", "description": "COFFEE",
             "amount": -4.50, "details": {"category": "Dining"}},
            {"id": "teller_tx_2", "date": "2026-04-11", "description": "GROCERY",
             "amount": -55.00, "details": {"category": "Food"}},
        ]
        with patch.object(
            state.teller, "list_transactions",
            new=AsyncMock(return_value=fake_txns),
        ):
            r = client.get("/api/accounts/acc_xyz/transactions")

        assert r.status_code == 200
        # In-memory populated
        assert "teller_tx_1" in state.stored_transactions
        assert "teller_tx_2" in state.stored_transactions
        # Flushed to the store dict (what save() writes to disk)
        assert "teller_tx_1" in state._transactions_store.data
        assert "teller_tx_2" in state._transactions_store.data


class TestAccountDetails:
    """CRUD for the side-car /accounts/{id}/details endpoints."""

    _endpoint = "/api/accounts/acc_xyz/details"

    def test_get_404_when_none_set(self, client):
        assert client.get(self._endpoint).status_code == 404

    def test_put_creates_and_get_returns(self, client):
        r = client.put(self._endpoint, json={
            "apr": 24.99, "credit_limit": 5000.0, "minimum_payment": 35.0,
            "statement_day": 14, "due_day": 7, "notes": "auto-pay minimum",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["account_id"] == "acc_xyz"
        assert body["apr"] == 24.99
        assert body["due_day"] == 7

        # GET retrieves the same record
        got = client.get(self._endpoint).json()
        assert got["apr"] == 24.99

    def test_put_updates_preserves_created(self, client):
        client.put(self._endpoint, json={"apr": 20.0})
        original_created = state.account_details["acc_xyz"]["created"]

        client.put(self._endpoint, json={"apr": 22.5})
        assert state.account_details["acc_xyz"]["created"] == original_created
        assert state.account_details["acc_xyz"]["apr"] == 22.5

    def test_day_out_of_range_rejected(self, client):
        assert client.put(self._endpoint, json={"due_day": 0}).status_code == 422
        assert client.put(self._endpoint, json={"statement_day": 32}).status_code == 422

    def test_negative_apr_rejected(self, client):
        assert client.put(self._endpoint, json={"apr": -1.0}).status_code == 422

    def test_delete_removes(self, client):
        client.put(self._endpoint, json={"apr": 20.0})
        r = client.delete(self._endpoint)
        assert r.status_code == 204
        assert "acc_xyz" not in state.account_details

    def test_delete_404_when_none(self, client):
        assert client.delete(self._endpoint).status_code == 404


class TestBatchAccountDetails:
    """GET /api/accounts/details (plural) returns a single map so the frontend
    doesn't have to fire N per-account requests that each 404 when no metadata
    is configured."""

    _batch = "/api/accounts/details"

    def test_empty_when_no_accounts_known(self, client):
        r = client.get(self._batch)
        assert r.status_code == 200
        assert r.json() == {}

    def test_returns_record_for_configured_account(self, client):
        client.put(
            "/api/accounts/acc_xyz/details",
            json={"apr": 24.99, "due_day": 7, "notes": ""},
        )
        r = client.get(self._batch)
        assert r.status_code == 200
        body = r.json()
        assert "acc_xyz" in body
        assert body["acc_xyz"]["apr"] == 24.99
        assert body["acc_xyz"]["due_day"] == 7

    def test_returns_null_for_manual_account_without_details(self, client):
        created = client.post(
            "/api/balances/manual",
            json={
                "institution": "Chase", "name": "Savings",
                "type": "depository", "available": 100.0, "ledger": 100.0,
            },
        ).json()
        r = client.get(self._batch).json()
        assert created["id"] in r
        assert r[created["id"]] is None

    def test_merges_configured_and_unconfigured_into_one_map(self, client):
        client.put(
            "/api/accounts/acc_with_details/details",
            json={"apr": 20.0},
        )
        blank = client.post(
            "/api/balances/manual",
            json={
                "institution": "C", "name": "X",
                "type": "depository", "available": 0.0, "ledger": 0.0,
            },
        ).json()

        r = client.get(self._batch).json()
        assert r["acc_with_details"]["apr"] == 20.0
        assert r[blank["id"]] is None


class TestErrorRowDelete:
    """Regression: disconnecting a 'Connection Error' row must remove ONLY
    the broken token, even when mask-collision-prone tokens share the same
    first-8 / last-4 characters as another token in the list.
    """

    def test_delete_error_row_removes_only_matching_token(self, client, monkeypatch):
        # Two tokens whose masks ( token[:8] + token[-4:] ) collide —
        # replicates the failure mode we used to hit with sandbox tokens.
        broken = "test_tok_broken_XXXX"
        working = "test_tok_working_XXXX"
        monkeypatch.setattr(state, "TELLER_ACCESS_TOKENS", [broken, working])
        state.teller._error_id_map.clear()

        # Mint a stable error_id for the broken token (same path as list_accounts).
        error_id = state.teller._error_id_for(broken)

        r = client.delete(f"/api/accounts/{error_id}")
        assert r.status_code == 200
        assert broken not in state.TELLER_ACCESS_TOKENS
        # Critical: the working token must survive.
        assert working in state.TELLER_ACCESS_TOKENS

    def test_delete_unknown_error_id_returns_404(self, client, monkeypatch):
        monkeypatch.setattr(state, "TELLER_ACCESS_TOKENS", ["tok_real"])
        state.teller._error_id_map.clear()
        r = client.delete("/api/accounts/_error_deadbeefdeadbeef")
        assert r.status_code == 404


class TestReconnectCleansUpBrokenToken:
    """Regression: reconnecting from an error row via /register-token must
    remove the broken token so both rows don't linger afterwards.
    """

    def test_register_token_with_old_account_id_removes_broken(self, client, monkeypatch):
        broken = "tok_broken_abcdef"
        monkeypatch.setattr(state, "TELLER_ACCESS_TOKENS", [broken])
        state.teller._error_id_map.clear()
        error_id = state.teller._error_id_for(broken)

        r = client.post("/api/teller/register-token", json={
            "access_token":   "tok_fresh_ghijkl",
            "enrollment_id":  "enr_new",
            "institution":    "Big Bank",
            "old_account_id": error_id,
        })
        assert r.status_code == 201
        assert r.json()["registered"] is True
        assert broken not in state.TELLER_ACCESS_TOKENS
        assert "tok_fresh_ghijkl" in state.TELLER_ACCESS_TOKENS

    def test_replace_token_fallback_when_enrollment_map_empty(self, client, monkeypatch):
        # Simulates the post-restart case: .env still has the broken token,
        # but the in-memory enrollment map was wiped.
        broken = "tok_broken_2"
        monkeypatch.setattr(state, "TELLER_ACCESS_TOKENS", [broken])
        state.teller._enrollment_map.clear()
        state.teller._error_id_map.clear()
        error_id = state.teller._error_id_for(broken)

        r = client.post("/api/teller/replace-token", json={
            "old_enrollment_id": "enr_unknown",
            "new_access_token":  "tok_fresh_2",
            "new_enrollment_id": "enr_new_2",
            "institution":       "Big Bank",
            "old_account_id":    error_id,
        })
        assert r.status_code == 200
        assert broken not in state.TELLER_ACCESS_TOKENS
        assert "tok_fresh_2" in state.TELLER_ACCESS_TOKENS


class TestSnapshotEnrichment:
    """build_financial_snapshot should fold account_details into debts entries."""

    def test_debts_entry_picks_up_apr(self, client):
        from analytics import build_financial_snapshot

        # Seed a manual credit account + its details
        m = client.post("/api/balances/manual", json={
            "institution": "Chase", "name": "Sapphire",
            "type": "credit", "available": 0.0, "ledger": 1234.56,
        }).json()
        client.put(f"/api/accounts/{m['id']}/details", json={
            "apr": 21.99, "minimum_payment": 35.0, "due_day": 12,
        })

        snap = build_financial_snapshot()
        credit_debts = [d for d in snap["debts"] if d["name"] == "Sapphire"]
        assert len(credit_debts) == 1
        assert credit_debts[0]["apr"] == 21.99
        assert credit_debts[0]["minimum_payment"] == 35.0
        assert credit_debts[0]["due_day"] == 12
