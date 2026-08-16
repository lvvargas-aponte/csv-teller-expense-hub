"""Integration tests for the instance identity and peer registry."""
import pytest
from sqlalchemy import text

from db import identity_repo
from db.base import sync_engine


class TestInstanceIdentity:
    def test_get_identity_returns_none_when_unset(self):
        assert identity_repo.get_identity() is None

    def test_set_identity_then_get_round_trips(self):
        identity_repo.set_identity(
            user_id="11111111-1111-1111-1111-111111111111",
            display_name="Valeria",
            person_slot=1,
        )
        me = identity_repo.get_identity()
        assert me["user_id"] == "11111111-1111-1111-1111-111111111111"
        assert me["display_name"] == "Valeria"
        assert me["person_slot"] == 1
        assert me["created_at"] is not None

    def test_set_identity_twice_updates_rather_than_duplicates(self):
        identity_repo.set_identity(
            user_id="11111111-1111-1111-1111-111111111111",
            display_name="Valeria",
            person_slot=1,
        )
        identity_repo.set_identity(
            user_id="11111111-1111-1111-1111-111111111111",
            display_name="Val",
            person_slot=1,
        )
        assert identity_repo.get_identity()["display_name"] == "Val"
        with sync_engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM instance_identity")).scalar()
        assert count == 1

    def test_invalid_person_slot_is_rejected(self):
        with pytest.raises(Exception):
            identity_repo.set_identity(
                user_id="11111111-1111-1111-1111-111111111111",
                display_name="Nobody",
                person_slot=3,
            )


class TestPeers:
    def test_list_peers_empty_by_default(self):
        assert identity_repo.list_peers() == []

    def test_upsert_peer_then_list(self):
        identity_repo.upsert_peer(
            user_id="22222222-2222-2222-2222-222222222222",
            display_name="Christy",
            person_slot=2,
        )
        peers = identity_repo.list_peers()
        assert len(peers) == 1
        assert peers[0]["display_name"] == "Christy"
        assert peers[0]["person_slot"] == 2

    def test_upsert_peer_updates_existing(self):
        identity_repo.upsert_peer(
            user_id="22222222-2222-2222-2222-222222222222",
            display_name="Christy",
            person_slot=2,
        )
        identity_repo.upsert_peer(
            user_id="22222222-2222-2222-2222-222222222222",
            display_name="Christina",
            person_slot=2,
        )
        peers = identity_repo.list_peers()
        assert len(peers) == 1
        assert peers[0]["display_name"] == "Christina"

    def test_delete_peer(self):
        identity_repo.upsert_peer(
            user_id="22222222-2222-2222-2222-222222222222",
            display_name="Christy",
            person_slot=2,
        )
        assert identity_repo.delete_peer("22222222-2222-2222-2222-222222222222") is True
        assert identity_repo.list_peers() == []

    def test_delete_missing_peer_returns_false(self):
        assert identity_repo.delete_peer("33333333-3333-3333-3333-333333333333") is False


class TestIdentityService:
    def test_ensure_identity_creates_identity_and_peer(self, monkeypatch):
        import identity_service

        monkeypatch.setattr(identity_service, "PERSON_1_NAME", "Valeria")
        monkeypatch.setattr(identity_service, "PERSON_2_NAME", "Christy")
        monkeypatch.setattr(identity_service, "INSTANCE_PERSON_SLOT", 1)

        me = identity_service.ensure_identity()
        assert me["display_name"] == "Valeria"
        assert me["person_slot"] == 1

        peers = identity_repo.list_peers()
        assert len(peers) == 1
        assert peers[0]["display_name"] == "Christy"
        assert peers[0]["person_slot"] == 2

    def test_ensure_identity_is_idempotent(self, monkeypatch):
        import identity_service

        monkeypatch.setattr(identity_service, "PERSON_1_NAME", "Valeria")
        monkeypatch.setattr(identity_service, "PERSON_2_NAME", "Christy")
        monkeypatch.setattr(identity_service, "INSTANCE_PERSON_SLOT", 1)

        first = identity_service.ensure_identity()
        second = identity_service.ensure_identity()
        assert first["user_id"] == second["user_id"]
        assert len(identity_repo.list_peers()) == 1

    def test_slot_two_instance_gets_the_other_name(self, monkeypatch):
        import identity_service

        monkeypatch.setattr(identity_service, "PERSON_1_NAME", "Valeria")
        monkeypatch.setattr(identity_service, "PERSON_2_NAME", "Christy")
        monkeypatch.setattr(identity_service, "INSTANCE_PERSON_SLOT", 2)

        me = identity_service.ensure_identity()
        assert me["display_name"] == "Christy"
        assert me["person_slot"] == 2
        assert identity_repo.list_peers()[0]["display_name"] == "Valeria"

    def test_current_and_peer_user_ids(self, monkeypatch):
        import identity_service

        monkeypatch.setattr(identity_service, "PERSON_1_NAME", "Valeria")
        monkeypatch.setattr(identity_service, "PERSON_2_NAME", "Christy")
        monkeypatch.setattr(identity_service, "INSTANCE_PERSON_SLOT", 1)

        me = identity_service.ensure_identity()
        assert identity_service.current_user_id() == me["user_id"]
        assert identity_service.peer_user_id() == identity_repo.list_peers()[0]["user_id"]

    def test_current_user_id_returns_none_when_unset(self):
        import identity_service

        assert identity_service.current_user_id() is None


class TestIdentityRoutes:
    def test_get_identity_bootstraps_on_first_call(self, client):
        res = client.get("/api/identity")
        assert res.status_code == 200
        body = res.json()
        assert body["me"]["user_id"]
        assert body["me"]["person_slot"] in (1, 2)
        assert len(body["peers"]) == 1

    def test_put_identity_updates_display_name(self, client):
        client.get("/api/identity")
        res = client.put("/api/identity", json={"display_name": "Val"})
        assert res.status_code == 200
        assert res.json()["display_name"] == "Val"
        assert client.get("/api/identity").json()["me"]["display_name"] == "Val"

    def test_put_identity_rejects_blank_name(self, client):
        client.get("/api/identity")
        res = client.put("/api/identity", json={"display_name": "   "})
        assert res.status_code == 422
