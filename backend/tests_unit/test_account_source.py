"""Every row in /balances/summary must say where it came from.

Without this the frontend infers source from absence — which is how healthy
SnapTrade brokerages ended up rendering as broken SimpleFIN connections.
"""
import state
from institution_normalizer import normalize as normalize_institution


def _by_id(rows):
    return {r["id"]: r for r in rows}


class TestBalanceSummarySource:
    def _seed(self):
        state._balances_cache["simplefin_accounts"] = [
            {"id": "sf_1", "institution": "Chase", "name": "Checking",
             "type": "depository", "subtype": "checking",
             "available": 100.0, "ledger": 100.0},
        ]
        state._balances_cache["snaptrade_accounts"] = [
            {"id": "st_1", "institution": "Robinhood", "name": "Individual",
             "type": "investment", "subtype": "brokerage",
             "available": 500.0, "ledger": 500.0, "manual": False},
        ]
        state._manual_accounts["mn_1"] = {
            "id": "mn_1", "institution": "Synchrony", "name": "HSY",
            "type": "depository", "subtype": "",
            "available": 50.0, "ledger": 50.0,
        }

    def test_each_row_reports_its_source(self, client):
        self._seed()
        rows = _by_id(client.get("/api/balances/summary").json()["accounts"])

        assert rows["sf_1"]["source"] == "simplefin"
        assert rows["st_1"]["source"] == "snaptrade"
        assert rows["mn_1"]["source"] == "manual"

    def test_source_is_stamped_not_read_from_cache(self, client):
        """A cached dict carrying a stale/wrong source must not win — the
        append helper knows the truth, the cache doesn't."""
        state._balances_cache["snaptrade_accounts"] = [
            {"id": "st_1", "institution": "Robinhood", "name": "Individual",
             "type": "investment", "subtype": "brokerage",
             "available": 500.0, "ledger": 500.0, "source": "simplefin"},
        ]
        rows = _by_id(client.get("/api/balances/summary").json()["accounts"])
        assert rows["st_1"]["source"] == "snaptrade"

    def test_manual_source_survives_disconnected_shadows(self, client):
        state._manual_accounts["shadow"] = {
            "id": "shadow", "institution": "Chase", "name": "Old Checking",
            "type": "depository", "subtype": "",
            "available": 0.0, "ledger": 0.0,
            "disconnected_from": "simplefin",
        }
        rows = _by_id(client.get("/api/balances/summary").json()["accounts"])
        assert rows["shadow"]["source"] == "manual"
        assert rows["shadow"]["disconnected_from"] == "simplefin"


class TestInstitutionNormalizer:
    def test_collapses_etrade_spellings(self):
        assert normalize_institution("E-Trade") == normalize_institution("E*Trade")

    def test_passes_through_unknown_names(self):
        assert normalize_institution("Ally Bank") == "Ally Bank"

    def test_collapses_chase_spellings(self):
        assert normalize_institution("Chase Bank") == "Chase"
        assert normalize_institution("Chase") == "Chase"

    def test_handles_blank(self):
        assert normalize_institution("") == ""
        assert normalize_institution(None) == ""

    def test_applied_when_a_transaction_is_built(self):
        """Teller-era rows say 'Chase', SimpleFIN says 'Chase Bank' — every
        writer goes through this constructor, so neither spelling reaches the
        store and the table can't show them as two institutions."""
        from csv_parser import BankType, Transaction

        made = [
            Transaction(
                date="2026-01-15", description="STARBUCKS", amount=4.50,
                source=BankType.SIMPLEFIN, transaction_id=tid, institution=inst,
            )
            for tid, inst in (("t_old", "Chase"), ("t_new", "Chase Bank"))
        ]
        assert [t.institution for t in made] == ["Chase", "Chase"]

    def test_stored_rows_are_served_as_stored(self, client):
        """Reads don't rewrite: the store holds canonical names already."""
        state.stored_transactions["t1"] = {
            "transaction_id": "t1", "id": "t1", "date": "2026-01-15",
            "amount": 4.50, "description": "STARBUCKS",
            "transaction_type": "debit", "source": "simplefin",
            "institution": "Chase",
        }
        rows = _by_id(client.get("/api/transactions/all").json())
        assert rows["t1"]["institution"] == "Chase"

    def test_applied_to_summary_rows(self, client):
        state._balances_cache["snaptrade_accounts"] = [
            {"id": "st_1", "institution": "E-Trade", "name": "Brokerage",
             "type": "investment", "subtype": "brokerage",
             "available": 1.0, "ledger": 1.0},
        ]
        state._balances_cache["simplefin_accounts"] = [
            {"id": "sf_1", "institution": "E*Trade", "name": "Individual",
             "type": "investment", "subtype": "brokerage",
             "available": 2.0, "ledger": 2.0},
        ]
        rows = _by_id(client.get("/api/balances/summary").json()["accounts"])
        assert rows["st_1"]["institution"] == rows["sf_1"]["institution"]
