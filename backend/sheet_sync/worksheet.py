"""Period ↔ worksheet title, and creating a month's worksheet.

Titles on the live spreadsheet are irregular: a PIF suffix appears once a month
is settled, one title carries a stray dash, and one worksheet is not a month at
all. Parsing is therefore lenient about everything except the month and year.
"""
from __future__ import annotations

import calendar
import re
from typing import Optional

from sheet_sync.gateway import SheetGateway, WorksheetExists, WorksheetNotFound

CUTOVER_PERIOD = "2026-06"


class NoTemplateWorksheet(Exception):
    """No existing month worksheet to copy formatting from."""


_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_TITLE_RE = re.compile(
    r"^\s*([A-Za-z]+)\s*-?\s*(\d{4})\b", re.IGNORECASE
)


def period_to_title(period: str) -> str:
    year, month = period.split("-")
    return f"{calendar.month_name[int(month)]} {int(year)}"


def title_to_period(title: str) -> Optional[str]:
    match = _TITLE_RE.match(title or "")
    if not match:
        return None
    month = _MONTHS.get(match.group(1).lower())
    if month is None:
        return None
    return f"{int(match.group(2)):04d}-{month:02d}"


def is_settled_title(title: str) -> bool:
    return "pif" in (title or "").lower()


def find_worksheet(gateway: SheetGateway, period: str) -> Optional[str]:
    for title in gateway.list_worksheets():
        if title_to_period(title) == period:
            return title
    return None


def latest_month_title(gateway: SheetGateway) -> Optional[str]:
    best: Optional[tuple[str, str]] = None
    for title in gateway.list_worksheets():
        period = title_to_period(title)
        if period and (best is None or period > best[0]):
            best = (period, title)
    return best[1] if best else None


def ensure_worksheet(gateway: SheetGateway, period: str) -> str:
    """Return the worksheet title for ``period``, creating it if needed.

    Creation duplicates the most recent month so header text, formatting,
    column widths and frozen rows carry over, then clears the copied data.
    """
    existing = find_worksheet(gateway, period)
    if existing:
        return existing

    template = latest_month_title(gateway)
    if template is None:
        raise NoTemplateWorksheet(
            f"No month worksheet to use as a template for {period}"
        )

    title = period_to_title(period)
    try:
        gateway.duplicate_worksheet(template, title)
    except (WorksheetExists, WorksheetNotFound):
        # Someone — plausibly the user's Apps Script — created it first.
        found = find_worksheet(gateway, period)
        if found:
            return found
        raise

    gateway.clear_rows_from(title, 2)
    return title
