"""The seam between the sync engine and Google Sheets.

Everything above this module talks to ``SheetGateway``. ``InMemoryGateway`` is
what lets a test run two instance identities against one spreadsheet with no
network; ``GspreadGateway`` is the only place gspread is imported.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Protocol

import gspread


class WorksheetNotFound(Exception):
    """No worksheet with that title exists in the spreadsheet."""


@dataclass(frozen=True)
class CellUpdate:
    """A single cell write. ``row`` and ``col`` are 1-based, as Sheets counts."""

    row: int
    col: int
    value: str


class SheetGateway(Protocol):
    def list_worksheets(self) -> list[str]: ...
    def read_rows(self, title: str) -> list[list[str]]: ...
    def write_cells(self, title: str, updates: list[CellUpdate]) -> None: ...
    def append_rows(self, title: str, rows: list[list[str]]) -> None: ...
    def delete_rows(self, title: str, row_numbers: list[int]) -> None: ...
    def duplicate_worksheet(self, source_title: str, new_title: str) -> None: ...
    def clear_rows_from(self, title: str, start_row: int) -> None: ...
    def set_hidden(self, title: str, hidden: bool) -> None: ...


class InMemoryGateway:
    """A spreadsheet in a dict. Used by every test; never used in production."""

    def __init__(self, data: dict[str, list[list[str]]] | None = None) -> None:
        self.data: dict[str, list[list[str]]] = copy.deepcopy(data or {})
        self.hidden: set[str] = set()
        self.calls: list[str] = []

    def _sheet(self, title: str) -> list[list[str]]:
        if title not in self.data:
            raise WorksheetNotFound(title)
        return self.data[title]

    def list_worksheets(self) -> list[str]:
        self.calls.append("list_worksheets")
        return list(self.data.keys())

    def read_rows(self, title: str) -> list[list[str]]:
        self.calls.append("read_rows")
        return copy.deepcopy(self._sheet(title))

    def write_cells(self, title: str, updates: list[CellUpdate]) -> None:
        self.calls.append("write_cells")
        rows = self._sheet(title)
        for u in updates:
            while len(rows) < u.row:
                rows.append([])
            row = rows[u.row - 1]
            while len(row) < u.col:
                row.append("")
            row[u.col - 1] = u.value

    def append_rows(self, title: str, rows: list[list[str]]) -> None:
        self.calls.append("append_rows")
        self._sheet(title).extend(copy.deepcopy(rows))

    def delete_rows(self, title: str, row_numbers: list[int]) -> None:
        self.calls.append("delete_rows")
        rows = self._sheet(title)
        # Descending, so each deletion cannot renumber the ones still pending.
        for n in sorted(set(row_numbers), reverse=True):
            if 1 <= n <= len(rows):
                del rows[n - 1]

    def duplicate_worksheet(self, source_title: str, new_title: str) -> None:
        self.calls.append("duplicate_worksheet")
        if new_title in self.data:
            raise ValueError(f"Worksheet {new_title!r} already exists")
        self.data[new_title] = copy.deepcopy(self._sheet(source_title))

    def clear_rows_from(self, title: str, start_row: int) -> None:
        self.calls.append("clear_rows_from")
        rows = self._sheet(title)
        del rows[start_row - 1:]

    def set_hidden(self, title: str, hidden: bool) -> None:
        self.calls.append("set_hidden")
        self._sheet(title)
        self.hidden.add(title) if hidden else self.hidden.discard(title)


class GspreadGateway:
    """The production gateway. The only module that imports gspread directly."""

    def __init__(self, spreadsheet: gspread.Spreadsheet) -> None:
        self._ss = spreadsheet

    def _ws(self, title: str):
        try:
            return self._ss.worksheet(title)
        except gspread.WorksheetNotFound as e:
            raise WorksheetNotFound(title) from e

    def list_worksheets(self) -> list[str]:
        return [w.title for w in self._ss.worksheets()]

    def read_rows(self, title: str) -> list[list[str]]:
        return self._ws(title).get_all_values()

    def write_cells(self, title: str, updates: list[CellUpdate]) -> None:
        if not updates:
            return
        ws = self._ws(title)
        cells = [gspread.Cell(u.row, u.col, u.value) for u in updates]
        ws.update_cells(cells, value_input_option="USER_ENTERED")

    def append_rows(self, title: str, rows: list[list[str]]) -> None:
        if not rows:
            return
        self._ws(title).append_rows(rows, value_input_option="USER_ENTERED")

    def delete_rows(self, title: str, row_numbers: list[int]) -> None:
        ws = self._ws(title)
        for n in sorted(set(row_numbers), reverse=True):
            ws.delete_rows(n)

    def duplicate_worksheet(self, source_title: str, new_title: str) -> None:
        source = self._ws(source_title)
        self._ss.duplicate_sheet(
            source_sheet_id=source.id, new_sheet_name=new_title
        )

    def clear_rows_from(self, title: str, start_row: int) -> None:
        ws = self._ws(title)
        if ws.row_count >= start_row:
            ws.delete_rows(start_row, ws.row_count)

    def set_hidden(self, title: str, hidden: bool) -> None:
        ws = self._ws(title)
        self._ss.batch_update(
            {
                "requests": [
                    {
                        "updateSheetProperties": {
                            "properties": {"sheetId": ws.id, "hidden": hidden},
                            "fields": "hidden",
                        }
                    }
                ]
            }
        )
