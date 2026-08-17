"""Unit tests for the in-memory gateway — the fake every other test relies on.

If this fake is wrong, every test built on it is wrong in the same direction,
so its semantics are pinned here explicitly.
"""
import pytest

from sheet_sync.gateway import (
    CellUpdate,
    InMemoryGateway,
    WorksheetExists,
    WorksheetNotFound,
)


def _gw():
    return InMemoryGateway(
        {
            "June 2026": [
                ["Transaction Date", "Description", "Amount"],
                ["06/01/2026", "COSTCO", "112.25"],
                ["06/02/2026", "WAWA", "12.07"],
            ],
            "_sync": [["key", "value"]],
        }
    )


class TestReads:
    def test_list_worksheets(self):
        assert _gw().list_worksheets() == ["June 2026", "_sync"]

    def test_read_rows(self):
        rows = _gw().read_rows("June 2026")
        assert len(rows) == 3
        assert rows[1][1] == "COSTCO"

    def test_read_missing_worksheet_raises(self):
        with pytest.raises(WorksheetNotFound):
            _gw().read_rows("Nope 2026")

    def test_read_returns_a_copy(self):
        """Mutating the result must not corrupt the fake's state."""
        gw = _gw()
        rows = gw.read_rows("June 2026")
        rows[1][1] = "TAMPERED"
        assert gw.read_rows("June 2026")[1][1] == "COSTCO"


class TestWrites:
    def test_write_cells_is_one_based(self):
        gw = _gw()
        gw.write_cells("June 2026", [CellUpdate(row=2, col=2, value="COSTCO WHSE")])
        assert gw.read_rows("June 2026")[1][1] == "COSTCO WHSE"

    def test_write_cells_extends_short_rows(self):
        gw = _gw()
        gw.write_cells("June 2026", [CellUpdate(row=2, col=6, value="x")])
        assert gw.read_rows("June 2026")[1][5] == "x"

    def test_append_rows(self):
        gw = _gw()
        gw.append_rows("June 2026", [["06/03/2026", "TARGET", "40.00"]])
        assert len(gw.read_rows("June 2026")) == 4

    def test_delete_rows_shifts_the_rest_up(self):
        gw = _gw()
        gw.delete_rows("June 2026", [2])
        rows = gw.read_rows("June 2026")
        assert len(rows) == 2
        assert rows[1][1] == "WAWA", "the row below must move up into its place"

    def test_delete_multiple_rows_uses_original_numbering(self):
        """Deleting 2 and 3 must remove COSTCO and WAWA, not COSTCO then nothing."""
        gw = _gw()
        gw.delete_rows("June 2026", [2, 3])
        assert len(gw.read_rows("June 2026")) == 1

    def test_delete_rows_out_of_range_raises(self):
        """A stale row number is a real defect and must fail loudly, like the
        real API does, rather than being silently skipped."""
        gw = _gw()
        with pytest.raises(IndexError):
            gw.delete_rows("June 2026", [99])

    def test_write_cells_empty_against_missing_worksheet_raises(self):
        gw = _gw()
        with pytest.raises(WorksheetNotFound):
            gw.write_cells("Nope 2026", [])

    def test_append_rows_empty_against_missing_worksheet_raises(self):
        gw = _gw()
        with pytest.raises(WorksheetNotFound):
            gw.append_rows("Nope 2026", [])


class TestWorksheetLifecycle:
    def test_duplicate_copies_content(self):
        gw = _gw()
        gw.duplicate_worksheet("June 2026", "July 2026")
        assert "July 2026" in gw.list_worksheets()
        assert gw.read_rows("July 2026") == gw.read_rows("June 2026")

    def test_duplicate_is_independent_of_its_source(self):
        gw = _gw()
        gw.duplicate_worksheet("June 2026", "July 2026")
        gw.write_cells("July 2026", [CellUpdate(row=2, col=2, value="CHANGED")])
        assert gw.read_rows("June 2026")[1][1] == "COSTCO"

    def test_duplicate_onto_existing_title_raises(self):
        gw = _gw()
        with pytest.raises(ValueError):
            gw.duplicate_worksheet("June 2026", "_sync")

    def test_duplicate_onto_existing_title_raises_worksheet_exists(self):
        gw = _gw()
        with pytest.raises(WorksheetExists):
            gw.duplicate_worksheet("June 2026", "_sync")

    def test_clear_rows_from_keeps_the_header(self):
        gw = _gw()
        gw.clear_rows_from("June 2026", 2)
        assert gw.read_rows("June 2026") == [
            ["Transaction Date", "Description", "Amount"]
        ]

    def test_set_hidden(self):
        gw = _gw()
        gw.set_hidden("_sync", True)
        assert "_sync" in gw.hidden


class TestCallRecording:
    def test_calls_are_recorded_for_quota_assertions(self):
        gw = _gw()
        gw.read_rows("June 2026")
        gw.write_cells("June 2026", [CellUpdate(row=2, col=1, value="x")])
        assert gw.calls == ["read_rows", "write_cells"]
