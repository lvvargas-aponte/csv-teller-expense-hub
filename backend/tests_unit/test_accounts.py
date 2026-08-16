"""Tests for the accounts router — list, delete, account details."""
import state


class TestListAccounts:
    def test_returns_empty_when_no_urls(self, client, monkeypatch):
        # Force no access URLs for this test regardless of what's in the env
        monkeypatch.setattr(state, "SIMPLEFIN_ACCESS_URLS", [])
        r = client.get("/api/accounts")
        assert r.status_code == 200
        assert r.json() == []


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

    def test_min_payment_window_round_trips(self, client):
        r = client.put(self._endpoint, json={
            "minimum_payment": 350.0,
            "deferred_interest": True,
            "promo_apr": 0.0,
            "promo_expires": "2028-06-01",
            "min_payment_from": "2026-08-01",
            "min_payment_until": "2027-08-01",
        })
        assert r.status_code == 200

        got = client.get(self._endpoint).json()
        assert got["minimum_payment"] == 350.0
        assert got["min_payment_from"] == "2026-08-01"
        assert got["min_payment_until"] == "2027-08-01"
        assert got["promo_expires"] == "2028-06-01"

    def test_malformed_min_payment_window_rejected(self, client):
        assert client.put(
            self._endpoint, json={"min_payment_from": "08/01/2026"}
        ).status_code == 422
        assert client.put(
            self._endpoint, json={"min_payment_until": "not-a-date"}
        ).status_code == 422

    def test_min_payment_window_optional(self, client):
        r = client.put(self._endpoint, json={"minimum_payment": 35.0})
        assert r.status_code == 200
        assert r.json()["min_payment_from"] is None
        assert r.json()["min_payment_until"] is None

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


class TestDisconnectHidesSimplefinAccount:
    """DELETE /accounts/{id} on a SimpleFIN-cached account hides it locally
    (SimpleFIN has no per-account revoke) but keeps the local record so
    transactions, balance, and APR/limit details survive.
    """

    _acct_id = "acc_keep_me"

    def _seed_simplefin_cache(self) -> None:
        """Put one SimpleFIN account in the cache, as if a sync had just run."""
        state._balances_cache_store.data["simplefin_accounts"] = [{
            "id": self._acct_id,
            "institution": "Chase",
            "name": "Sapphire Reserve",
            "type": "credit",
            "subtype": "credit_card",
            "available": 0.0,
            "ledger": 1234.56,
        }]
        state._balances_cache_store.data["simplefin_cash"] = 0.0
        state._balances_cache_store.data["simplefin_credit_debt"] = 1234.56
        state._balances_cache_store.save()

    def test_default_disconnect_preserves_account_and_details(self, client, monkeypatch):
        monkeypatch.setattr(state, "SIMPLEFIN_ACCESS_URLS", ["https://user:pass@bridge.example/access"])
        self._seed_simplefin_cache()
        client.put(
            f"/api/accounts/{self._acct_id}/details",
            json={"apr": 21.99, "credit_limit": 5000.0, "due_day": 12},
        )

        r = client.delete(f"/api/accounts/{self._acct_id}")

        assert r.status_code == 200
        body = r.json()
        assert body == {"deleted": self._acct_id, "purged": False}

        # No longer in the live simplefin cache, but lives on as a manual shadow.
        assert all(
            a.get("id") != self._acct_id
            for a in state._balances_cache.get("simplefin_accounts", [])
        )
        shadow = state._manual_accounts.get(self._acct_id)
        assert shadow is not None
        assert shadow["disconnected_from"] == "simplefin"
        assert shadow["institution"] == "Chase"
        assert shadow["name"] == "Sapphire Reserve"
        assert shadow["ledger"] == 1234.56

        # Side-car details survive (the user can keep using APR/limit/due-day).
        assert self._acct_id in state.account_details
        assert state.account_details[self._acct_id]["apr"] == 21.99

        # Balances summary still shows the account, flagged as disconnected.
        summary = client.get("/api/balances/summary").json()
        rows = [a for a in summary["accounts"] if a["id"] == self._acct_id]
        assert len(rows) == 1
        assert rows[0]["manual"] is True
        assert rows[0]["disconnected_from"] == "simplefin"

    def test_purge_query_removes_everything(self, client, monkeypatch):
        monkeypatch.setattr(state, "SIMPLEFIN_ACCESS_URLS", ["https://user:pass@bridge.example/access"])
        self._seed_simplefin_cache()
        client.put(f"/api/accounts/{self._acct_id}/details", json={"apr": 19.0})

        r = client.delete(f"/api/accounts/{self._acct_id}?purge=true")

        assert r.status_code == 200
        assert r.json() == {"deleted": self._acct_id, "purged": True}
        assert self._acct_id not in state._manual_accounts
        assert all(
            a.get("id") != self._acct_id
            for a in state._balances_cache.get("simplefin_accounts", [])
        )
        assert self._acct_id not in state.account_details

    def test_purge_works_on_existing_manual_shadow(self, client, monkeypatch):
        """After a disconnect, a follow-up purge?=true must still wipe the
        shadow even with no SimpleFIN access URLs configured."""
        monkeypatch.setattr(state, "SIMPLEFIN_ACCESS_URLS", ["https://user:pass@bridge.example/access"])
        self._seed_simplefin_cache()
        client.delete(f"/api/accounts/{self._acct_id}")
        assert self._acct_id in state._manual_accounts

        monkeypatch.setattr(state, "SIMPLEFIN_ACCESS_URLS", [])
        r = client.delete(f"/api/accounts/{self._acct_id}?purge=true")
        assert r.status_code == 200
        assert self._acct_id not in state._manual_accounts

    def test_unknown_account_returns_404(self, client, monkeypatch):
        monkeypatch.setattr(state, "SIMPLEFIN_ACCESS_URLS", ["https://user:pass@bridge.example/access"])
        r = client.delete("/api/accounts/does_not_exist")
        assert r.status_code == 404


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
