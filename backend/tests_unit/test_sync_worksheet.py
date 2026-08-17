"""Unit tests for period↔worksheet resolution and creation."""
import pytest

from sheet_sync import worksheet as ws
from sheet_sync.gateway import InMemoryGateway

HEADER = ["Transaction Date", "Description", "Amount"]


def _gw(titles=("March 2026 - PIF", "April 2026", "May 2026", "June 2026")):
    return InMemoryGateway(
        {t: [HEADER[:], ["06/01/2026", "COSTCO", "112.25"]] for t in titles}
    )


class TestTitleMapping:
    def test_period_to_title(self):
        assert ws.period_to_title("2026-06") == "June 2026"
        assert ws.period_to_title("2026-12") == "December 2026"

    @pytest.mark.parametrize(
        "title,expected",
        [
            ("June 2026", "2026-06"),
            ("March 2026 - PIF", "2026-03"),
            ("December - 2023 - PIF", "2023-12"),
            ("  July 2026  ", "2026-07"),
            ("january 2025", "2025-01"),
        ],
    )
    def test_title_to_period_is_lenient(self, title, expected):
        assert ws.title_to_period(title) == expected

    @pytest.mark.parametrize("title", ["CodingTemple - PIF", "_sync", "", "Notes"])
    def test_non_month_titles_return_none(self, title):
        assert ws.title_to_period(title) is None

    def test_round_trip(self):
        assert ws.title_to_period(ws.period_to_title("2026-08")) == "2026-08"

    @pytest.mark.parametrize(
        "title,settled",
        [("March 2026 - PIF", True), ("June 2026", False), ("June 2026 - pif", True)],
    )
    def test_is_settled_title(self, title, settled):
        assert ws.is_settled_title(title) is settled


class TestFinding:
    def test_find_worksheet_matches_regardless_of_suffix(self):
        assert ws.find_worksheet(_gw(), "2026-03") == "March 2026 - PIF"

    def test_find_worksheet_returns_none_when_absent(self):
        assert ws.find_worksheet(_gw(), "2026-08") is None

    def test_latest_month_title_ignores_non_month_worksheets(self):
        gw = _gw(("April 2026", "June 2026", "CodingTemple - PIF", "_sync"))
        assert ws.latest_month_title(gw) == "June 2026"

    def test_latest_month_title_is_by_period_not_sheet_order(self):
        gw = _gw(("June 2026", "April 2026"))
        assert ws.latest_month_title(gw) == "June 2026"

    def test_latest_month_title_none_when_no_months(self):
        gw = InMemoryGateway({"_sync": [["key", "value"]]})
        assert ws.latest_month_title(gw) is None


class TestEnsure:
    def test_returns_existing_title_without_creating(self):
        gw = _gw()
        before = gw.list_worksheets()
        assert ws.ensure_worksheet(gw, "2026-06") == "June 2026"
        assert gw.list_worksheets() == before

    def test_creates_from_the_latest_month(self):
        gw = _gw()
        title = ws.ensure_worksheet(gw, "2026-07")
        assert title == "July 2026"
        assert "July 2026" in gw.list_worksheets()

    def test_created_worksheet_keeps_the_header_and_drops_the_data(self):
        gw = _gw()
        ws.ensure_worksheet(gw, "2026-07")
        assert gw.read_rows("July 2026") == [HEADER]

    def test_is_idempotent(self):
        gw = _gw()
        first = ws.ensure_worksheet(gw, "2026-07")
        second = ws.ensure_worksheet(gw, "2026-07")
        assert first == second
        assert gw.list_worksheets().count("July 2026") == 1

    def test_tolerates_a_concurrent_create(self, monkeypatch):
        """The user may run their Apps Script at the same moment."""
        gw = _gw()
        original = gw.duplicate_worksheet

        def racing_duplicate(source_title, new_title):
            gw.data[new_title] = [HEADER[:]]
            original(source_title, new_title)

        monkeypatch.setattr(gw, "duplicate_worksheet", racing_duplicate)
        assert ws.ensure_worksheet(gw, "2026-07") == "July 2026"

    def test_raises_when_there_is_no_template(self):
        gw = InMemoryGateway({"_sync": [["key", "value"]]})
        with pytest.raises(ws.NoTemplateWorksheet):
            ws.ensure_worksheet(gw, "2026-07")
