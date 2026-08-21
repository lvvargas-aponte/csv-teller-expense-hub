"""Outbound disputes: the one place this instance writes to a row it does not own."""
from sheet_sync import contract, engine
from sheet_sync.engine import DesiredDispute, SheetRow

ME = "11111111-1111-1111-1111-111111111111"
PEER = "22222222-2222-2222-2222-222222222222"
P1, P2 = "Valeria", "Christy"

HEADERS = [
    "Transaction Date", "Description", "Amount", "Who",
    f"What {P1} Owes", f"What {P2} Owes", "Notes", "Reviewed",
    "Dispute", "Dispute By", "Dispute Note", "Txn ID", "Owner", "Carried From",
]
INDEX = contract.header_index_map(HEADERS, P1, P2)


def row(n, txn_id, dispute="", by="", note=""):
    values = {k: "" for k in INDEX}
    values.update({"txn_id": txn_id, "dispute": dispute,
                   "dispute_by": by, "dispute_note": note})
    return SheetRow(row_number=n, values=values)


class TestOwnershipSafety:
    def test_never_writes_to_a_row_we_own(self):
        """The single-writer rule in the direction that corrupts the peer's data."""
        desired = [DesiredDispute(f"{ME}:t1", "Y", P1, "mine")]
        assert engine.plan_dispute_push(desired, [row(2, f"{ME}:t1")], INDEX, ME) == []

    def test_writes_only_disputer_columns(self):
        desired = [DesiredDispute(f"{PEER}:x1", "Y", P1, "not shared")]
        updates = engine.plan_dispute_push(desired, [row(2, f"{PEER}:x1")], INDEX, ME)

        allowed = {INDEX[k] + 1 for k in contract.DISPUTER_KEYS}
        assert updates and {u.col for u in updates} <= allowed

    def test_targets_the_right_row_number(self):
        current = [row(2, f"{PEER}:x1"), row(7, f"{PEER}:x2")]
        desired = [DesiredDispute(f"{PEER}:x2", "Y", P1, "this one")]

        assert {u.row for u in engine.plan_dispute_push(desired, current, INDEX, ME)} == {7}

    def test_a_mixed_batch_skips_only_the_owned_row(self):
        """A per-row 'if any row is owned, return []' bug would pass every
        other test here — every one of them passes a single-element batch."""
        current = [row(2, f"{ME}:mine"), row(3, f"{PEER}:theirs")]
        desired = [
            DesiredDispute(f"{ME}:mine", "Y", P1, "mine"),
            DesiredDispute(f"{PEER}:theirs", "Y", P1, "theirs"),
        ]

        updates = engine.plan_dispute_push(desired, current, INDEX, ME)

        assert updates and {u.row for u in updates} == {3}


class TestContent:
    def test_writes_flag_author_and_note(self):
        desired = [DesiredDispute(f"{PEER}:x1", "Y", P1, "should be 70/30")]
        by_col = {u.col: u.value
                  for u in engine.plan_dispute_push(desired, [row(2, f"{PEER}:x1")], INDEX, ME)}

        assert by_col[INDEX["dispute"] + 1] == "Y"
        assert by_col[INDEX["dispute_by"] + 1] == P1
        assert by_col[INDEX["dispute_note"] + 1] == "should be 70/30"

    def test_clearing_blanks_all_three_cells(self):
        current = [row(2, f"{PEER}:x1", dispute="Y", by=P1, note="was wrong")]
        desired = [DesiredDispute(f"{PEER}:x1", None, "", "")]

        updates = engine.plan_dispute_push(desired, current, INDEX, ME)

        assert len(updates) == 3
        assert all(u.value == "" for u in updates)

    def test_an_unchanged_dispute_writes_nothing(self):
        """Idempotency — a steady state must not rewrite cells every cycle."""
        current = [row(2, f"{PEER}:x1", dispute="Y", by=P1, note="same")]
        desired = [DesiredDispute(f"{PEER}:x1", "Y", P1, "same")]

        assert engine.plan_dispute_push(desired, current, INDEX, ME) == []

    def test_a_row_not_on_this_worksheet_is_skipped(self):
        desired = [DesiredDispute(f"{PEER}:absent", "Y", P1, "x")]
        assert engine.plan_dispute_push(desired, [row(2, f"{PEER}:x1")], INDEX, ME) == []


class TestPullClearing:
    def test_a_blank_disputer_cell_is_reported_so_it_can_clear(self):
        result = engine.plan_pull([row(2, f"{ME}:t1")], ME)
        assert f"{ME}:t1" in result.my_disputes

    def test_a_present_dispute_is_still_reported(self):
        result = engine.plan_pull([row(2, f"{ME}:t1", dispute="Y", by=P2, note="n")], ME)
        assert result.my_disputes[f"{ME}:t1"]["dispute"] == "Y"
