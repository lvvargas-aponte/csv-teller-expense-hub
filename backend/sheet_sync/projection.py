"""Local transaction documents ↔ sheet rows. Pure — no I/O.

Kept apart from ``service.py`` because these are the rules, not the plumbing:
which rows may be published, who the payer is, and — the one the previous
implementation got wrong — that only the non-payer's owes cell is ever filled.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from sheet_sync import contract
from sheet_sync.engine import DesiredRow, SheetRow


@dataclass(frozen=True)
class Unpublishable:
    transaction_id: str
    description: str
    reason: str


def period_of(txn: Dict[str, Any]) -> Optional[str]:
    """The month whose settlement includes this row.

    ``settles_in_period`` wins when present — that is how a transaction dated
    inside a closed month settles in the current open one instead.
    """
    explicit = (txn.get("settles_in_period") or "").strip()
    if explicit:
        return explicit
    parsed = contract.parse_date_loose(txn.get("date"))
    return parsed.strftime("%Y-%m") if parsed else None


def payer_slot(who: str, person_1_name: str, person_2_name: str) -> Optional[int]:
    name = (who or "").strip().casefold()
    if not name:
        return None
    if name == person_1_name.strip().casefold():
        return 1
    if name == person_2_name.strip().casefold():
        return 2
    return None


def owned_payer_slot(
    who: str, person_1_name: str, person_2_name: str, my_slot: int
) -> Optional[int]:
    """The payer's slot for a transaction *this* instance owns.

    A blank ``who`` resolves to us. The row came off our own account, so we
    paid it — an expense the peer paid reaches the sheet from their instance,
    never ours. The app has never modelled a payer (``who`` is blank on every
    stored transaction); it used to be typed straight into the sheet by hand.

    A ``who`` that is present but matches neither name still returns None: that
    is a value someone chose, and guessing past it would fill the wrong cell.
    """
    if not (who or "").strip():
        return my_slot
    return payer_slot(who, person_1_name, person_2_name)


def _decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def project_push(
    items: List[Tuple[str, Dict[str, Any]]],
    period: str,
    me: str,
    person_1_name: str,
    person_2_name: str,
    my_slot: int,
) -> Tuple[List[DesiredRow], List[Unpublishable]]:
    """Select and shape the local rows this instance should publish for ``period``.

    Sharing a row is the decision to publish it; ``reviewed`` rides along as
    triage state rather than gating the push. It cannot gate: the app's own
    bulk action sets ``reviewed`` False precisely *because* a row is shared, so
    requiring both would make a shared row unpublishable by construction.

    A blank owes cell therefore means "no split set", not "not yet published".
    """
    desired: List[DesiredRow] = []
    unpublishable: List[Unpublishable] = []

    for transaction_id, txn in items:
        if not txn.get("is_shared"):
            continue
        if period_of(txn) != period:
            continue

        description = txn.get("description") or ""
        when = contract.parse_date_loose(txn.get("date"))
        if when is None:
            unpublishable.append(
                Unpublishable(
                    transaction_id,
                    description,
                    f"Cannot read {txn.get('date')!r} as a date.",
                )
            )
            continue

        slot = owned_payer_slot(
            txn.get("who") or "", person_1_name, person_2_name, my_slot
        )
        if slot is None:
            unpublishable.append(
                Unpublishable(
                    transaction_id,
                    description,
                    f"Who is {txn.get('who')!r}, which is neither "
                    f"{person_1_name!r} nor {person_2_name!r}, so sync cannot tell "
                    f"whose owes cell to fill.",
                )
            )
            continue

        amount = _decimal(txn.get("amount"))
        if amount is None:
            unpublishable.append(
                Unpublishable(
                    transaction_id,
                    description,
                    f"Cannot read {txn.get('amount')!r} as an amount.",
                )
            )
            continue

        owes_1 = None if slot == 1 else _decimal(txn.get("person_1_owes"))
        owes_2 = None if slot == 2 else _decimal(txn.get("person_2_owes"))
        non_payer_owes = owes_2 if slot == 1 else owes_1
        if not non_payer_owes:
            payer_name = person_1_name if slot == 1 else person_2_name
            unpublishable.append(
                Unpublishable(
                    transaction_id,
                    description,
                    f"No split set — the amount {payer_name} is owed is blank or "
                    f"zero, so there is nothing to publish. Set a split in the app.",
                )
            )
            continue

        desired.append(
            DesiredRow(
                txn_id=contract.make_txn_id(me, transaction_id),
                owner=me,
                date=when,
                description=description,
                amount=abs(amount),
                who=person_1_name if slot == 1 else person_2_name,
                owes_1=owes_1,
                owes_2=owes_2,
                notes=txn.get("notes") or "",
                reviewed=bool(txn.get("reviewed")),
                carried_from=(txn.get("carried_from_period") or "") or None,
            )
        )

    return desired, unpublishable


def project_peer_row(
    row: SheetRow,
    period: str,
    slot_to_user_id: Dict[int, str],
    person_1_name: str,
    person_2_name: str,
) -> Optional[Dict[str, Any]]:
    """Shape one peer-owned sheet row into ``peer_transactions_repo`` parameters.

    Returns None for a row the store cannot accept — the caller counts those as
    skipped rather than failing the cycle over one bad line in a hand-edited sheet.
    """
    values = row.values
    try:
        owner, _local = contract.split_txn_id(values.get("txn_id", ""))
        when = contract.parse_date(values.get("date"))
        amount = contract.parse_amount(values.get("amount"))
        owes_1 = contract.parse_amount(values.get("owes_1"))
        owes_2 = contract.parse_amount(values.get("owes_2"))
    except contract.ContractError:
        return None

    if when is None or amount is None:
        return None

    who = values.get("who") or ""
    slot = payer_slot(who, person_1_name, person_2_name)

    return {
        "txn_id": values["txn_id"],
        "owner_user_id": owner,
        "date": when.isoformat(),
        "description": values.get("description") or "",
        "amount": amount,
        "who": who,
        "person_1_owes": owes_1,
        "person_2_owes": owes_2,
        "notes": values.get("notes") or "",
        "reviewed": contract.parse_bool(values.get("reviewed")),
        "payer_user_id": slot_to_user_id.get(slot) if slot else None,
        "carried_from_period": (values.get("carried_from") or "") or None,
        "settles_in_period": period,
    }
