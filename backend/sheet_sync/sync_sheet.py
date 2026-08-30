"""The hidden ``_sync`` worksheet — the instances' handshake.

One table with a ``Record`` discriminator. ``claim`` rows are one per instance
and carry everything that is not per-transaction: who I am, which person slot I
occupy, and which contract version I speak. ``period`` rows are one per
instance per month and carry that instance's settlement position: whether its
rows are complete, the net it computed, and whether it considers the month
paid. Settlement is advisory — each side states its own position and either
may declare a month paid — so these rows are never merged into one.

Hidden because it is machine state living inside a spreadsheet a human reads by
hand. Unhiding it in the Sheets UI still shows everything.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from sheet_sync.contract import escape_formula, format_amount
from sheet_sync.gateway import (
    CellUpdate,
    SheetGateway,
    WorksheetExists,
    WorksheetNotFound,
)
from sheet_sync.guards import Claim

logger = logging.getLogger(__name__)

SYNC_TITLE = "_sync"

SYNC_HEADERS = [
    "Record",
    "Period",
    "User ID",
    "Display Name",
    "Person Slot",
    "Contract Version",
    "Person 1 Name",
    "Person 2 Name",
    # Only ``period`` rows fill these; a claim leaves them blank.
    "Ready At",
    "Closed At",
    "Net Amount",
    "Debtor User ID",
    "PIF At",
    "PIF Note",
]

_RECORD, _PERIOD, _USER_ID = 0, 1, 2
_DISPLAY_NAME, _SLOT, _VERSION, _P1, _P2 = 3, 4, 5, 6, 7
_READY_AT, _CLOSED_AT, _NET, _DEBTOR, _PIF_AT, _PIF_NOTE = 8, 9, 10, 11, 12, 13

CLAIM_RECORD = "claim"
PERIOD_RECORD = "period"


def _cell(row: List[str], index: int) -> str:
    return (row[index] if index < len(row) else "").strip()


def _money(value: Optional[object]) -> str:
    """A net as the sheet should carry it: two decimals, or blank.

    Through the contract's own formatter so a settlement figure is spelled
    exactly like every amount already on the sheet.
    """
    if value is None or value == "":
        return ""
    try:
        return format_amount(Decimal(str(value)))
    except InvalidOperation:
        logger.warning(f"[sync_sheet] dropping unreadable net {value!r} from the sheet")
        return ""


def _int_or_zero(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        return 0


def ensure_sync_worksheet(gateway: SheetGateway) -> None:
    """Create ``_sync`` with its header row and hide it. Idempotent."""
    try:
        gateway.create_worksheet(SYNC_TITLE, rows=100, cols=len(SYNC_HEADERS))
    except WorksheetExists:
        pass

    if not gateway.read_rows(SYNC_TITLE):
        gateway.append_rows(SYNC_TITLE, [list(SYNC_HEADERS)])

    gateway.set_hidden(SYNC_TITLE, True)


def read_claims(gateway: SheetGateway) -> List[Claim]:
    try:
        rows = gateway.read_rows(SYNC_TITLE)
    except WorksheetNotFound:
        return []

    claims: List[Claim] = []
    for row in rows[1:]:
        if _cell(row, _RECORD) != CLAIM_RECORD or not _cell(row, _USER_ID):
            continue
        slot = _int_or_zero(_cell(row, _SLOT))
        if slot not in (1, 2):
            continue
        claims.append(
            Claim(
                user_id=_cell(row, _USER_ID),
                display_name=_cell(row, _DISPLAY_NAME),
                person_slot=slot,
                contract_version=_cell(row, _VERSION),
                person_1_name=_cell(row, _P1),
                person_2_name=_cell(row, _P2),
            )
        )
    return claims


def _claim_values(claim: Claim) -> List[str]:
    values = [""] * len(SYNC_HEADERS)
    values[_RECORD] = CLAIM_RECORD
    values[_USER_ID] = claim.user_id
    values[_DISPLAY_NAME] = claim.display_name
    values[_SLOT] = str(claim.person_slot)
    values[_VERSION] = claim.contract_version
    values[_P1] = claim.person_1_name
    values[_P2] = claim.person_2_name
    return values


def _upsert_row(gateway: SheetGateway, key: tuple, values: List[str]) -> None:
    """Write ``values`` over the first row matching ``key``, else append.

    ``key`` is (Record, Period, User ID) — a claim carries no period, so its
    key is simply the one with a blank middle. One identity for both record
    types keeps a period record from ever overwriting a claim.
    """
    ensure_sync_worksheet(gateway)
    rows = gateway.read_rows(SYNC_TITLE)

    for offset, row in enumerate(rows[1:], start=2):
        if (_cell(row, _RECORD), _cell(row, _PERIOD), _cell(row, _USER_ID)) == key:
            gateway.write_cells(
                SYNC_TITLE,
                [CellUpdate(row=offset, col=i + 1, value=v) for i, v in enumerate(values)],
            )
            return

    gateway.append_rows(SYNC_TITLE, [values])


def write_claim(gateway: SheetGateway, claim: Claim) -> None:
    """Upsert this instance's claim row, keyed on its user id."""
    _upsert_row(
        gateway,
        (CLAIM_RECORD, "", claim.user_id),
        _claim_values(claim),
    )


def read_period_records(gateway: SheetGateway) -> List[dict]:
    """Every instance's settlement position, as written to ``_sync``.

    Rows missing a period or a user id are skipped rather than raising: this
    worksheet is visible to anyone who unhides it, and a half-typed row must
    not take a sync down.
    """
    try:
        rows = gateway.read_rows(SYNC_TITLE)
    except WorksheetNotFound:
        return []

    records: List[dict] = []
    for row in rows[1:]:
        if _cell(row, _RECORD) != PERIOD_RECORD:
            continue
        period, user_id = _cell(row, _PERIOD), _cell(row, _USER_ID)
        if not period or not user_id:
            continue
        records.append(
            {
                "period": period,
                "user_id": user_id,
                "display_name": _cell(row, _DISPLAY_NAME),
                "ready_at": _cell(row, _READY_AT) or None,
                "closed_at": _cell(row, _CLOSED_AT) or None,
                "net_amount": _cell(row, _NET) or None,
                "debtor_user_id": _cell(row, _DEBTOR) or None,
                "pif_at": _cell(row, _PIF_AT) or None,
                "pif_note": _cell(row, _PIF_NOTE) or None,
            }
        )
    return records


def write_period_record(gateway: SheetGateway, record: dict) -> None:
    """Upsert one instance's settlement position, keyed on (period, user id).

    Blank cells are meaningful — clearing ``PIF At`` is how a month is
    reopened — so every column is written on every upsert.
    """
    values = [""] * len(SYNC_HEADERS)
    values[_RECORD] = PERIOD_RECORD
    values[_PERIOD] = record["period"]
    values[_USER_ID] = record["user_id"]
    values[_DISPLAY_NAME] = escape_formula(record.get("display_name") or "")
    values[_READY_AT] = record.get("ready_at") or ""
    values[_CLOSED_AT] = record.get("closed_at") or ""
    values[_NET] = _money(record.get("net_amount"))
    values[_DEBTOR] = record.get("debtor_user_id") or ""
    values[_PIF_AT] = record.get("pif_at") or ""
    values[_PIF_NOTE] = escape_formula(record.get("pif_note") or "")

    _upsert_row(
        gateway,
        (PERIOD_RECORD, record["period"], record["user_id"]),
        values,
    )
