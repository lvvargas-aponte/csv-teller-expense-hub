"""Attributing transactions to a property.

Tagging is what turns a pro forma into observed performance, so the
validation matters: a typo'd property id would vanish from every rollup
without a word.
"""
import pytest

import properties
import state
from db import properties_repo_memory


@pytest.fixture
def repo():
    return properties_repo_memory.install_for_tests()


@pytest.fixture
def prop(repo):
    return repo.upsert_property({
        "id": "prop_1", "name": "Maple St", "status": "rental",
        "monthly_rent": 3000,
    })


def _txn(tid="t1", description="ZELLE FROM TENANT J SMITH 0421", **overrides):
    row = {
        "id": tid, "transaction_id": tid, "date": "2026-08-01",
        "description": description, "amount": 3000.0,
        "transaction_type": "credit", "source": "simplefin",
        "is_shared": False, "reviewed": False,
        "person_1_owes": 0.0, "person_2_owes": 0.0, "notes": "",
    }
    row.update(overrides)
    state.stored_transactions[tid] = row
    return row


def _update_payload(**overrides):
    payload = {"is_shared": False}
    payload.update(overrides)
    return payload


class TestSingleUpdate:
    def test_tags_a_transaction(self, client, prop):
        _txn()
        response = client.put(
            "/api/transactions/t1", json=_update_payload(property_id="prop_1")
        )
        assert response.status_code == 200
        assert response.json()["property_id"] == "prop_1"

    def test_empty_string_clears_the_tag(self, client, prop):
        _txn(property_id="prop_1")
        response = client.put(
            "/api/transactions/t1", json=_update_payload(property_id="")
        )
        assert response.json()["property_id"] is None

    def test_omitting_the_field_is_a_no_op(self, client, prop):
        _txn(property_id="prop_1")
        response = client.put("/api/transactions/t1", json=_update_payload())
        assert response.json()["property_id"] == "prop_1"

    def test_unknown_property_is_rejected(self, client, prop):
        """A typo would otherwise disappear from every rollup silently."""
        _txn()
        response = client.put(
            "/api/transactions/t1", json=_update_payload(property_id="prop_typo")
        )
        assert response.status_code == 422
        assert "does not exist" in response.json()["detail"]


class TestBulkUpdate:
    def test_tags_many_at_once(self, client, prop):
        _txn("t1")
        _txn("t2")
        response = client.put("/api/transactions/bulk", json={
            "transaction_ids": ["t1", "t2"],
            "is_shared": False,
            "property_id": "prop_1",
        })
        assert response.status_code == 200
        assert state.stored_transactions["t1"]["property_id"] == "prop_1"
        assert state.stored_transactions["t2"]["property_id"] == "prop_1"

    def test_bulk_clear(self, client, prop):
        _txn("t1", property_id="prop_1")
        client.put("/api/transactions/bulk", json={
            "transaction_ids": ["t1"], "is_shared": False, "property_id": "",
        })
        assert state.stored_transactions["t1"]["property_id"] is None

    def test_unknown_property_rejects_the_whole_batch(self, client, prop):
        """Validated once up front, so a bad id can't tag half the rows."""
        _txn("t1")
        response = client.put("/api/transactions/bulk", json={
            "transaction_ids": ["t1"], "is_shared": False,
            "property_id": "prop_typo",
        })
        assert response.status_code == 422
        assert "property_id" not in state.stored_transactions["t1"]


class TestActualsIntegration:
    def test_tagged_rent_shows_up_in_actuals(self, client, prop):
        _txn("t1", amount=3000, transaction_type="credit")
        client.put("/api/transactions/t1", json=_update_payload(property_id="prop_1"))

        econ = client.get("/api/properties/prop_1").json()
        assert econ["actual"]["total_inflow"] == 3000.0

    def test_tagged_repair_shows_up_as_outflow(self, client, prop):
        _txn("t1", description="HOME DEPOT", amount=450,
             transaction_type="debit")
        client.put("/api/transactions/t1", json=_update_payload(property_id="prop_1"))

        econ = client.get("/api/properties/prop_1").json()
        assert econ["actual"]["total_outflow"] == 450.0

    def test_untagged_transactions_stay_out(self, client, prop):
        _txn("t1", amount=9999)
        econ = client.get("/api/properties/prop_1").json()
        assert econ["actual"]["total_inflow"] == 0.0


class TestSuggestions:
    def test_operating_account_match(self, repo, client):
        repo.upsert_property({
            "id": "prop_1", "name": "Maple St", "status": "rental",
            "operating_account_id": "acct_9",
        })
        _txn("t1", account_id="acct_9")

        suggestions = client.get("/api/properties/suggest-transactions").json()
        assert len(suggestions) == 1
        assert suggestions[0]["property_id"] == "prop_1"
        assert "operating account" in suggestions[0]["reason"]

    def test_merchant_key_match_survives_a_changing_reference(self, repo, client):
        """The point of routing through _normalize_merchant: the trailing
        digits differ month to month but the key is stable."""
        repo.upsert_property({
            "id": "prop_1", "name": "Maple St", "status": "rental",
            "rules": [{"match": "merchant_key",
                       "value": "ZELLE FROM TENANT J SMITH 0421"}],
        })
        _txn("t1", description="ZELLE FROM TENANT J SMITH 0876")

        suggestions = client.get("/api/properties/suggest-transactions").json()
        assert len(suggestions) == 1
        assert suggestions[0]["property_id"] == "prop_1"

    def test_description_substring_match(self, repo, client):
        repo.upsert_property({
            "id": "prop_1", "name": "Maple St", "status": "rental",
            "rules": [{"match": "description_contains", "value": "maple"}],
        })
        _txn("t1", description="MAPLE ST PLUMBING REPAIR")

        suggestions = client.get("/api/properties/suggest-transactions").json()
        assert suggestions[0]["property_id"] == "prop_1"

    def test_already_tagged_transactions_are_skipped(self, repo, client):
        repo.upsert_property({
            "id": "prop_1", "name": "Maple St", "status": "rental",
            "operating_account_id": "acct_9",
        })
        _txn("t1", account_id="acct_9", property_id="prop_1")
        assert client.get("/api/properties/suggest-transactions").json() == []

    def test_no_match_yields_nothing(self, repo, client):
        repo.upsert_property({
            "id": "prop_1", "name": "Maple St", "status": "rental",
            "rules": [{"match": "description_contains", "value": "nomatch"}],
        })
        _txn("t1", description="COFFEE SHOP")
        assert client.get("/api/properties/suggest-transactions").json() == []

    def test_suggestions_never_write_the_tag(self, repo, client):
        """Auto-applying a wrong rent payment would distort NOI, cash flow
        and the retirement projection with no visible cause."""
        repo.upsert_property({
            "id": "prop_1", "name": "Maple St", "status": "rental",
            "operating_account_id": "acct_9",
        })
        _txn("t1", account_id="acct_9")

        client.get("/api/properties/suggest-transactions")
        assert state.stored_transactions["t1"].get("property_id") is None

    def test_empty_rule_values_are_ignored(self, repo, client):
        """A blank rule must not match everything."""
        repo.upsert_property({
            "id": "prop_1", "name": "Maple St", "status": "rental",
            "rules": [{"match": "description_contains", "value": ""}],
        })
        _txn("t1", description="ANYTHING AT ALL")
        assert client.get("/api/properties/suggest-transactions").json() == []

    def test_no_properties_yields_nothing(self, client):
        _txn("t1")
        assert client.get("/api/properties/suggest-transactions").json() == []

    def test_limit_is_respected(self, repo, client):
        repo.upsert_property({
            "id": "prop_1", "name": "Maple St", "status": "rental",
            "operating_account_id": "acct_9",
        })
        for i in range(10):
            _txn(f"t{i}", account_id="acct_9")
        suggestions = client.get(
            "/api/properties/suggest-transactions", params={"limit": 3}
        ).json()
        assert len(suggestions) == 3

    def test_route_is_not_captured_as_a_property_id(self, client):
        """/properties/suggest-transactions must not hit /{property_id}."""
        assert client.get("/api/properties/suggest-transactions").status_code == 200
