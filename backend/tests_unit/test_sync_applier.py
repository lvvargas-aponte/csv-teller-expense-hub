"""Unit tests for the push applier.

A ``PushPlan``'s row numbers all come from one pre-write read, so the order the
three lists are applied in decides whether a correction lands on the right
financial row. That order is pinned here.
"""
import pytest

from sheet_sync.applier import apply_push
from sheet_sync.engine import PushPlan
from sheet_sync.gateway import CellUpdate, InMemoryGateway


def _gw():
    return InMemoryGateway(
        {
            "June 2026": [
                ["Transaction Date", "Description", "Amount"],
                ["06/01/2026", "COSTCO", "112.25"],
                ["06/02/2026", "WAWA", "12.07"],
                ["06/03/2026", "TARGET", "40.00"],
            ]
        }
    )


def test_updates_land_before_deletes_renumber_the_sheet():
    """Deleting row 2 first would drag TARGET up to row 3 and mis-write WAWA."""
    gw = _gw()
    plan = PushPlan(
        updates=[CellUpdate(row=4, col=3, value="99.99")],
        delete_row_numbers=[2],
    )
    apply_push(gw, "June 2026", plan)
    rows = gw.read_rows("June 2026")
    assert rows[2] == ["06/03/2026", "TARGET", "99.99"]
    assert rows[1] == ["06/02/2026", "WAWA", "12.07"]


def test_appends_land_at_the_bottom_before_deletes():
    gw = _gw()
    plan = PushPlan(
        appends=[["06/04/2026", "ALDI", "22.00"]],
        delete_row_numbers=[2],
    )
    apply_push(gw, "June 2026", plan)
    rows = gw.read_rows("June 2026")
    assert rows[-1] == ["06/04/2026", "ALDI", "22.00"]
    assert len(rows) == 4
    assert rows[1] == ["06/02/2026", "WAWA", "12.07"], "COSTCO was the delete"


def test_an_empty_plan_touches_nothing():
    gw = _gw()
    before = gw.read_rows("June 2026")
    gw.calls.clear()
    apply_push(gw, "June 2026", PushPlan())
    assert gw.calls == []
    assert gw.read_rows("June 2026") == before


def test_a_stale_delete_row_number_still_fails_loudly():
    gw = _gw()
    with pytest.raises(IndexError):
        apply_push(gw, "June 2026", PushPlan(delete_row_numbers=[99]))
