"""Adopting a peer's real user_id over the locally-invented placeholder."""
import pytest

from db import identity_repo

PLACEHOLDER = "99999999-9999-9999-9999-999999999999"
REAL = "22222222-2222-2222-2222-222222222222"


class TestAdoptPeerIdentity:
    def test_replaces_placeholder_at_the_same_slot(self):
        identity_repo.upsert_peer(PLACEHOLDER, "Christy", 2)

        adopted = identity_repo.adopt_peer_identity(2, REAL, "Christy")

        assert adopted["user_id"] == REAL
        peers = identity_repo.list_peers()
        assert len(peers) == 1, "the placeholder must not survive as a second row"
        assert peers[0]["user_id"] == REAL
        assert peers[0]["person_slot"] == 2

    def test_is_idempotent(self):
        identity_repo.upsert_peer(PLACEHOLDER, "Christy", 2)
        identity_repo.adopt_peer_identity(2, REAL, "Christy")
        identity_repo.adopt_peer_identity(2, REAL, "Christy")

        peers = identity_repo.list_peers()
        assert len(peers) == 1
        assert peers[0]["user_id"] == REAL

    def test_works_when_no_placeholder_exists(self):
        adopted = identity_repo.adopt_peer_identity(2, REAL, "Christy")

        assert adopted["user_id"] == REAL
        assert len(identity_repo.list_peers()) == 1

    def test_updates_the_display_name(self):
        identity_repo.upsert_peer(PLACEHOLDER, "Christy", 2)
        adopted = identity_repo.adopt_peer_identity(2, REAL, "Christina")
        assert adopted["display_name"] == "Christina"

    def test_leaves_the_other_slot_alone(self):
        identity_repo.upsert_peer(PLACEHOLDER, "Christy", 2)
        identity_repo.upsert_peer("33333333-3333-3333-3333-333333333333", "Someone", 1)

        identity_repo.adopt_peer_identity(2, REAL, "Christy")

        slots = {p["person_slot"]: p["user_id"] for p in identity_repo.list_peers()}
        assert slots[1] == "33333333-3333-3333-3333-333333333333"
        assert slots[2] == REAL


class TestSlotUniqueness:
    def test_two_peers_cannot_share_a_slot(self):
        identity_repo.upsert_peer(PLACEHOLDER, "Christy", 2)
        with pytest.raises(Exception) as exc:
            identity_repo.upsert_peer(REAL, "Christy", 2)
        assert "peers_person_slot_key" in str(exc.value)
