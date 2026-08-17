"""Each guard refuses the whole sync. A half-synced month is worse than none."""
import pytest

from sheet_sync import guards
from sheet_sync.engine import SheetRow


def claim(**over):
    base = dict(
        user_id="11111111-1111-1111-1111-111111111111",
        display_name="Valeria",
        person_slot=1,
        contract_version="1.0",
        person_1_name="Valeria",
        person_2_name="Christy",
    )
    base.update(over)
    return guards.Claim(**base)


PEER_ID = "22222222-2222-2222-2222-222222222222"


class TestContractVersion:
    def test_matching_versions_pass(self):
        assert guards.check_contract_version(claim(), [claim(user_id=PEER_ID)]) is None

    def test_no_peer_claim_passes(self):
        assert guards.check_contract_version(claim(), []) is None

    def test_mismatch_names_both_versions_and_who_updates(self):
        peer = claim(user_id=PEER_ID, display_name="Christy", contract_version="1.1")
        refusal = guards.check_contract_version(claim(), [peer])

        assert refusal.reason == "contract_version"
        assert "1.0" in refusal.message and "1.1" in refusal.message
        assert "Christy" in refusal.message
        assert "update" in refusal.message.lower()

    def test_blank_peer_version_is_a_mismatch(self):
        peer = claim(user_id=PEER_ID, display_name="Christy", contract_version="")
        assert guards.check_contract_version(claim(), [peer]).reason == "contract_version"


class TestPersonNames:
    def test_identical_names_pass(self):
        assert guards.check_person_names(claim(), [claim(user_id=PEER_ID)]) is None

    def test_mismatch_shows_both_values(self):
        peer = claim(user_id=PEER_ID, display_name="Christy", person_2_name="Christina")
        refusal = guards.check_person_names(claim(), [peer])

        assert refusal.reason == "person_names"
        assert "Christy" in refusal.message and "Christina" in refusal.message

    def test_person_1_mismatch_is_caught_too(self):
        peer = claim(user_id=PEER_ID, display_name="Christy", person_1_name="Val")
        assert guards.check_person_names(claim(), [peer]).reason == "person_names"


class TestSlotCollision:
    def test_different_slots_pass(self):
        peer = claim(user_id=PEER_ID, display_name="Christy", person_slot=2)
        assert guards.check_slot_collision(claim(), [peer]) is None

    def test_same_slot_different_user_refuses_and_names_both(self):
        peer = claim(user_id=PEER_ID, display_name="Christy", person_slot=1)
        refusal = guards.check_slot_collision(claim(), [peer])

        assert refusal.reason == "slot_collision"
        assert "Valeria" in refusal.message and "Christy" in refusal.message
        assert "1" in refusal.message

    def test_our_own_claim_echoed_back_is_not_a_collision(self):
        assert guards.check_slot_collision(claim(), [claim()]) is None


class TestCheckClaims:
    def test_returns_the_first_failure_in_declared_order(self):
        peer = claim(
            user_id=PEER_ID,
            display_name="Christy",
            person_slot=1,
            contract_version="2.0",
            person_2_name="Christina",
        )
        assert guards.check_claims(claim(), [peer]).reason == "contract_version"

    def test_all_clear_returns_none(self):
        peer = claim(user_id=PEER_ID, display_name="Christy", person_slot=2)
        assert guards.check_claims(claim(), [peer]) is None


class TestDuplicateTxnIds:
    def _row(self, n, txn_id):
        return SheetRow(row_number=n, values={"txn_id": txn_id, "description": "x"})

    def test_unique_ids_pass(self):
        rows = [self._row(2, "u1:a"), self._row(3, "u1:b")]
        assert guards.check_duplicate_txn_ids("June 2026", rows) is None

    def test_duplicate_refuses_and_names_the_id_and_rows(self):
        rows = [self._row(2, "u1:a"), self._row(5, "u1:a")]
        refusal = guards.check_duplicate_txn_ids("June 2026", rows)

        assert refusal.reason == "duplicate_txn_id"
        assert "u1:a" in refusal.message
        assert "June 2026" in refusal.message
        assert "2" in refusal.message and "5" in refusal.message

    def test_reports_every_duplicated_id(self):
        rows = [
            self._row(2, "u1:a"), self._row(3, "u1:a"),
            self._row(4, "u2:b"), self._row(6, "u2:b"),
        ]
        message = guards.check_duplicate_txn_ids("June 2026", rows).message
        assert "u1:a" in message and "u2:b" in message

    def test_empty_worksheet_passes(self):
        assert guards.check_duplicate_txn_ids("June 2026", []) is None
