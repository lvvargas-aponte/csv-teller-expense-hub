"""The read-only join of both sides' shared rows, for display only.

Deliberately separate from ``service.py``'s sync-cycle orchestration: this
module runs no sync, writes nothing, and changes for a different reason — how
the shared-expenses page renders — than the push/pull cycle does.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import identity_service
import state
from config import PERSON_1_NAME, PERSON_2_NAME
from db import identity_repo, peer_transactions_repo, sync_state_repo
from sheet_sync import contract, projection


def _blocked_reason(
    txn: Dict[str, Any], person_1_name: str, person_2_name: str
) -> Optional[str]:
    """Why ``project_push`` would withhold this row, or None if it would not.

    Mirrors ``projection.project_push``'s checks in the same order, so the page
    never disagrees with what a sync cycle actually does.
    """
    if not txn.get("reviewed"):
        return "Not reviewed yet — review it in Transactions to publish."

    who = txn.get("who") or ""
    slot = projection.payer_slot(who, person_1_name, person_2_name)
    if slot is None:
        return (
            f"Who is {who or '(blank)'!r}, which is neither "
            f"{person_1_name!r} nor {person_2_name!r}, so sync cannot tell "
            f"whose owes cell to fill."
        )

    when = contract.parse_date_loose(txn.get("date"))
    if when is None:
        return f"Cannot read {txn.get('date')!r} as a date."

    if projection._decimal(txn.get("amount")) is None:
        return f"Cannot read {txn.get('amount')!r} as an amount."

    non_payer_owes = (
        projection._decimal(txn.get("person_2_owes"))
        if slot == 1
        else projection._decimal(txn.get("person_1_owes"))
    )
    if not non_payer_owes:
        return "No split set — nothing to publish. Set a split in Transactions."

    return None


def _owes_by_slot(
    my_slot: int, txn_slot: Optional[int], owes_1: Any, owes_2: Any
) -> tuple[Optional[float], Optional[float]]:
    """(you_owe, they_owe), with the payer's side forced to None.

    ``txn_slot`` is the payer's slot; when unresolvable neither side is the
    payer, so nothing is forced null but there is also nothing sensible to
    report — both halves stay whatever the raw values say once cast to float.
    """
    def _num(v: Any) -> Optional[float]:
        return None if v is None else float(v)

    my_owes = owes_1 if my_slot == 1 else owes_2
    their_owes = owes_2 if my_slot == 1 else owes_1
    if txn_slot == my_slot:
        my_owes = None
    elif txn_slot is not None:
        their_owes = None
    return _num(my_owes), _num(their_owes)


def _my_row(
    transaction_id: str,
    txn: Dict[str, Any],
    my_user_id: str,
    my_slot: int,
    person_1_name: str,
    person_2_name: str,
) -> Dict[str, Any]:
    who = txn.get("who") or ""
    txn_slot = projection.payer_slot(who, person_1_name, person_2_name)
    you_owe, they_owe = _owes_by_slot(
        my_slot, txn_slot, txn.get("person_1_owes"), txn.get("person_2_owes")
    )
    when = contract.parse_date_loose(txn.get("date"))
    reason = _blocked_reason(txn, person_1_name, person_2_name)

    row_state = sync_state_repo.get_row_state(
        contract.make_txn_id(my_user_id, transaction_id)
    ) or {}

    return {
        "transaction_id": transaction_id,
        "owner": "me",
        "owner_name": person_1_name if my_slot == 1 else person_2_name,
        "date": when.isoformat() if when else txn.get("date"),
        "description": txn.get("description") or "",
        "amount": txn.get("amount"),
        "who": who,
        "notes": txn.get("notes") or "",
        "you_owe": you_owe,
        "they_owe": they_owe,
        "reviewed": bool(txn.get("reviewed")),
        "publishable": reason is None,
        "blocked_reason": reason,
        "dispute_flag": row_state.get("dispute_flag"),
        "dispute_by": row_state.get("dispute_by"),
        "dispute_note": row_state.get("dispute_note"),
        "synced_at": _iso(row_state.get("sheet_synced_at")),
    }


def _peer_row(
    peer_row: Dict[str, Any], my_slot: int, peer_name: str
) -> Dict[str, Any]:
    who = peer_row.get("who") or ""
    txn_slot = projection.payer_slot(who, PERSON_1_NAME, PERSON_2_NAME)
    you_owe, they_owe = _owes_by_slot(
        my_slot,
        txn_slot,
        peer_row.get("person_1_owes"),
        peer_row.get("person_2_owes"),
    )

    return {
        "transaction_id": peer_row["txn_id"],
        "owner": "peer",
        "owner_name": peer_name,
        "date": peer_row.get("date"),
        "description": peer_row.get("description") or "",
        "amount": peer_row.get("amount"),
        "who": who,
        "notes": peer_row.get("notes") or "",
        "you_owe": you_owe,
        "they_owe": they_owe,
        "reviewed": bool(peer_row.get("reviewed")),
        "publishable": True,
        "blocked_reason": None,
        "dispute_flag": peer_row.get("dispute_flag"),
        "dispute_by": peer_row.get("dispute_by"),
        "dispute_note": peer_row.get("dispute_note"),
        "synced_at": None,
    }


def _iso(value) -> Optional[str]:
    return value.isoformat() if hasattr(value, "isoformat") else value


def shared_rows(period: str) -> Dict[str, Any]:
    """Both sides' shared rows for ``period``, joined for display only.

    Yours come from ``state.stored_transactions`` (is_shared, any review
    state); theirs from ``peer_transactions_repo`` (already on the sheet, so
    always publishable). Never writes to either store.
    """
    mine = identity_service.ensure_identity()
    peers = identity_repo.list_peers()
    my_slot = mine["person_slot"]

    rows: List[Dict[str, Any]] = []
    for transaction_id, txn in state.stored_transactions.items():
        if not txn.get("is_shared"):
            continue
        if projection.period_of(txn) != period:
            continue
        rows.append(
            _my_row(
                transaction_id,
                txn,
                mine["user_id"],
                my_slot,
                PERSON_1_NAME,
                PERSON_2_NAME,
            )
        )

    peer_name = peers[0]["display_name"] if peers else PERSON_2_NAME if my_slot == 1 else PERSON_1_NAME
    for peer_row in peer_transactions_repo.list_for_period(period):
        rows.append(_peer_row(peer_row, my_slot, peer_name))

    rows.sort(key=lambda r: (r["date"] or "", r["description"], r["transaction_id"]))

    return {
        "period": period,
        "me": {
            "user_id": mine["user_id"],
            "display_name": mine["display_name"],
            "person_slot": my_slot,
        },
        "peer": (
            {"display_name": peers[0]["display_name"], "person_slot": peers[0]["person_slot"]}
            if peers
            else None
        ),
        "rows": rows,
    }
