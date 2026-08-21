"""The push/pull diff. Pure — no I/O, no database, no network.

Two rules carry the whole design: an instance writes only rows it owns, and
within a row it writes only the columns it owns. The disputer columns (I–K —
``contract.DISPUTER_KEYS``) are the single exception, and it is a mirror image
of the rule rather than a hole in it: those three columns are written only on
rows this instance does NOT own (``plan_dispute_push``), never on rows it does
own (``plan_push`` never touches them). Everything else here is bookkeeping
around those two rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from sheet_sync import contract
from sheet_sync.gateway import CellUpdate


@dataclass(frozen=True)
class DesiredRow:
    txn_id: str
    owner: str
    date: date
    description: str
    amount: Decimal
    who: str
    owes_1: Optional[Decimal]
    owes_2: Optional[Decimal]
    notes: str
    reviewed: bool
    carried_from: Optional[str]


@dataclass(frozen=True)
class SheetRow:
    row_number: int
    values: dict[str, str]


@dataclass(frozen=True)
class DesiredDispute:
    txn_id: str
    flag: Optional[str]
    by: str
    note: str


@dataclass(frozen=True)
class Correction:
    txn_id: str
    column_name: str
    sheet_value: str
    app_value: str


@dataclass(frozen=True)
class PushPlan:
    updates: list[CellUpdate] = field(default_factory=list)
    appends: list[list[str]] = field(default_factory=list)
    delete_row_numbers: list[int] = field(default_factory=list)
    corrections: list[Correction] = field(default_factory=list)
    skipped_foreign: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PullResult:
    peer_rows: list[SheetRow] = field(default_factory=list)
    my_disputes: dict[str, dict[str, str]] = field(default_factory=dict)


def read_sheet(rows: list[list[str]], index: dict[str, int]) -> list[SheetRow]:
    """Parse data rows into ``SheetRow``s, keeping 1-based sheet row numbers.

    Rows without a Txn ID are outside the contract — a hand-entered line, a
    totals footer — and are left strictly alone.
    """
    parsed: list[SheetRow] = []
    for offset, raw in enumerate(rows[1:], start=2):
        values = {
            key: (raw[i] if i < len(raw) else "").strip()
            for key, i in index.items()
        }
        if values.get("txn_id"):
            parsed.append(SheetRow(row_number=offset, values=values))
    return parsed


def _desired_cells(row: DesiredRow) -> dict[str, str]:
    return {
        "date": contract.format_date(row.date),
        "description": row.description,
        "amount": contract.format_amount(row.amount),
        "who": row.who,
        "owes_1": contract.format_amount(row.owes_1),
        "owes_2": contract.format_amount(row.owes_2),
        "notes": row.notes,
        "reviewed": contract.format_bool(row.reviewed),
        "txn_id": row.txn_id,
        "owner": row.owner,
        "carried_from": row.carried_from or "",
    }


_AMOUNT_KEYS = frozenset({"amount", "owes_1", "owes_2"})


def cells_agree(key: str, on_sheet: str, app_value: str) -> bool:
    """Compare a sheet cell to the value we would write, semantically.

    Sheets re-renders what we send: ``112.25`` comes back ``$112.25`` and
    ``06/01/2026`` comes back ``6/1/2026``. A byte comparison would therefore
    see every owned row as changed on every cycle and rewrite it forever.
    """
    try:
        if key in _AMOUNT_KEYS:
            return contract.parse_amount(on_sheet) == contract.parse_amount(app_value)
        if key == "date":
            return contract.parse_date(on_sheet) == contract.parse_date(app_value)
        if key == "reviewed":
            return contract.parse_bool(on_sheet) == contract.parse_bool(app_value)
    except contract.ContractError:
        # A cell we cannot read is garbage; overwriting it is the right answer.
        return False
    return on_sheet.strip() == app_value.strip()


def _row_owner(row: SheetRow) -> Optional[str]:
    """Ownership comes from the Txn ID, not the human-editable Owner cell."""
    try:
        return contract.split_txn_id(row.values.get("txn_id", ""))[0]
    except contract.ContractError:
        return None


def plan_push(
    desired: list[DesiredRow],
    current: list[SheetRow],
    index: dict[str, int],
    me: str,
    headers: list[str],
) -> PushPlan:
    column_count = len(headers)
    by_id = {r.values["txn_id"]: r for r in current if _row_owner(r) == me}
    skipped_foreign = [d.txn_id for d in desired if d.owner != me]
    desired_by_id = {d.txn_id: d for d in desired if d.owner == me}

    updates: list[CellUpdate] = []
    appends: list[list[str]] = []
    corrections: list[Correction] = []

    for txn_id, want in desired_by_id.items():
        cells = _desired_cells(want)
        existing = by_id.get(txn_id)
        if existing is None:
            row = [""] * column_count
            for key, value in cells.items():
                row[index[key]] = value
            appends.append(row)
            continue
        for key, value in cells.items():
            on_sheet = existing.values.get(key, "")
            if not cells_agree(key, on_sheet, value):
                updates.append(
                    CellUpdate(
                        row=existing.row_number, col=index[key] + 1, value=value
                    )
                )
                corrections.append(
                    Correction(
                        txn_id=txn_id,
                        column_name=headers[index[key]],
                        sheet_value=on_sheet,
                        app_value=value,
                    )
                )

    deletes = sorted(
        (r.row_number for tid, r in by_id.items() if tid not in desired_by_id),
        reverse=True,
    )

    return PushPlan(
        updates=updates,
        appends=appends,
        delete_row_numbers=deletes,
        corrections=corrections,
        skipped_foreign=skipped_foreign,
    )


def plan_pull(current: list[SheetRow], me: str) -> PullResult:
    peer_rows: list[SheetRow] = []
    my_disputes: dict[str, dict[str, str]] = {}

    for row in current:
        owner = _row_owner(row)
        if owner is None:
            continue
        if owner == me:
            my_disputes[row.values["txn_id"]] = {
                k: row.values.get(k, "") for k in contract.DISPUTER_KEYS
            }
        else:
            peer_rows.append(row)

    return PullResult(peer_rows=peer_rows, my_disputes=my_disputes)


def plan_dispute_push(
    desired: list[DesiredDispute],
    current: list[SheetRow],
    index: dict[str, int],
    me: str,
) -> list[CellUpdate]:
    """Write columns I–K on rows we do NOT own — the disputer's half of a row.

    The mirror image of ``plan_push``: here ownership is the reason to skip a
    row, not the reason to write it. A ``DesiredDispute`` naming a row ``me``
    owns is silently dropped — writing I–K there would corrupt the owner's data.
    """
    by_id = {r.values["txn_id"]: r for r in current}
    updates: list[CellUpdate] = []

    for want in desired:
        row = by_id.get(want.txn_id)
        if row is None:
            continue
        owner = _row_owner(row)
        if owner is None or owner == me:
            continue
        if want.flag is None:
            cells = {"dispute": "", "dispute_by": "", "dispute_note": ""}
        else:
            cells = {
                "dispute": want.flag,
                "dispute_by": want.by,
                "dispute_note": want.note,
            }
        for key in contract.DISPUTER_KEYS:
            value = cells[key]
            on_sheet = row.values.get(key, "")
            if on_sheet.strip() == value.strip():
                continue
            updates.append(
                CellUpdate(row=row.row_number, col=index[key] + 1, value=value)
            )

    return updates
