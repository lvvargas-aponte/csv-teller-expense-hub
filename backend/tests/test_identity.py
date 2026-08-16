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
