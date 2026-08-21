"""The sync endpoints. The gateway is faked; the database is real."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import state
from db import sync_state_repo
from main import app
from sheet_sync import service
from sheet_sync.gateway import InMemoryGateway

P1, P2 = "Valeria", "Christy"
HEADERS = [
    "Transaction Date", "Description", "Amount", "Who",
    f"What {P1} Owes", f"What {P2} Owes", "Notes", "Reviewed",
    "Dispute", "Dispute By", "Dispute Note", "Txn ID", "Owner", "Carried From",
]


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def names(monkeypatch):
    monkeypatch.setattr(service, "PERSON_1_NAME", P1, raising=False)
    monkeypatch.setattr(service, "PERSON_2_NAME", P2, raising=False)


@pytest.fixture
def fake_gateway():
    gw = InMemoryGateway({"June 2026": [list(HEADERS)]})
    with patch.object(service, "build_gateway", return_value=gw):
        yield gw


class TestSyncShared:
    def test_syncs_one_period_on_request(self, client, fake_gateway):
        state.stored_transactions["t1"] = {
            "date": "06/15/2026", "description": "Groceries", "amount": -112.25,
            "who": P1, "notes": "", "is_shared": True, "reviewed": True,
            "person_1_owes": 56.13, "person_2_owes": 56.13,
        }

        res = client.post("/api/sync/shared", json={"period": "2026-06"})

        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["results"][0]["rows_pushed"] == 1
        assert len(fake_gateway.read_rows("June 2026")) == 2

    def test_dry_run_writes_nothing(self, client, fake_gateway):
        state.stored_transactions["t1"] = {
            "date": "06/15/2026", "description": "Groceries", "amount": -112.25,
            "who": P1, "notes": "", "is_shared": True, "reviewed": True,
            "person_1_owes": 56.13, "person_2_owes": 56.13,
        }

        res = client.post("/api/sync/shared", json={"period": "2026-06", "dry_run": True})

        assert res.json()["results"][0]["rows_pushed"] == 1
        assert len(fake_gateway.read_rows("June 2026")) == 1

    def test_an_invalid_period_is_rejected(self, client, fake_gateway):
        assert client.post("/api/sync/shared", json={"period": "June"}).status_code == 422

    def test_a_period_before_the_cutover_is_rejected(self, client, fake_gateway):
        res = client.post("/api/sync/shared", json={"period": "2026-05"})
        assert res.status_code == 422
        assert "cutover" in res.json()["detail"].lower()

    def test_disabled_sync_returns_a_clear_error(self, client):
        with patch.object(service, "build_gateway", side_effect=service.SyncDisabled("off")):
            res = client.post("/api/sync/shared", json={"period": "2026-06"})

        assert res.status_code == 503
        assert "off" in res.json()["detail"]

    def test_a_refusal_is_reported_as_success_with_a_refused_status(self, client, fake_gateway):
        """A refusal is an answer, not a transport failure — the UI shows the reason."""
        from sheet_sync import sync_sheet
        from sheet_sync.guards import Claim

        sync_sheet.write_claim(fake_gateway, Claim(
            user_id="22222222-2222-2222-2222-222222222222", display_name=P2,
            person_slot=2, contract_version="9.9",
            person_1_name=P1, person_2_name=P2,
        ))

        res = client.post("/api/sync/shared", json={"period": "2026-06"})

        assert res.status_code == 200
        assert res.json()["status"] == "refused"
        assert res.json()["results"][0]["refusal_reason"] == "contract_version"


class TestStatus:
    def test_reports_the_flag_and_an_empty_feed(self, client, monkeypatch):
        monkeypatch.setattr(service, "SHEET_SYNC_ENABLED", False)
        body = client.get("/api/sync/status").json()

        assert body["enabled"] is False
        assert body["corrections"] == []
        assert body["last_run"] is None

    def test_reports_enabled_true_when_the_flag_is_on(self, client, monkeypatch):
        monkeypatch.setattr(service, "SHEET_SYNC_ENABLED", True)
        assert client.get("/api/sync/status").json()["enabled"] is True

    def test_reports_the_last_run(self, client, fake_gateway):
        client.post("/api/sync/shared", json={"period": "2026-06"})

        body = client.get("/api/sync/status").json()
        assert body["last_run"]["period"] == "2026-06"
        assert body["last_run"]["status"] == "ok"

    def test_status_serializes_a_dispute_with_a_raw_datetime(self, client):
        """``list_disputes_against_me`` rows carry a raw ``datetime`` for
        ``sheet_synced_at`` — unlike the corrections/run-log dicts, which are
        already ISO strings. Confirm ``jsonable_encoder`` handles that rather
        than assuming it: this is the one field shaped differently."""
        sync_state_repo.mark_synced("u1:t1", "t1", "2026-06")
        sync_state_repo.set_disputes("u1:t1", "Y", P2, "not mine")

        res = client.get("/api/sync/status")

        assert res.status_code == 200
        dispute = res.json()["disputes_against_me"][0]
        assert dispute["txn_id"] == "u1:t1"
        assert dispute["sheet_synced_at"] is not None


class TestAcknowledge:
    def test_acknowledges_a_correction(self, client):
        sync_state_repo.record_corrections(
            "2026-06",
            [{"txn_id": "u1:t1", "column_name": "Amount",
              "sheet_value": "9.99", "app_value": "112.25"}],
        )
        cid = sync_state_repo.list_unacknowledged()[0]["id"]

        res = client.post(f"/api/sync/corrections/{cid}/acknowledge")

        assert res.status_code == 200
        assert res.json()["acknowledged"] is True
        assert client.get("/api/sync/status").json()["corrections"] == []

    def test_an_unknown_correction_is_404(self, client):
        assert client.post("/api/sync/corrections/9999/acknowledge").status_code == 404
