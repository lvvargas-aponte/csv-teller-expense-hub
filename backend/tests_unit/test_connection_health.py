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
