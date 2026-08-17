"""The hidden ``_sync`` worksheet — the instances' handshake.

One table with a ``Record`` discriminator. ``claim`` rows are one per instance
and carry everything that is not per-transaction: who I am, which person slot I
occupy, and which contract version I speak. ``period`` rows are written by
sub-project C; they are defined here so the schema is stable, and ignored by
everything in Part II.

Hidden because it is machine state living inside a spreadsheet a human reads by
hand. Unhiding it in the Sheets UI still shows everything.
"""
from __future__ import annotations

from typing import List

from sheet_sync.gateway import (
    CellUpdate,
    SheetGateway,
    WorksheetExists,
    WorksheetNotFound,
)
from sheet_sync.guards import Claim

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
    # Reserved for sub-project C. Defined now so the schema never changes shape.
    "Ready At",
    "Closed At",
    "Net Amount",
    "Debtor User ID",
    "PIF At",
    "PIF Note",
]

_RECORD, _PERIOD, _USER_ID = 0, 1, 2
_DISPLAY_NAME, _SLOT, _VERSION, _P1, _P2 = 3, 4, 5, 6, 7

CLAIM_RECORD = "claim"


def _cell(row: List[str], index: int) -> str:
    return (row[index] if index < len(row) else "").strip()


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
        claims.append(
            Claim(
                user_id=_cell(row, _USER_ID),
                display_name=_cell(row, _DISPLAY_NAME),
                person_slot=_int_or_zero(_cell(row, _SLOT)),
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


def write_claim(gateway: SheetGateway, claim: Claim) -> None:
    """Upsert this instance's claim row, keyed on its user id."""
    ensure_sync_worksheet(gateway)
    rows = gateway.read_rows(SYNC_TITLE)
    values = _claim_values(claim)

    for offset, row in enumerate(rows[1:], start=2):
        if _cell(row, _RECORD) == CLAIM_RECORD and _cell(row, _USER_ID) == claim.user_id:
            gateway.write_cells(
                SYNC_TITLE,
                [CellUpdate(row=offset, col=i + 1, value=v) for i, v in enumerate(values)],
            )
            return

    gateway.append_rows(SYNC_TITLE, [values])
