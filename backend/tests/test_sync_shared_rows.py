"""The combined view of both sides' shared rows for one month."""
import pytest
from fastapi.testclient import TestClient

import identity_service
import state
from db import peer_transactions_repo, sync_state_repo
from main import app
from sheet_sync import shared_view

P1, P2 = "Valeria", "Christy"
PEER_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def names(monkeypatch):
    monkeypatch.setattr(shared_view, "PERSON_1_NAME", P1)
    monkeypatch.setattr(shared_view, "PERSON_2_NAME", P2)


def mine(tid, **over):
    txn = {
        "date": "06/15/2026", "description": "Groceries", "amount": -112.25,
        "who": P1, "notes": "", "is_shared": True, "reviewed": True,
        "person_1_owes": 0.0, "person_2_owes": 56.13,
    }
    txn.update(over)
    state.stored_transactions[tid] = txn
    return txn


def theirs(txn_id=f"{PEER_ID}:x1", **over):
    row = {
        "txn_id": txn_id, "owner_user_id": PEER_ID, "date": "2026-06-02",
        "description": "Cleaning", "amount": 150, "who": P2,
        "person_1_owes": 75, "person_2_owes": 0, "notes": "",
        "reviewed": True, "settles_in_period": "2026-06",
    }
    row.update(over)
    peer_transactions_repo.upsert_many([row])
    return row


class TestShape:
    def test_returns_identity_and_period(self, client):
        identity_service.ensure_identity()
        body = client.get("/api/sync/shared-rows?period=2026-06").json()

        assert body["period"] == "2026-06"
        assert body["me"]["display_name"] == P1
        assert body["me"]["person_slot"] == 1

    def test_empty_month_returns_no_rows(self, client):
        identity_service.ensure_identity()
        assert client.get("/api/sync/shared-rows?period=2026-06").json()["rows"] == []


class TestOwnership:
    def test_your_row_and_their_row_appear_together_and_are_labelled(self, client):
        identity_service.ensure_identity()
        mine("t1")
        theirs()

        rows = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"]

        assert {r["owner"] for r in rows} == {"me", "peer"}
        assert [r["description"] for r in rows] == ["Cleaning", "Groceries"]  # date order
        peer_row = next(r for r in rows if r["owner"] == "peer")
        assert peer_row["owner_name"] == P2

    def test_rows_from_another_month_are_excluded(self, client):
        identity_service.ensure_identity()
        mine("t1", date="07/04/2026")
        assert client.get("/api/sync/shared-rows?period=2026-06").json()["rows"] == []


class TestOwesResolvedBySlot:
    def test_when_you_paid_your_side_is_null_and_theirs_is_set(self, client):
        identity_service.ensure_identity()
        mine("t1", who=P1, person_1_owes=0.0, person_2_owes=56.13)

        row = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"][0]

        assert row["you_owe"] is None
        assert row["they_owe"] == 56.13

    def test_when_they_paid_your_side_carries_the_amount(self, client):
        identity_service.ensure_identity()
        mine("t1", who=P2, person_1_owes=56.13, person_2_owes=0.0)

        row = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"][0]

        assert row["you_owe"] == 56.13
        assert row["they_owe"] is None

    def test_a_peer_row_is_resolved_by_slot_too(self, client):
        identity_service.ensure_identity()
        theirs()

        row = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"][0]

        assert row["you_owe"] == 75.0


class TestPublishability:
    def _reason(self, client):
        rows = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"]
        return rows[0]["publishable"], rows[0]["blocked_reason"]

    def test_a_complete_row_is_publishable(self, client):
        identity_service.ensure_identity()
        mine("t1")
        assert self._reason(client) == (True, None)

    def test_an_unreviewed_row_is_flagged(self, client):
        identity_service.ensure_identity()
        mine("t1", reviewed=False)
        publishable, reason = self._reason(client)
        assert publishable is False and "review" in reason.lower()

    def test_a_row_with_no_split_is_flagged(self, client):
        """The rows sub-project B deliberately withholds must not be invisible."""
        identity_service.ensure_identity()
        mine("t1", who=P1, person_1_owes=0.0, person_2_owes=0.0)
        publishable, reason = self._reason(client)
        assert publishable is False and "split" in reason.lower()

    def test_a_row_with_an_unrecognised_who_is_flagged(self, client):
        identity_service.ensure_identity()
        mine("t1", who="Mom")
        publishable, reason = self._reason(client)
        assert publishable is False and "Mom" in reason

    def test_a_peer_row_is_always_publishable(self, client):
        identity_service.ensure_identity()
        theirs()
        assert self._reason(client) == (True, None)


class TestDisputes:
    def test_a_dispute_against_your_row_is_shown(self, client):
        me = identity_service.ensure_identity()
        mine("t1")
        sync_state_repo.set_disputes(f"{me['user_id']}:t1", "Y", P2, "that was mine")

        row = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"][0]

        assert row["dispute_flag"] == "Y"
        assert row["dispute_by"] == P2
        assert row["dispute_note"] == "that was mine"

    def test_a_dispute_you_raised_on_their_row_is_shown(self, client):
        identity_service.ensure_identity()
        theirs()
        peer_transactions_repo.set_dispute(f"{PEER_ID}:x1", "Y", P1, "not shared")

        row = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"][0]

        assert row["dispute_flag"] == "Y"


class TestRoute:
    def test_a_malformed_period_is_422(self, client):
        assert client.get("/api/sync/shared-rows?period=June").status_code == 422

    def test_a_period_before_the_cutover_is_422(self, client):
        res = client.get("/api/sync/shared-rows?period=2026-05")
        assert res.status_code == 422
        assert "cutover" in res.json()["detail"].lower()
