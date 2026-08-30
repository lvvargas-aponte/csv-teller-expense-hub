"""The settlement footer a human reads at the bottom of a month worksheet.

The shape is not invented — it is the convention the spreadsheet has carried
by hand for three years, and it is reproduced exactly so a synced month looks
like every settled month before it:

    …last transaction…
    (blank)
                                    $640.99      $1,253.26      <- totals, E/F
    (blank)
            Christy pays Valeria via Zelle       $612.27        <- D and E

Totals come from the worksheet itself rather than from local state, so the
footer always reconciles against the rows printed above it — which is the only
thing a person reading the sheet can check.

Pure except for the gateway calls in ``write``: the arithmetic and the row
shapes are separately testable.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional

from sheet_sync import contract
from sheet_sync.gateway import CellUpdate, SheetGateway

logger = logging.getLogger(__name__)

PIF_SUFFIX = " - PIF"

# How the settlement line reads when nobody said otherwise. Both settled
# months on the live sheet say Zelle.
DEFAULT_METHOD = "via Zelle"

# " X pays Y …" — how the settlement line is recognised on a re-run, so the
# footer is rewritten in place instead of stacking up a second copy.
_SETTLEMENT_RE = re.compile(r"\bpays\b", re.IGNORECASE)


@dataclass(frozen=True)
class Footer:
    """The two rendered lines, and where they belong."""

    totals_row: int
    settlement_row: int
    owes_1: Decimal
    owes_2: Decimal
    net: Decimal
    debtor: str
    creditor: str
    method: str

    @property
    def sentence(self) -> str:
        return f"{self.debtor} pays {self.creditor} {self.method}".strip()


def _money(value: Decimal) -> str:
    """``$1,253.26`` — the sheet's own spelling, not the contract's bare form.

    The footer is prose for a person, unlike the transaction cells a sync
    reads back and compares.
    """
    quantised = value.quantize(Decimal("0.01"))
    return f"${quantised:,.2f}"


def totals_from_rows(
    rows: List[List[str]], index: dict, skip_rows: Optional[set] = None
) -> tuple[Decimal, Decimal]:
    """Sum the two owes columns over every transaction row.

    A row with no Txn ID is outside the contract — a hand-entered line, or the
    footer this module wrote last time — and is skipped, so re-running never
    counts a previous footer's totals as transactions.
    """
    skip = skip_rows or set()
    owes_1 = Decimal("0")
    owes_2 = Decimal("0")
    for offset, raw in enumerate(rows[1:], start=2):
        if offset in skip:
            continue
        cell = lambda key: (  # noqa: E731 - local reader, reads better inline
            raw[index[key]] if index.get(key) is not None and index[key] < len(raw) else ""
        )
        if not (cell("txn_id") or "").strip():
            continue
        owes_1 += contract.parse_amount(cell("owes_1")) or Decimal("0")
        owes_2 += contract.parse_amount(cell("owes_2")) or Decimal("0")
    return owes_1, owes_2


def find_existing(rows: List[List[str]], index: dict) -> tuple[Optional[int], Optional[int]]:
    """(totals_row, settlement_row) of a footer already on the sheet.

    Recognised by shape rather than by a marker column, because the three
    years of footers written by hand carry no marker: a settlement line is a
    row with no Txn ID whose Who cell reads "… pays …", and the totals line is
    the nearest earlier row with no Txn ID that carries an owes figure.
    """
    who_col = index.get("who")
    txn_col = index.get("txn_id")
    o1, o2 = index.get("owes_1"), index.get("owes_2")

    def cell(raw: List[str], col: Optional[int]) -> str:
        return (raw[col] if col is not None and col < len(raw) else "").strip()

    settlement_row = None
    for offset in range(len(rows), 1, -1):
        raw = rows[offset - 1]
        if cell(raw, txn_col):
            break   # reached the transaction block; no footer below it
        if _SETTLEMENT_RE.search(cell(raw, who_col)):
            settlement_row = offset
            break

    if settlement_row is None:
        return None, None

    totals_row = None
    for offset in range(settlement_row - 1, 1, -1):
        raw = rows[offset - 1]
        if cell(raw, txn_col):
            break
        if cell(raw, o1) or cell(raw, o2):
            totals_row = offset
            break

    return totals_row, settlement_row


def last_transaction_row(rows: List[List[str]], index: dict) -> int:
    txn_col = index.get("txn_id")
    for offset in range(len(rows), 1, -1):
        raw = rows[offset - 1]
        if (raw[txn_col] if txn_col is not None and txn_col < len(raw) else "").strip():
            return offset
    return 1


def plan(
    rows: List[List[str]],
    index: dict,
    *,
    person_1_name: str,
    person_2_name: str,
    method: Optional[str] = None,
) -> Footer:
    """Where the footer goes and what it says. Pure."""
    totals_row, settlement_row = find_existing(rows, index)
    if totals_row is None or settlement_row is None:
        # One blank row of air after the transactions, matching the sheet's
        # existing rhythm, then totals, a blank, and the settlement line.
        anchor = last_transaction_row(rows, index)
        totals_row = anchor + 2
        settlement_row = totals_row + 2

    owes_1, owes_2 = totals_from_rows(
        rows, index, skip_rows={totals_row, settlement_row}
    )
    net = owes_2 - owes_1
    debtor, creditor = (
        (person_2_name, person_1_name) if net >= 0 else (person_1_name, person_2_name)
    )

    return Footer(
        totals_row=totals_row,
        settlement_row=settlement_row,
        owes_1=owes_1,
        owes_2=owes_2,
        net=abs(net),
        debtor=debtor,
        creditor=creditor,
        method=(method or "").strip() or DEFAULT_METHOD,
    )


def updates_for(footer: Footer, index: dict) -> List[CellUpdate]:
    """The cells to write. Only the four the convention fills."""
    return [
        CellUpdate(row=footer.totals_row, col=index["owes_1"] + 1, value=_money(footer.owes_1)),
        CellUpdate(row=footer.totals_row, col=index["owes_2"] + 1, value=_money(footer.owes_2)),
        CellUpdate(row=footer.settlement_row, col=index["who"] + 1, value=footer.sentence),
        CellUpdate(row=footer.settlement_row, col=index["owes_1"] + 1, value=_money(footer.net)),
    ]


def write(
    gateway: SheetGateway,
    title: str,
    rows: List[List[str]],
    index: dict,
    *,
    person_1_name: str,
    person_2_name: str,
    method: Optional[str] = None,
) -> Footer:
    """Render the footer onto ``title``, rewriting any footer already there."""
    footer = plan(
        rows, index,
        person_1_name=person_1_name,
        person_2_name=person_2_name,
        method=method,
    )

    # The footer sits below the last row that exists, so the blank rows it
    # needs — including the separators — have to be added before any cell in
    # them can be addressed.
    missing = footer.settlement_row - len(rows)
    if missing > 0:
        width = len(rows[0]) if rows else 1
        gateway.append_rows(title, [[""] * width for _ in range(missing)])

    gateway.write_cells(title, updates_for(footer, index))
    return footer


def settled_title(title: str) -> str:
    """``June 2026`` -> ``June 2026 - PIF``. Idempotent."""
    return title if title.lower().endswith(PIF_SUFFIX.lower()) else title + PIF_SUFFIX


def unsettled_title(title: str) -> str:
    """``June 2026 - PIF`` -> ``June 2026``. The inverse of ``settled_title``."""
    if title.lower().endswith(PIF_SUFFIX.lower()):
        return title[: -len(PIF_SUFFIX)]
    return title
