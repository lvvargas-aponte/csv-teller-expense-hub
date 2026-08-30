"""The read-only join of both sides' shared rows, for display only.

Deliberately separate from ``service.py``'s sync-cycle orchestration: this
module runs no sync, writes nothing, and changes for a different reason — how
the shared-expenses page renders — than the push/pull cycle does.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

import identity_service
import state
from config import PERSON_1_NAME, PERSON_2_NAME
from institution_normalizer import normalize as normalize_institution
from db import identity_repo, peer_transactions_repo, sync_state_repo
from sheet_sync import contract, projection, settlement


def _blocked(
    txn: Dict[str, Any], person_1_name: str, person_2_name: str, my_slot: int
) -> tuple[Optional[str], Optional[str]]:
    """``(kind, reason)`` for why ``project_push`` would withhold this row.

    Mirrors ``projection.project_push``'s checks in the same order (date, then
    who/slot, then amount, then split), so the page never disagrees with what a
    sync cycle actually does — including which reason it reports first when a
    row fails more than one check. ``reviewed`` is not among them: it is triage
    state, not a gate.

    ``kind`` is the machine-readable half, so the page can offer the matching
    repair without reading the prose of ``reason``.
    """
    when = contract.parse_date_loose(txn.get("date"))
    if when is None:
        return "date", f"Cannot read {txn.get('date')!r} as a date."

    who = txn.get("who") or ""
    slot = projection.owned_payer_slot(who, person_1_name, person_2_name, my_slot)
    if slot is None:
        return "who", (
            f"Who is {who!r}, which is neither "
            f"{person_1_name!r} nor {person_2_name!r}, so sync cannot tell "
            f"whose owes cell to fill."
        )

    if projection._decimal(txn.get("amount")) is None:
        return "amount", f"Cannot read {txn.get('amount')!r} as an amount."

    non_payer_owes = (
        projection._decimal(txn.get("person_2_owes"))
        if slot == 1
        else projection._decimal(txn.get("person_1_owes"))
    )
    if not non_payer_owes:
        return "split", "No split set — nothing to publish."

    return None, None


def _owes_by_slot(
    my_slot: int, txn_slot: Optional[int], owes_1: Any, owes_2: Any
) -> tuple[Optional[float], Optional[float]]:
    """(you_owe, they_owe), with the payer's side forced to None.

    ``txn_slot`` is the payer's slot; when unresolvable neither side is the
    payer, so nothing is forced null but there is also nothing sensible to
    report — both halves stay whatever the raw values say once cast to float.
    """
    def _num(v: Any) -> Optional[float]:
        parsed = projection._decimal(v)
        return None if parsed is None else float(parsed)

    my_owes = owes_1 if my_slot == 1 else owes_2
    their_owes = owes_2 if my_slot == 1 else owes_1
    if txn_slot == my_slot:
        my_owes = None
    elif txn_slot is not None:
        their_owes = None
    return _num(my_owes), _num(their_owes)


def _split_label(
    amount: Any, you_owe: Optional[float], they_owe: Optional[float]
) -> Optional[str]:
    """e.g. ``"50 / 50 split"``, payer's share first, or None when there is none.

    Once the payer's slot resolves only one side is owed anything, so a row
    carrying figures on both sides (or on neither) has no split to describe.
    """
    owed = [v for v in (you_owe, they_owe) if v is not None]
    total = projection._decimal(amount)
    if len(owed) != 1 or total is None:
        return None

    total = abs(total)
    share = Decimal(str(owed[0]))
    if total <= 0 or share <= 0:
        return None

    # A share larger than the amount is a mis-entered split — exactly the kind
    # of row this page exists to surface — so clamp rather than render
    # "-20 / 120 split" and make the reader doubt the page instead of the row.
    other_pct = min(100, max(0, int((share / total * 100).to_integral_value())))
    return f"{100 - other_pct} / {other_pct} split"


def _my_row(
    transaction_id: str,
    txn: Dict[str, Any],
    my_user_id: str,
    my_slot: int,
    my_display_name: str,
    person_1_name: str,
    person_2_name: str,
) -> Dict[str, Any]:
    who = txn.get("who") or ""
    txn_slot = projection.owned_payer_slot(
        who, person_1_name, person_2_name, my_slot
    )
    you_owe, they_owe = _owes_by_slot(
        my_slot, txn_slot, txn.get("person_1_owes"), txn.get("person_2_owes")
    )
    when = contract.parse_date_loose(txn.get("date"))
    kind, reason = _blocked(txn, person_1_name, person_2_name, my_slot)

    row_state = sync_state_repo.get_row_state(
        contract.make_txn_id(my_user_id, transaction_id)
    ) or {}

    return {
        "transaction_id": transaction_id,
        "owner": "me",
        "owner_name": my_display_name,
        "date": when.isoformat() if when else txn.get("date"),
        "description": txn.get("description") or "",
        "amount": txn.get("amount"),
        "who": who,
        # Which person slot actually paid, as sync resolves it — a blank ``who``
        # resolves to us, so the page must not re-derive this by matching names.
        "payer_slot": txn_slot,
        "notes": txn.get("notes") or "",
        "category": txn.get("category") or None,
        "account": normalize_institution(txn.get("institution")) or None,
        "you_owe": you_owe,
        "they_owe": they_owe,
        "split_label": _split_label(txn.get("amount"), you_owe, they_owe),
        "reviewed": bool(txn.get("reviewed")),
        "publishable": reason is None,
        "blocked_reason": reason,
        "blocked_kind": kind,
        # The raw fields behind the display ones, so the page can repair a
        # blocked row in place. Only ours carry them: a peer row lives on
        # their instance and is not ours to edit.
        "editable": {
            "is_shared": bool(txn.get("is_shared")),
            "what": txn.get("what") or "",
            "person_1_owes": txn.get("person_1_owes"),
            "person_2_owes": txn.get("person_2_owes"),
            "raw_date": txn.get("date"),
            "raw_amount": txn.get("amount"),
        },
        "dispute_flag": row_state.get("dispute_flag"),
        "dispute_by": row_state.get("dispute_by"),
        "dispute_note": row_state.get("dispute_note"),
        "synced_at": _iso(row_state.get("sheet_synced_at")),
    }


def _peer_row(
    peer_row: Dict[str, Any],
    my_slot: int,
    peer_name: str,
    person_1_name: str,
    person_2_name: str,
) -> Dict[str, Any]:
    who = peer_row.get("who") or ""
    txn_slot = projection.payer_slot(who, person_1_name, person_2_name)
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
        "payer_slot": txn_slot,
        "notes": peer_row.get("notes") or "",
        # A peer row has no account or category columns to report, but it
        # carries the keys anyway so both row shapes can be indexed alike.
        "category": None,
        "account": None,
        "you_owe": you_owe,
        "they_owe": they_owe,
        "split_label": _split_label(peer_row.get("amount"), you_owe, they_owe),
        "reviewed": bool(peer_row.get("reviewed")),
        "publishable": True,
        "blocked_reason": None,
        "blocked_kind": None,
        "editable": None,
        "dispute_flag": peer_row.get("dispute_flag"),
        "dispute_by": peer_row.get("dispute_by"),
        "dispute_note": peer_row.get("dispute_note"),
        "synced_at": None,
    }


def _settlement(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The month's standing net, counting only rows a sync would publish.

    Computed here rather than in the page so the settle-up card and the list
    can never disagree about which rows count — the same reason
    ``_blocked`` mirrors ``projection.project_push``.
    """
    counted = [r for r in rows if r["publishable"]]

    you_owe_total = sum(Decimal(str(r["you_owe"])) for r in counted if r["you_owe"])
    they_owe_total = sum(Decimal(str(r["they_owe"])) for r in counted if r["they_owe"])
    counted_amount = sum(
        abs(projection._decimal(r["amount"]) or Decimal(0)) for r in counted
    )
    net = they_owe_total - you_owe_total

    if net > 0:
        direction = "they_owe"
    elif net < 0:
        direction = "you_owe"
    else:
        direction = "even"

    return {
        "you_owe_total": float(round(Decimal(you_owe_total), 2)),
        "they_owe_total": float(round(Decimal(they_owe_total), 2)),
        "net": float(round(abs(Decimal(net)), 2)),
        "direction": direction,
        "counted_count": len(counted),
        "counted_amount": float(round(Decimal(counted_amount), 2)),
        "blocked_count": len(rows) - len(counted),
    }


def _iso(value) -> Optional[str]:
    return value.isoformat() if hasattr(value, "isoformat") else value


def shared_rows(period: str, today: Optional[date] = None) -> Dict[str, Any]:
    """Both sides' shared rows for ``period``, joined for display only.

    Yours come from ``state.stored_transactions`` (is_shared, any review
    state); theirs from ``peer_transactions_repo`` (already on the sheet, so
    always publishable). Never writes to either store.

    ``today`` is injectable — same as ``service.open_periods`` — so the
    undated-row fallback below can be exercised without freezing global time.
    """
    mine = identity_service.ensure_identity()
    peers = identity_repo.list_peers()
    my_slot = mine["person_slot"]

    rows: List[Dict[str, Any]] = []
    current_period = (today or date.today()).strftime("%Y-%m")
    for transaction_id, txn in state.stored_transactions.items():
        if not txn.get("is_shared"):
            continue
        row_period = projection.period_of(txn)
        # A row whose date cannot be read belongs to no month, so it would be
        # invisible on every one of them — including the page that exists to
        # report why sync will not publish it. It is listed on the current
        # month instead, once, so it can be found and repaired.
        if row_period is None:
            if period != current_period:
                continue
        elif row_period != period:
            continue
        rows.append(
            _my_row(
                transaction_id,
                txn,
                mine["user_id"],
                my_slot,
                mine["display_name"],
                PERSON_1_NAME,
                PERSON_2_NAME,
            )
        )

    peer_name = peers[0]["display_name"] if peers else PERSON_2_NAME if my_slot == 1 else PERSON_1_NAME
    for peer_row in peer_transactions_repo.list_for_period(period):
        rows.append(
            _peer_row(peer_row, my_slot, peer_name, PERSON_1_NAME, PERSON_2_NAME)
        )

    rows.sort(key=lambda r: (r["date"] or "", r["description"], r["transaction_id"]))
    block = _settlement(rows)

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
        "settlement": block,
        "settlement_state": settlement.describe(period, block),
    }
