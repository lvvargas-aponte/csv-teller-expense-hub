"""Applies a ``PushPlan`` to a worksheet. The only module here that does I/O.

``engine`` stays pure, so its plan is computed against one pre-write read and
every row number in it — in ``updates`` and in ``delete_row_numbers`` alike —
refers to that snapshot. Deleting first would renumber the rows the updates
address and write pending corrections into the wrong financial row, so the
order below is part of the contract, not a preference.
"""
from __future__ import annotations

from sheet_sync.engine import PushPlan
from sheet_sync.gateway import SheetGateway


def apply_push(gateway: SheetGateway, title: str, plan: PushPlan) -> None:
    if plan.updates:
        gateway.write_cells(title, plan.updates)
    if plan.appends:
        gateway.append_rows(title, plan.appends)
    if plan.delete_row_numbers:
        gateway.delete_rows(title, plan.delete_row_numbers)
