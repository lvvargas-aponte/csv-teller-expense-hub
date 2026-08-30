"""Settling a month — the advisory handshake between the two instances.

Advisory means: each side publishes its own position, either side may declare a
month paid without the other agreeing, and a disagreement about the net is
reported rather than enforced. These tests pin that down, because the tempting
"both must agree" reading is a different product.
"""
import pytest
from fastapi.testclient import TestClient

import identity_service
import state
from db import identity_repo, period_settlements_repo
from main import app
from sheet_sync import service, settlement, shared_view

P1, P2 = "Valeria", "Christy"
PEER_ID = "22222222-2222-2222-2222-222222222222"
PERIOD = "2026-06"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def names(monkeypatch):
    monkeypatch.setattr(shared_view, "PERSON_1_NAME", P1)
    monkeypatch.setattr(shared_view, "PERSON_2_NAME", P2)


@pytest.fixture
def peer():
    """The peer with their REAL id.

    Bootstrap already seeded a placeholder in slot 2, so this adopts over it —
    the same call ``service._adopt_peers`` makes when it reads their claim.
    """
    identity_service.ensure_identity()
    identity_repo.adopt_peer_identity(
        person_slot=2, real_user_id=PEER_ID, display_name=P2
    )
    return PEER_ID


def my_row(tid="t1", owes=56.13, **over):
    """A row I paid; the peer owes ``owes``."""
    txn = {
        "date": "06/15/2026", "description": "Groceries", "amount": -112.26,
        "who": P1, "notes": "", "is_shared": True, "reviewed": True,
        "person_1_owes": 0.0, "person_2_owes": owes,
    }
    txn.update(over)
    state.stored_transactions[tid] = txn


def state_of(client):
    return client.get(f"/api/sync/shared-rows?period={PERIOD}").json()["settlement_state"]


class TestStartingPosition:
    def test_a_month_nobody_has_touched_is_open(self, client):
        assert state_of(client)["state"] == "open"

    def test_an_open_month_reports_neither_side_ready(self, client):
        s = state_of(client)
        assert s["you_ready"] is False
        assert s["peer_ready"] is False
        assert s["paid_at"] is None


class TestReady:
    def test_marking_ready_records_the_net_as_it_stands(self, client):
        my_row(owes=56.13)
        body = client.post(f"/api/sync/periods/{PERIOD}/ready").json()

        assert body["settlement_state"]["state"] == "ready"
        assert body["settlement_state"]["you_ready"] is True
        # Positive: the peer owes me.
        assert body["settlement_state"]["declared_net"] == 56.13

    def test_a_net_i_owe_is_recorded_negative(self, client):
        my_row(who=P2, person_1_owes=40.0, person_2_owes=0.0)
        client.post(f"/api/sync/periods/{PERIOD}/ready")

        assert state_of(client)["declared_net"] == -40.0

    def test_withdrawing_ready_returns_the_month_to_open(self, client):
        my_row()
        client.post(f"/api/sync/periods/{PERIOD}/ready")
        body = client.delete(f"/api/sync/periods/{PERIOD}/ready").json()

        assert body["settlement_state"]["state"] == "open"
        assert body["settlement_state"]["declared_net"] is None

    def test_the_declared_net_does_not_move_when_rows_change_afterwards(self, client):
        my_row(owes=56.13)
        client.post(f"/api/sync/periods/{PERIOD}/ready")
        my_row("t2", owes=10.00)

        s = state_of(client)
        assert s["declared_net"] == 56.13
        assert s["live_net"] == 66.13


class TestPaidIsAdvisory:
    def test_either_side_can_mark_paid_without_the_peer_being_ready(self, client, peer):
        my_row()
        body = client.post(f"/api/sync/periods/{PERIOD}/paid").json()

        assert body["settlement_state"]["state"] == "settled"
        assert body["settlement_state"]["paid_by_me"] is True
        assert body["settlement_state"]["peer_ready"] is False

    def test_marking_paid_without_declaring_ready_first_still_works(self, client):
        my_row()
        assert state_of(client)["you_ready"] is False

        client.post(f"/api/sync/periods/{PERIOD}/paid")
        s = state_of(client)
        assert s["state"] == "settled"
        # Paying implies the rows were complete enough to pay against.
        assert s["you_ready"] is True

    def test_the_peer_marking_paid_settles_the_month_here_too(self, client, peer):
        period_settlements_repo.upsert(
            PERIOD, PEER_ID, ready_at="2026-07-01T10:00:00+00:00",
            pif_at="2026-07-01T10:05:00+00:00", pif_note="Venmo",
        )

        s = state_of(client)
        assert s["state"] == "settled"
        assert s["paid_by_me"] is False
        assert s["paid_by_name"] == P2
        assert s["paid_note"] == "Venmo"

    def test_a_note_is_kept_with_the_settlement(self, client):
        my_row()
        client.post(f"/api/sync/periods/{PERIOD}/paid", json={"note": "Zelle, 3 Jul"})

        assert state_of(client)["paid_note"] == "Zelle, 3 Jul"

    def test_a_blank_note_is_stored_as_no_note(self, client):
        my_row()
        client.post(f"/api/sync/periods/{PERIOD}/paid", json={"note": "   "})

        assert state_of(client)["paid_note"] is None


class TestReopen:
    def test_reopening_clears_my_own_settlement(self, client):
        my_row()
        client.post(f"/api/sync/periods/{PERIOD}/paid")
        body = client.delete(f"/api/sync/periods/{PERIOD}/paid").json()

        assert body["settlement_state"]["state"] != "settled"
        assert body["settlement_state"]["paid_at"] is None

    def test_reopening_does_not_clear_the_peers_settlement(self, client, peer):
        period_settlements_repo.upsert(
            PERIOD, PEER_ID, pif_at="2026-07-01T10:05:00+00:00"
        )
        client.post(f"/api/sync/periods/{PERIOD}/paid")

        client.delete(f"/api/sync/periods/{PERIOD}/paid")

        # One-sided in both directions: they said paid, so it stays paid.
        s = state_of(client)
        assert s["state"] == "settled"
        assert s["paid_by_me"] is False


class TestNetDisagreement:
    def test_matching_nets_report_no_disagreement(self, client, peer):
        my_row(owes=56.13)
        client.post(f"/api/sync/periods/{PERIOD}/ready")
        # Their net is signed from their side, so it is ours negated.
        period_settlements_repo.upsert(
            PERIOD, PEER_ID, ready_at="2026-07-01T10:00:00+00:00", net_amount=-56.13
        )

        assert state_of(client)["net_disagreement"] is None

    def test_differing_nets_are_reported_not_resolved(self, client, peer):
        my_row(owes=56.13)
        client.post(f"/api/sync/periods/{PERIOD}/ready")
        period_settlements_repo.upsert(
            PERIOD, PEER_ID, ready_at="2026-07-01T10:00:00+00:00", net_amount=-40.00
        )

        disagreement = state_of(client)["net_disagreement"]
        assert disagreement == {"mine": 56.13, "theirs": 40.00}

    def test_a_disagreement_never_blocks_marking_paid(self, client, peer):
        my_row(owes=56.13)
        client.post(f"/api/sync/periods/{PERIOD}/ready")
        period_settlements_repo.upsert(
            PERIOD, PEER_ID, ready_at="2026-07-01T10:00:00+00:00", net_amount=-40.00
        )

        body = client.post(f"/api/sync/periods/{PERIOD}/paid")
        assert body.status_code == 200
        assert body.json()["settlement_state"]["state"] == "settled"


class TestSyncablePeriods:
    def test_an_unsettled_month_is_swept(self):
        assert PERIOD in service.syncable_periods()

    def test_a_settled_month_drops_out_of_the_sweep(self, client):
        my_row()
        client.post(f"/api/sync/periods/{PERIOD}/paid")

        assert PERIOD not in service.syncable_periods()
        # But the calendar itself is unchanged — it is the work list that shrank.
        assert PERIOD in service.open_periods()

    def test_reopening_puts_it_back_in_the_sweep(self, client):
        my_row()
        client.post(f"/api/sync/periods/{PERIOD}/paid")
        client.delete(f"/api/sync/periods/{PERIOD}/paid")

        assert PERIOD in service.syncable_periods()


class TestPeriodValidation:
    def test_a_month_before_the_cutover_is_refused(self, client):
        assert client.post("/api/sync/periods/2026-01/paid").status_code == 422

    def test_a_malformed_period_is_refused(self, client):
        assert client.post("/api/sync/periods/nonsense/paid").status_code == 422
