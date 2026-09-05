"""Tests for the accounts router — list, delete, account details."""
import analytics
import state


class TestListAccounts:
    def test_returns_empty_when_no_urls(self, client, monkeypatch):
        # Force no access URLs for this test regardless of what's in the env
        monkeypatch.setattr(state, "SIMPLEFIN_ACCESS_URLS", [])
        r = client.get("/api/accounts")
        assert r.status_code == 200
        assert r.json() == []

    def test_includes_manual_accounts(self, client, monkeypatch):
        """Manual accounts list alongside synced ones — otherwise the Linked
        Accounts modal can't offer a way to delete them."""
        monkeypatch.setattr(state, "SIMPLEFIN_ACCESS_URLS", [])
        created = client.post(
            "/api/balances/manual",
            json={
                "institution": "Discover", "name": "Discover Credit Card",
                "type": "credit", "available": 405.73, "ledger": 405.73,
            },
        ).json()

        rows = client.get("/api/accounts").json()
        assert [r["id"] for r in rows] == [created["id"]]
        assert rows[0]["_source"] == "manual"
        assert rows[0]["institution"] == {"name": "Discover"}
        assert rows[0]["name"] == "Discover Credit Card"
        assert rows[0]["type"] == "credit"

    def test_excludes_simplefin_shadows(self, client, monkeypatch):
        """A shadow exists to keep a hidden SimpleFIN account out of this
        list, so it must not resurface as a manual row."""
        monkeypatch.setattr(state, "SIMPLEFIN_ACCESS_URLS", [])
        state._manual_accounts["acc_hidden"] = {
            "id": "acc_hidden",
            "institution": "Chase", "name": "TOTAL CHECKING",
            "type": "depository", "subtype": "",
            "available": 0.0, "ledger": 0.0,
            "disconnected_from": "simplefin",
            "disconnected_at": "2026-01-01T00:00:00",
        }

        assert client.get("/api/accounts").json() == []


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


class TestInstitutionNormalization:
    """/api/accounts and /api/balances/summary are matched against each other
    by institution name (that pairing is what tells the UI a connection is
    healthy), so both endpoints must spell an institution the same way."""

    def test_manual_account_institution_is_normalized(self, client, monkeypatch):
        monkeypatch.setattr(state, "SIMPLEFIN_ACCESS_URLS", [])
        client.post(
            "/api/balances/manual",
            json={
                "institution": "Chase Bank", "name": "TOTAL CHECKING",
                "type": "depository", "available": 100.0, "ledger": 100.0,
            },
        )

        rows = client.get("/api/accounts").json()
        summary = client.get("/api/balances/summary").json()

        assert rows[0]["institution"] == {"name": "Chase"}
        assert {a["institution"] for a in summary["accounts"]} == {"Chase"}


class TestAccountsMetadata:
    """The subtype list the frontend classifier reads, so the two copies of
    the rule cannot drift apart silently."""

    def test_metadata_exposes_the_investment_subtypes(self, client):
        r = client.get("/api/accounts/metadata")

        assert r.status_code == 200
        subtypes = r.json()["investment_subtypes"]
        assert set(subtypes) == set(analytics._INVESTMENT_SUBTYPES)
        assert "roth ira" in subtypes
        assert subtypes == sorted(subtypes)


class TestManualCreditAvailable:
    """A manual card's entered available credit used to be overwritten with the
    amount owed, so the Add form asked for a figure it then threw away — and
    the Accounts row printed the balance twice, once captioned "available"."""

    def _add(self, client, **over):
        body = {
            "institution": "Discover", "name": "Store Card", "type": "credit",
            "ledger": 1200.0, "available": 3800.0,
        }
        body.update(over)
        return client.post("/api/balances/manual", json=body).json()

    def _row(self, client, acct_id):
        rows = client.get("/api/balances/summary").json()["accounts"]
        return next(r for r in rows if r["id"] == acct_id)

    def test_entered_available_credit_survives_the_summary(self, client):
        created = self._add(client)

        row = self._row(client, created["id"])
        assert row["ledger"] == 1200.0
        assert row["available"] == 3800.0

    def test_nothing_entered_still_mirrors_what_is_owed(self, client):
        """The shape every SimpleFIN credit row has. The UI reads
        available == ledger as "no available-credit figure known"."""
        created = self._add(client, available=0.0)

        row = self._row(client, created["id"])
        assert row["available"] == row["ledger"] == 1200.0

    def test_totals_ignore_available_on_a_credit_row(self, client):
        """Debt and net worth are computed from `ledger`; changing what
        `available` carries must not move either."""
        self._add(client)
        entered = client.get("/api/balances/summary").json()

        state._manual_accounts.clear()
        self._add(client, available=0.0)
        mirrored = client.get("/api/balances/summary").json()

        assert entered["total_credit_debt"] == mirrored["total_credit_debt"] == 1200.0
        assert entered["net_worth"] == mirrored["net_worth"]


class TestClosedAccounts:
    """SimpleFIN has no open/closed concept — the protocol's Account object has
    no status field at all — so a closed account keeps arriving on every fetch.
    ``account_details.closed_on`` is the user's way to say so. A closed account
    keeps its row and its history but counts toward no total."""

    def _add(self, client, **over):
        body = {
            "institution": "Barclays", "name": "Old Card", "type": "credit",
            "ledger": 500.0, "available": 0.0,
        }
        body.update(over)
        return client.post("/api/balances/manual", json=body).json()["id"]

    def _close(self, client, acct_id, on="2026-05-01"):
        client.put(f"/api/accounts/{acct_id}/details", json={"closed_on": on})

    def _row(self, summary, acct_id):
        return next(r for r in summary["accounts"] if r["id"] == acct_id)

    def test_closed_credit_leaves_the_totals_but_keeps_its_row(self, client):
        acct_id = self._add(client)
        before = client.get("/api/balances/summary").json()
        assert before["total_credit_debt"] == 500.0

        self._close(client, acct_id)
        after = client.get("/api/balances/summary").json()

        assert after["total_credit_debt"] == 0.0
        assert after["net_worth"] == before["net_worth"] + 500.0
        row = self._row(after, acct_id)
        assert row["closed_on"] == "2026-05-01"

    def test_closed_cash_leaves_the_cash_total(self, client):
        acct_id = self._add(
            client, type="depository", name="Old Savings",
            available=2500.0, ledger=2500.0,
        )
        assert client.get("/api/balances/summary").json()["total_cash"] == 2500.0

        self._close(client, acct_id)
        after = client.get("/api/balances/summary").json()

        assert after["total_cash"] == 0.0
        assert self._row(after, acct_id)["closed_on"] == "2026-05-01"

    def test_clearing_the_date_reopens_the_account(self, client):
        acct_id = self._add(client)
        self._close(client, acct_id)
        assert client.get("/api/balances/summary").json()["total_credit_debt"] == 0.0

        client.put(f"/api/accounts/{acct_id}/details", json={"closed_on": None})
        after = client.get("/api/balances/summary").json()

        assert after["total_credit_debt"] == 500.0
        assert self._row(after, acct_id)["closed_on"] is None

    def test_closed_card_is_absent_from_utilization(self, client):
        """Its limit is gone with it — counting it would divide the balances by
        headroom that no longer exists."""
        acct_id = self._add(client)
        client.put(
            f"/api/accounts/{acct_id}/details",
            json={"credit_limit": 2000.0},
        )
        before = client.get("/api/accounts/credit-health").json()
        assert [a["account_id"] for a in before["accounts"]] == [acct_id]
        assert before["overall_utilization_pct"] == 25.0

        client.put(
            f"/api/accounts/{acct_id}/details",
            json={"credit_limit": 2000.0, "closed_on": "2026-05-01"},
        )
        after = client.get("/api/accounts/credit-health").json()

        assert after["accounts"] == []
        assert after["overall_utilization_pct"] is None


class TestInstallmentVocabulary:
    """The set lived in credit_health_service and credit_factors as two copies (the latter since deleted).
    It now has one owner in analytics, served from here so the JS side does not
    become a third."""

    def test_metadata_exposes_the_installment_subtypes(self, client):
        r = client.get("/api/accounts/metadata")

        assert r.status_code == 200
        subtypes = r.json()["installment_subtypes"]
        assert set(subtypes) == set(analytics._INSTALLMENT_SUBTYPES)
        assert "mortgage" in subtypes
        assert subtypes == sorted(subtypes)

    def test_is_installment_requires_a_credit_account(self):
        assert analytics.is_installment("credit", "mortgage") is True
        assert analytics.is_installment("credit", "MORTGAGE") is True
        assert analytics.is_installment("credit", "credit_card") is False
        # A checking account someone labelled "loan" is still not credit.
        assert analytics.is_installment("depository", "loan") is False

    def test_a_loan_is_still_left_out_of_utilization(self, client, monkeypatch):
        """Guards the import refactor: the behaviour these two modules shared
        must survive them no longer each declaring the set."""
        monkeypatch.setattr(state, "SIMPLEFIN_ACCESS_URLS", [])
        created = client.post(
            "/api/balances/manual",
            json={
                "institution": "Truist", "name": "Mortgage", "type": "credit",
                "subtype": "loan", "ledger": 400000.0, "available": 0.0,
            },
        ).json()
        client.put(
            f"/api/accounts/{created['id']}/details", json={"credit_limit": 500000.0}
        )

        health = client.get("/api/accounts/credit-health").json()

        # Not merely unrated — absent. A 500k limit on a mortgage would swamp
        # every card in the ratio, and the row itself carried no percentage to
        # show, so the composition drops it rather than listing it blank.
        assert all(a["account_id"] != created["id"] for a in health["accounts"])
        assert health["overall_utilization_pct"] is None
