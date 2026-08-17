"""The sheet's column contract and cell coercion. Pure — no I/O.

Column letters in the design describe intent; lookup is always by header name,
because the previous positional implementation is exactly what misaligned the
writer against a sheet whose shape had drifted.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

CONTRACT_VERSION = "1.0"


class ContractError(Exception):
    """The sheet does not match the contract this release speaks."""


# Logical key → header text. A callable takes the two person names.
_HEADERS: tuple[tuple[str, object], ...] = (
    ("date", "Transaction Date"),
    ("description", "Description"),
    ("amount", "Amount"),
    ("who", "Who"),
    ("owes_1", lambda p1, p2: f"What {p1} Owes"),
    ("owes_2", lambda p1, p2: f"What {p2} Owes"),
    ("notes", "Notes"),
    ("reviewed", "Reviewed"),
    ("dispute", "Dispute"),
    ("dispute_by", "Dispute By"),
    ("dispute_note", "Dispute Note"),
    ("txn_id", "Txn ID"),
    ("owner", "Owner"),
    ("carried_from", "Carried From"),
)

DISPUTER_KEYS = ("dispute", "dispute_by", "dispute_note")
OWNER_KEYS = tuple(k for k, _ in _HEADERS if k not in DISPUTER_KEYS)

_DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y")
_TRUTHY = {"true", "yes", "y", "1", "x"}


def _header_text(spec: object, person_1_name: str, person_2_name: str) -> str:
    return spec(person_1_name, person_2_name) if callable(spec) else spec


def build_headers(person_1_name: str, person_2_name: str) -> list[str]:
    return [_header_text(s, person_1_name, person_2_name) for _, s in _HEADERS]


def header_index_map(
    header_row: list[str], person_1_name: str, person_2_name: str
) -> dict[str, int]:
    """Logical key → 0-based column index, resolved by header text."""
    seen: dict[str, int] = {}
    for i, h in enumerate(header_row):
        text = (h or "").strip()
        if not text:
            continue
        if text in seen:
            raise ContractError(f"Sheet has a duplicate {text!r} column")
        seen[text] = i
    mapping: dict[str, int] = {}
    for key, spec in _HEADERS:
        wanted = _header_text(spec, person_1_name, person_2_name)
        if wanted not in seen:
            raise ContractError(f"Sheet is missing the {wanted!r} column")
        mapping[key] = seen[wanted]
    return mapping


def parse_amount(raw: Optional[str]) -> Optional[Decimal]:
    """Blank is None, never zero — blank means untriaged, and 0 settles a debt."""
    text = (raw or "").strip()
    if not text:
        return None
    cleaned = text.replace("$", "").replace(",", "").strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation as e:
        raise ContractError(f"Cannot read {raw!r} as an amount") from e


def format_amount(value: Optional[Decimal]) -> str:
    if value is None:
        return ""
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def parse_date(raw: Optional[str]) -> Optional[date]:
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ContractError(f"Cannot read {raw!r} as a date")


def parse_date_loose(raw: Optional[str]) -> Optional[date]:
    """``parse_date`` that returns None instead of raising. For local data,
    which reaches us from CSV importers rather than from the sheet."""
    try:
        return parse_date(raw)
    except ContractError:
        return None


def format_date(value: date) -> str:
    return value.strftime("%m/%d/%Y")


def parse_bool(raw: Optional[str]) -> bool:
    return (raw or "").strip().lower() in _TRUTHY


def format_bool(value: bool) -> str:
    return "TRUE" if value else ""


def make_txn_id(owner_user_id: str, transaction_id: str) -> str:
    return f"{owner_user_id}:{transaction_id}"


def split_txn_id(txn_id: str) -> tuple[str, str]:
    owner, sep, local = (txn_id or "").partition(":")
    if not sep or not owner or not local:
        raise ContractError(f"Malformed Txn ID {txn_id!r}")
    return owner, local
