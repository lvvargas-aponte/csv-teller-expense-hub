"""Local transaction dicts ↔ sheet rows. Pure; the rules live here."""
from datetime import date
from decimal import Decimal

from sheet_sync import projection
from sheet_sync.engine import SheetRow

ME = "11111111-1111-1111-1111-111111111111"
PEER = "22222222-2222-2222-2222-222222222222"
P1, P2 = "Valeria", "Christy"


def txn(**over):
    base = {
        "date": "06/15/2026",
        "description": "Groceries",
        "amount": -112.25,
        "who": "Valeria",
        "notes": "",
        "is_shared": True,
        "reviewed": True,
        "person_1_owes": 56.13,
        "person_2_owes": 56.13,
    }
    base.update(over)
    return base


class TestPeriodOf:
    def test_uses_the_transaction_date(self):
        assert projection.period_of(txn()) == "2026-06"

    def test_iso_dates_parse_too(self):
        assert projection.period_of(txn(date="2026-07-02")) == "2026-07"

    def test_settles_in_period_wins(self):
        """A carried row settles in the open month, not the closed one it came from."""
        assert projection.period_of(txn(settles_in_period="2026-08")) == "2026-08"

    def test_unparseable_date_is_none(self):
        assert projection.period_of(txn(date="whenever")) is None


class TestPayerSlot:
    def test_matches_either_configured_name(self):
        assert projection.payer_slot("Valeria", P1, P2) == 1
        assert projection.payer_slot("Christy", P1, P2) == 2

    def test_is_insensitive_to_case_and_padding(self):
        assert projection.payer_slot("  christy ", P1, P2) == 2

    def test_an_unknown_name_is_none(self):
        assert projection.payer_slot("Mom", P1, P2) is None
        assert projection.payer_slot("", P1, P2) is None


class TestProjectPush:
    def _project(self, items, period="2026-06"):
        return projection.project_push(items, period, ME, P1, P2)

    def test_fills_only_the_non_payers_owes_cell(self):
        rows, bad = self._project([("t1", txn(who="Valeria"))])

        assert bad == []
        assert rows[0].owes_1 is None
        assert rows[0].owes_2 == Decimal("56.13")

    def test_the_other_payer_inverts_which_cell_is_filled(self):
        rows, _ = self._project([("t1", txn(who="Christy"))])

        assert rows[0].owes_1 == Decimal("56.13")
        assert rows[0].owes_2 is None

    def test_builds_the_full_desired_row(self):
        rows, _ = self._project([("t1", txn(notes="split 1/3"))])
        row = rows[0]

        assert row.txn_id == f"{ME}:t1"
        assert row.owner == ME
        assert row.date == date(2026, 6, 15)
        assert row.description == "Groceries"
        assert row.amount == Decimal("112.25")
        assert row.who == "Valeria"
        assert row.notes == "split 1/3"
        assert row.reviewed is True
        assert row.carried_from is None

    def test_negative_amounts_publish_as_positive(self):
        rows, _ = self._project([("t1", txn(amount=-8.57))])
        assert rows[0].amount == Decimal("8.57")

    def test_carried_from_is_carried_through(self):
        rows, _ = self._project(
            [("t1", txn(carried_from_period="2026-03", settles_in_period="2026-06"))]
        )
        assert rows[0].carried_from == "2026-03"

    def test_a_blank_or_zero_split_is_unpublishable(self):
        """person_N_owes defaults to 0.0 in the transactions router whenever a
        row is marked reviewed without an explicit split, so a zero here is not
        a user decision — it must not be published as a settled claim."""
        rows, bad = self._project([("t1", txn(who="Valeria", person_2_owes=0))])
        assert rows == []
        assert bad[0].transaction_id == "t1"
        assert "split" in bad[0].reason.lower()
        assert "Valeria" in bad[0].reason

    def test_a_missing_split_is_unpublishable(self):
        rows, bad = self._project([("t1", txn(who="Valeria", person_2_owes=None))])
        assert rows == []
        assert bad[0].transaction_id == "t1"

    def test_a_nonzero_split_still_publishes(self):
        rows, bad = self._project([("t1", txn(who="Valeria", person_2_owes=56.13))])
        assert bad == []
        assert rows[0].owes_2 == Decimal("56.13")

    def test_skips_unshared_and_unreviewed(self):
        rows, bad = self._project([
            ("t1", txn(is_shared=False)),
            ("t2", txn(reviewed=False)),
        ])
        assert rows == [] and bad == []

    def test_skips_other_periods(self):
        rows, bad = self._project([("t1", txn(date="07/04/2026"))])
        assert rows == [] and bad == []

    def test_an_unrecognised_payer_is_reported_not_guessed(self):
        rows, bad = self._project([("t1", txn(who="Mom"))])

        assert rows == []
        assert bad[0].transaction_id == "t1"
        assert "Mom" in bad[0].reason

    def test_a_blank_who_is_reported(self):
        rows, bad = self._project([("t1", txn(who=""))])
        assert rows == [] and bad[0].transaction_id == "t1"

    def test_an_unparseable_date_is_reported(self):
        rows, bad = self._project([("t1", txn(date="soon", settles_in_period="2026-06"))])
        assert rows == [] and "date" in bad[0].reason.lower()


class TestProjectPeerRow:
    SLOTS = {1: ME, 2: PEER}

    def _row(self, **over):
        values = {
            "txn_id": f"{PEER}:x1",
            "date": "6/15/2026",
            "description": "Cleaning",
            "amount": "$112.25",
            "who": "Christy",
            "owes_1": "$56.13",
            "owes_2": "",
            "notes": "monthly",
            "reviewed": "TRUE",
            "carried_from": "",
        }
        values.update(over)
        return SheetRow(row_number=4, values=values)

    def _project(self, row):
        return projection.project_peer_row(row, "2026-06", self.SLOTS, P1, P2)

    def test_maps_the_row_to_repo_parameters(self):
        out = self._project(self._row())

        assert out["txn_id"] == f"{PEER}:x1"
        assert out["owner_user_id"] == PEER
        assert out["date"] == "2026-06-15"
        assert out["description"] == "Cleaning"
        assert out["amount"] == Decimal("112.25")
        assert out["person_1_owes"] == Decimal("56.13")
        assert out["person_2_owes"] is None
        assert out["reviewed"] is True
        assert out["settles_in_period"] == "2026-06"
        assert out["carried_from_period"] is None

    def test_resolves_the_payer_to_a_user_id(self):
        assert self._project(self._row())["payer_user_id"] == PEER

    def test_an_unresolvable_payer_leaves_the_id_null(self):
        assert self._project(self._row(who="Mom"))["payer_user_id"] is None

    def test_an_undated_row_is_dropped(self):
        """The peer store requires a date; a row without one cannot be imported."""
        assert self._project(self._row(date="")) is None

    def test_an_unreadable_amount_is_dropped(self):
        assert self._project(self._row(amount="lots")) is None

    def test_a_malformed_txn_id_is_dropped(self):
        assert self._project(self._row(txn_id="nonsense")) is None

    def test_carried_from_is_preserved(self):
        assert self._project(self._row(carried_from="2026-03"))["carried_from_period"] == "2026-03"
