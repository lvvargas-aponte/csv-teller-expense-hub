"""Connection health is recorded at sync time and read from cache.

The point of these tests is the trade the design makes: viewing the Accounts
page must cost zero provider calls, which means health has to survive in the
cache between syncs — including the mapping from a failed access URL back to
the institutions it serves, which a failed fetch can no longer tell us.
"""
from unittest.mock import AsyncMock, patch

import connection_health
import state
from models import AccountBalance


def _account(institution, manual=False, source="simplefin"):
    return AccountBalance(
        id=f"id-{institution}-{manual}",
        institution=institution,
        name=f"{institution} account",
        type="depository",
        subtype="checking",
        available=100.0,
        ledger=100.0,
        source=source,
        manual=manual,
    )


def _batch(url, org, count=1):
    return (url, [{"id": f"a{i}", "_org_name": org} for i in range(count)])


class TestRecordAndBuild:
    def test_healthy_sync_marks_institutions_connected(self, client):
        connection_health.record_simplefin_sync([_batch("https://u:p@b/x", "Chase")], [])

        health = connection_health.build([_account("Chase")])

        assert health == [{"institution": "Chase", "status": "connected", "last_error": None}]

    def test_manual_only_institution_is_manual(self, client):
        health = connection_health.build([_account("Ally", manual=True, source="manual")])

        assert health[0]["status"] == "manual"

    def test_one_synced_account_makes_the_institution_a_connection(self, client):
        """A bank with both a synced and a manual account is still connected —
        otherwise adding a manual row would hide a broken sync."""
        health = connection_health.build([
            _account("Chase"),
            _account("Chase", manual=True, source="manual"),
        ])

        assert len(health) == 1
        assert health[0]["status"] == "connected"

    def test_failed_url_is_attributed_to_the_banks_it_last_served(self, client):
        """A failing access URL returns no accounts and therefore no bank
        names; the institutions remembered from its last success are what let
        the strip say *which* bank to reconnect."""
        url = "https://u:p@bridge/x"
        connection_health.record_simplefin_sync([_batch(url, "Bank of America")], [])

        from simplefin import connection_id
        connection_health.record_simplefin_sync(
            [], [{"id": connection_id(url), "label": "https://***@bridge/x", "error": "Auth failed (403)"}],
        )

        health = connection_health.build([_account("Bank of America")])
        assert health[0]["status"] == "disconnected"
        assert health[0]["last_error"] == "Auth failed (403)"

    def test_recovery_clears_the_error(self, client):
        url = "https://u:p@bridge/x"
        from simplefin import connection_id
        connection_health.record_simplefin_sync(
            [], [{"id": connection_id(url), "label": "m", "error": "boom"}],
        )
        connection_health.record_simplefin_sync([_batch(url, "Chase")], [])

        health = connection_health.build([_account("Chase")])
        assert health[0]["status"] == "connected"

    def test_disabled_brokerage_is_disconnected(self, client):
        connection_health.record_snaptrade_connections(
            [{"brokerage": "Fidelity", "disabled": True},
             {"brokerage": "Robinhood", "disabled": False}],
        )

        health = {h["institution"]: h for h in connection_health.build([
            _account("Fidelity", source="snaptrade"),
            _account("Robinhood", source="snaptrade"),
        ])}

        assert health["Fidelity"]["status"] == "disconnected"
        assert health["Robinhood"]["status"] == "connected"

    def test_never_successful_connection_is_reported_under_its_label(self, client):
        """A URL that failed before it ever returned an account has no
        institution to name — it must still be reported, not swallowed."""
        connection_health.record_simplefin_sync(
            [], [{"id": "abc123", "label": "https://***@bridge/x", "error": "Auth failed (403)"}],
        )

        health = connection_health.build([])

        assert health == [{
            "institution": "https://***@bridge/x",
            "status": "disconnected",
            "last_error": "Auth failed (403)",
        }]


class TestSummaryExposesHealth:
    def test_summary_returns_connections_without_calling_the_provider(self, client, monkeypatch):
        """The unforced summary is what a page load hits; it must answer from
        cache alone."""
        monkeypatch.setattr(state, "SIMPLEFIN_ACCESS_URLS", ["https://u:p@bridge/x"])
        connection_health.record_simplefin_sync([_batch("https://u:p@bridge/x", "Chase")], [])

        never_call = AsyncMock(side_effect=AssertionError("provider was called on a page load"))
        with patch.object(state.simplefin, "list_accounts_by_url", never_call):
            data = client.get("/api/balances/summary").json()

        assert never_call.await_count == 0
        assert "connections" in data

    def test_forced_refresh_records_health(self, client, monkeypatch):
        monkeypatch.setattr(state, "SIMPLEFIN_ACCESS_URLS", ["https://u:p@bridge/x"])
        # ``_org_name`` is what the real client stamps on each account after
        # resolving SimpleFIN's connections array; everything downstream reads
        # that field, so the fixture has to carry it too.
        accounts = [{"id": "acc1", "name": "Checking", "_org_name": "Chase",
                     "balance": "10.00", "transactions": []}]
        errors = [{"id": "dead", "label": "https://***@bridge/y", "error": "Auth failed (403)"}]

        with patch.object(
            state.simplefin, "list_accounts_by_url",
            AsyncMock(return_value=([("https://u:p@bridge/x", accounts)], errors)),
        ):
            data = client.get("/api/balances/summary?force=true").json()

        statuses = {c["institution"]: c["status"] for c in data["connections"]}
        assert statuses["Chase"] == "connected"
        assert statuses["https://***@bridge/y"] == "disconnected"


class TestOutageDoesNotEraseBalances:
    """The cache exists so the Accounts page can answer without calling a
    provider. A provider that cannot be reached has said nothing about its
    accounts — which is not the same as saying they are gone — so its cached
    rows have to survive the failure that used to overwrite them with nothing.
    """

    URL = "https://u:p@bridge/x"

    def _seed_good_sync(self, client, monkeypatch):
        """One successful sync, so there are balances and a cid→bank mapping."""
        monkeypatch.setattr(state, "SIMPLEFIN_ACCESS_URLS", [self.URL])
        accounts = [
            {"id": "acc1", "name": "Checking", "_org_name": "Chase",
             "balance": "1500.00", "transactions": []},
            {"id": "acc2", "name": "Sapphire", "_org_name": "Chase",
             "balance": "-400.00", "transactions": []},
        ]
        with patch.object(
            state.simplefin, "list_accounts_by_url",
            AsyncMock(return_value=([(self.URL, accounts)], [])),
        ):
            return client.get("/api/balances/summary?force=true").json()

    def _blackout(self, client):
        from simplefin import connection_id

        errors = [{"id": connection_id(self.URL), "label": "https://***@bridge/x",
                   "error": "Connection failed"}]
        with patch.object(
            state.simplefin, "list_accounts_by_url",
            AsyncMock(return_value=([], errors)),
        ):
            return client.get("/api/balances/summary?force=true").json()

    def test_a_total_outage_keeps_the_last_good_balances(self, client, monkeypatch):
        before = self._seed_good_sync(client, monkeypatch)
        assert before["total_cash"] == 1500.0
        assert before["total_credit_debt"] == 400.0

        after = self._blackout(client)

        assert [a["id"] for a in after["accounts"]] == ["acc1", "acc2"]
        assert after["total_cash"] == 1500.0
        assert after["total_credit_debt"] == 400.0
        assert after["net_worth"] == before["net_worth"]

    def test_the_outage_is_still_reported(self, client, monkeypatch):
        """Keeping the balances must not make a dead connection look healthy."""
        self._seed_good_sync(client, monkeypatch)

        after = self._blackout(client)

        statuses = {c["institution"]: c["status"] for c in after["connections"]}
        assert statuses["Chase"] == "disconnected"

    def test_the_kept_rows_survive_a_later_page_load(self, client, monkeypatch):
        """They are written back to the cache, not just returned once."""
        self._seed_good_sync(client, monkeypatch)
        self._blackout(client)

        later = client.get("/api/balances/summary").json()

        assert [a["id"] for a in later["accounts"]] == ["acc1", "acc2"]

    def test_a_connection_that_answers_still_replaces_its_own_rows(self, client, monkeypatch):
        """The guard must not pin stale balances: an account a working
        connection stops returning is still dropped."""
        self._seed_good_sync(client, monkeypatch)

        remaining = [{"id": "acc1", "name": "Checking", "_org_name": "Chase",
                      "balance": "1600.00", "transactions": []}]
        with patch.object(
            state.simplefin, "list_accounts_by_url",
            AsyncMock(return_value=([(self.URL, remaining)], [])),
        ):
            after = client.get("/api/balances/summary?force=true").json()

        assert [a["id"] for a in after["accounts"]] == ["acc1"]
        assert after["total_cash"] == 1600.0
        assert after["total_credit_debt"] == 0.0

    def test_a_connection_with_no_history_contributes_nothing(self, client, monkeypatch):
        """A URL that has never synced has no institutions on file, so there is
        nothing to attribute to it and nothing to keep."""
        monkeypatch.setattr(state, "SIMPLEFIN_ACCESS_URLS", [self.URL])
        errors = [{"id": "never-synced", "label": "https://***@bridge/z",
                   "error": "Auth failed (403)"}]
        with patch.object(
            state.simplefin, "list_accounts_by_url",
            AsyncMock(return_value=([], errors)),
        ):
            data = client.get("/api/balances/summary?force=true").json()

        assert data["accounts"] == []
        assert data["total_cash"] == 0.0
