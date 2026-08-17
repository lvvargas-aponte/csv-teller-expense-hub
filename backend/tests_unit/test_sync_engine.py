"""Unit tests for the pure push/pull diff.

These rules decide who owes whom, so they are tested against plain dicts with
no database and no sheet.
"""
from datetime import date
from decimal import Decimal

from sheet_sync import contract, engine

ME = "11111111-1111-1111-1111-111111111111"
PEER = "22222222-2222-2222-2222-222222222222"

HEADERS = contract.build_headers("Valeria", "Christy")
INDEX = contract.header_index_map(HEADERS, "Valeria", "Christy")
COLS = len(HEADERS)


def _desired(local_id="t1", owner=ME, **over):
    kwargs = dict(
        txn_id=contract.make_txn_id(owner, local_id),
        owner=owner,
        date=date(2026, 6, 1),
        description="COSTCO",
        amount=Decimal("112.25"),
        who="Christy",
        owes_1=Decimal("56.13"),
        owes_2=None,
        notes="",
        reviewed=True,
        carried_from=None,
    )
    kwargs.update(over)
    return engine.DesiredRow(**kwargs)


def _sheet_row(row_number, desired, **over):
    values = {
        "date": contract.format_date(desired.date),
        "description": desired.description,
        "amount": contract.format_amount(desired.amount),
        "who": desired.who,
        "owes_1": contract.format_amount(desired.owes_1),
        "owes_2": contract.format_amount(desired.owes_2),
        "notes": desired.notes,
        "reviewed": contract.format_bool(desired.reviewed),
        "dispute": "",
        "dispute_by": "",
        "dispute_note": "",
        "txn_id": desired.txn_id,
        "owner": desired.owner,
        "carried_from": desired.carried_from or "",
    }
    values.update(over)
    return engine.SheetRow(row_number=row_number, values=values)


class TestReadSheet:
    def test_skips_the_header_and_untagged_rows(self):
        headers = contract.build_headers("Valeria", "Christy")
        blank = [""] * COLS
        tagged = [""] * COLS
        tagged[INDEX["txn_id"]] = contract.make_txn_id(ME, "t1")
        rows = engine.read_sheet([headers, blank, tagged], INDEX)
        assert len(rows) == 1
        assert rows[0].row_number == 3, "row numbers are 1-based sheet positions"

    def test_tolerates_short_rows(self):
        headers = contract.build_headers("Valeria", "Christy")
        short = ["06/01/2026", "COSTCO"]
        assert engine.read_sheet([headers, short], INDEX) == []


class TestPushAppends:
    def test_a_new_transaction_is_appended(self):
        plan = engine.plan_push([_desired()], [], INDEX, ME, HEADERS)
        assert len(plan.appends) == 1
        assert plan.updates == []
        row = plan.appends[0]
        assert row[INDEX["who"]] == "Christy"
        assert row[INDEX["owner"]] == ME

    def test_only_the_non_payer_cell_is_filled(self):
        """The payer's cell stays empty — this is the sheet's whole convention."""
        plan = engine.plan_push([_desired()], [], INDEX, ME, HEADERS)
        row = plan.appends[0]
        assert row[INDEX["owes_1"]] == "56.13"
        assert row[INDEX["owes_2"]] == ""

    def test_appended_row_is_full_width(self):
        plan = engine.plan_push([_desired()], [], INDEX, ME, HEADERS)
        assert len(plan.appends[0]) == COLS

    def test_dispute_columns_are_never_written_on_append(self):
        plan = engine.plan_push([_desired()], [], INDEX, ME, HEADERS)
        row = plan.appends[0]
        for key in contract.DISPUTER_KEYS:
            assert row[INDEX[key]] == ""


class TestPushUpdates:
    def test_an_unchanged_row_produces_no_writes(self):
        d = _desired()
        plan = engine.plan_push([d], [_sheet_row(2, d)], INDEX, ME, HEADERS)
        assert plan.updates == []
        assert plan.appends == []
        assert plan.delete_row_numbers == []

    def test_a_changed_split_updates_only_that_cell(self):
        d = _desired(owes_1=Decimal("78.57"))
        stale = _sheet_row(2, _desired())
        plan = engine.plan_push([d], [stale], INDEX, ME, HEADERS)
        assert len(plan.updates) == 1
        u = plan.updates[0]
        assert (u.row, u.col, u.value) == (2, INDEX["owes_1"] + 1, "78.57")

    def test_a_hand_edited_row_is_restored_and_reported(self):
        d = _desired()
        edited = _sheet_row(2, d, owes_1="70.00")
        plan = engine.plan_push([d], [edited], INDEX, ME, HEADERS)
        assert len(plan.updates) == 1
        assert plan.updates[0].value == "56.13"
        assert len(plan.corrections) == 1
        c = plan.corrections[0]
        assert c.column_name == "What Valeria Owes"
        assert c.sheet_value == "70.00"
        assert c.app_value == "56.13"

    def test_disputes_on_my_row_are_never_overwritten(self):
        d = _desired()
        disputed = _sheet_row(2, d, dispute="Y", dispute_by="Christy", dispute_note="no")
        plan = engine.plan_push([d], [disputed], INDEX, ME, HEADERS)
        assert plan.updates == []
        assert plan.corrections == []


class TestPushOwnership:
    def test_peer_rows_are_never_written(self):
        peer_row = _sheet_row(2, _desired(owner=PEER, local_id="p1"))
        plan = engine.plan_push([], [peer_row], INDEX, ME, HEADERS)
        assert plan.updates == []
        assert plan.delete_row_numbers == []

    def test_peer_rows_are_never_deleted_even_when_absent_locally(self):
        """Absent from MY desired set is meaningless for a row I do not own."""
        peer_row = _sheet_row(2, _desired(owner=PEER, local_id="p1"))
        plan = engine.plan_push([_desired()], [peer_row], INDEX, ME, HEADERS)
        assert plan.delete_row_numbers == []
        assert len(plan.appends) == 1


class TestPushDeletes:
    def test_unsharing_deletes_my_row(self):
        mine = _sheet_row(2, _desired())
        plan = engine.plan_push([], [mine], INDEX, ME, HEADERS)
        assert plan.delete_row_numbers == [2]

    def test_deletes_are_returned_high_to_low(self):
        """Applying low-to-high would renumber the rows still pending."""
        rows = [
            _sheet_row(2, _desired(local_id="a")),
            _sheet_row(3, _desired(local_id="b")),
            _sheet_row(4, _desired(local_id="c")),
        ]
        plan = engine.plan_push([], rows, INDEX, ME, HEADERS)
        assert plan.delete_row_numbers == [4, 3, 2]


class TestCarriedFrom:
    def test_carried_from_is_written(self):
        plan = engine.plan_push(
            [_desired(carried_from="2026-06")], [], INDEX, ME, HEADERS
        )
        assert plan.appends[0][INDEX["carried_from"]] == "2026-06"


class TestPull:
    def test_peer_rows_are_returned(self):
        peer_row = _sheet_row(2, _desired(owner=PEER, local_id="p1"))
        mine = _sheet_row(3, _desired())
        result = engine.plan_pull([peer_row, mine], ME)
        assert len(result.peer_rows) == 1
        assert result.peer_rows[0].values["owner"] == PEER

    def test_disputes_raised_against_me_are_returned(self):
        mine = _sheet_row(
            2, _desired(), dispute="Y", dispute_by="Christy", dispute_note="wrong split"
        )
        result = engine.plan_pull([mine], ME)
        d = result.my_disputes[mine.values["txn_id"]]
        assert d == {
            "dispute": "Y",
            "dispute_by": "Christy",
            "dispute_note": "wrong split",
        }

    def test_my_undisputed_rows_are_not_reported(self):
        result = engine.plan_pull([_sheet_row(2, _desired())], ME)
        assert result.my_disputes == {}

    def test_a_row_is_never_both_peer_and_mine(self):
        rows = [
            _sheet_row(2, _desired()),
            _sheet_row(3, _desired(owner=PEER, local_id="p1")),
        ]
        result = engine.plan_pull(rows, ME)
        peer_ids = {r.values["txn_id"] for r in result.peer_rows}
        assert peer_ids.isdisjoint(result.my_disputes)
