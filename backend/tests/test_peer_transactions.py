"""Integration tests for the peer's imported shared transactions."""
from db import peer_transactions_repo as repo

OWNER = "22222222-2222-2222-2222-222222222222"


def _row(txn_id: str, date: str = "2026-03-15", amount: float = -40.00, **over):
    row = {
        "txn_id": f"{OWNER}:{txn_id}",
        "owner_user_id": OWNER,
        "date": date,
        "description": "GROCERIES",
        "amount": amount,
        "who": "Christy",
        "person_1_owes": 20.00,
        "person_2_owes": 20.00,
        "notes": "",
        "reviewed": True,
        "payer_user_id": OWNER,
        "carried_from_period": None,
        "settles_in_period": None,
        "dispute_flag": None,
        "dispute_by": None,
        "dispute_note": None,
    }
    row.update(over)
    return row


class TestUpsert:
    def test_upsert_many_inserts(self):
        assert repo.upsert_many([_row("a"), _row("b")]) == 2
        assert len(repo.list_for_period("2026-03")) == 2

    def test_upsert_many_is_idempotent(self):
        repo.upsert_many([_row("a")])
        repo.upsert_many([_row("a")])
        assert len(repo.list_for_period("2026-03")) == 1

    def test_upsert_updates_changed_fields(self):
        repo.upsert_many([_row("a", person_1_owes=20.00)])
        repo.upsert_many([_row("a", person_1_owes=30.00)])
        stored = repo.get(f"{OWNER}:a")
        assert float(stored["person_1_owes"]) == 30.00

    def test_upsert_many_with_empty_list_is_a_noop(self):
        assert repo.upsert_many([]) == 0

    def test_get_missing_returns_none(self):
        assert repo.get("nope") is None


class TestPeriodFiltering:
    def test_list_for_period_filters_by_month(self):
        repo.upsert_many([_row("a", date="2026-03-15"), _row("b", date="2026-04-02")])
        assert len(repo.list_for_period("2026-03")) == 1
        assert len(repo.list_for_period("2026-04")) == 1

    def test_carried_row_settles_in_april_not_closed_march(self):
        """A March transaction that arrives after March closed settles in April.

        This is the whole point of carry-forward: closed months never change.
        """
        repo.upsert_many([
            _row(
                "late",
                date="2026-03-28",
                carried_from_period="2026-03",
                settles_in_period="2026-04",
            )
        ])

        assert repo.list_for_period("2026-03") == []

        april = repo.list_for_period("2026-04")
        assert len(april) == 1
        assert april[0]["carried_from_period"] == "2026-03"

    def test_uncarried_row_settles_in_its_own_month(self):
        repo.upsert_many([_row("normal", date="2026-03-15")])
        assert len(repo.list_for_period("2026-03")) == 1
        assert repo.list_for_period("2026-04") == []

    def test_empty_period_returns_empty_list(self):
        assert repo.list_for_period("2030-01") == []


class TestDisputes:
    def test_set_dispute_marks_the_row(self):
        repo.upsert_many([_row("a")])
        assert repo.set_dispute(f"{OWNER}:a", "Y", "Valeria", "Split should be 70/30") is True
        stored = repo.get(f"{OWNER}:a")
        assert stored["dispute_flag"] == "Y"
        assert stored["dispute_by"] == "Valeria"
        assert stored["dispute_note"] == "Split should be 70/30"

    def test_set_dispute_can_resolve(self):
        repo.upsert_many([_row("a")])
        repo.set_dispute(f"{OWNER}:a", "Y", "Valeria", "wrong")
        repo.set_dispute(f"{OWNER}:a", "N", "Valeria", "wrong")
        assert repo.get(f"{OWNER}:a")["dispute_flag"] == "N"

    def test_set_dispute_on_missing_row_returns_false(self):
        assert repo.set_dispute("nope", "Y", "Valeria", "x") is False

    def test_upsert_preserves_our_dispute(self):
        """Re-importing the peer's row must not wipe the dispute we raised."""
        repo.upsert_many([_row("a")])
        repo.set_dispute(f"{OWNER}:a", "Y", "Valeria", "wrong split")
        repo.upsert_many([_row("a", person_1_owes=25.00)])
        stored = repo.get(f"{OWNER}:a")
        assert float(stored["person_1_owes"]) == 25.00
        assert stored["dispute_flag"] == "Y"
        assert stored["dispute_note"] == "wrong split"
