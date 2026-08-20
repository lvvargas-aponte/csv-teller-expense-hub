"""Orchestration — the one impure module that knows the whole cycle.

Everything it composes is pure or already behind a seam: guards, projection and
engine take plain data, the gateway hides Google. The order below is load
bearing: every guard runs, and refuses, before anything is written.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any, Dict, List, Optional

import identity_service
import state
from config import (
    PERSON_1_NAME,
    PERSON_2_NAME,
    SHEET_SYNC_ENABLED,
    SPREADSHEET_ID,
)
from db import identity_repo, peer_transactions_repo, sync_state_repo
from sheet_sync import applier, contract, engine, guards, projection, sync_sheet, worksheet
from sheet_sync.adoption import ADOPTED_ID_PREFIX
from sheet_sync.gateway import SheetGateway
from sheet_sync.guards import Claim

logger = logging.getLogger(__name__)


class SyncDisabled(Exception):
    """Sync is switched off, or the spreadsheet is not configured."""


@dataclass
class SyncOutcome:
    period: str
    status: str = "ok"
    title: Optional[str] = None
    rows_pushed: int = 0
    rows_pulled: int = 0
    rows_deleted: int = 0
    skipped_peer_rows: int = 0
    refusal_reason: Optional[str] = None
    refusal_message: Optional[str] = None
    error_detail: Optional[str] = None
    unpublishable: List[Dict[str, str]] = field(default_factory=list)
    corrections: List[Dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def open_periods(today: Optional[date] = None) -> List[str]:
    """Every month from the cutover to the current one.

    Sub-project C will subtract closed periods here; until then every month
    from the cutover forward is open by definition.
    """
    today = today or date.today()
    year, month = (int(p) for p in worksheet.CUTOVER_PERIOD.split("-"))
    periods: List[str] = []
    while (year, month) <= (today.year, today.month):
        periods.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return periods


def _my_claim() -> Claim:
    me = identity_service.ensure_identity()
    return Claim(
        user_id=me["user_id"],
        display_name=me["display_name"],
        person_slot=me["person_slot"],
        contract_version=contract.CONTRACT_VERSION,
        person_1_name=PERSON_1_NAME,
        person_2_name=PERSON_2_NAME,
    )


def _slot_map(me: Claim, peers: List[Claim]) -> Dict[int, str]:
    slots = {me.person_slot: me.user_id}
    for peer in peers:
        slots.setdefault(peer.person_slot, peer.user_id)
    for row in identity_repo.list_peers():
        slots.setdefault(row["person_slot"], row["user_id"])
    return slots


def _adopt_peers(peers: List[Claim]) -> None:
    """Replace the bootstrap placeholder with the peer's real id (A/PF-5).

    Their claim row is the only authoritative source: the id is minted on their
    instance and reaches us nowhere else.
    """
    for peer in peers:
        identity_repo.adopt_peer_identity(
            person_slot=peer.person_slot,
            real_user_id=peer.user_id,
            display_name=peer.display_name or "",
        )


def _visible_corrections(plan_corrections) -> List[Dict[str, str]]:
    """Keep only divergences the app did not itself cause.

    ``PushPlan.corrections`` records every overwritten cell, because telling
    them apart inside ``engine`` would make it stateful. A cell we overwrite
    because the user changed the transaction after the last push is the system
    working; only a change with no local edit behind it is a hand edit worth
    warning about.
    """
    if not plan_corrections:
        return []

    txn_ids = [c.txn_id for c in plan_corrections]
    synced = sync_state_repo.synced_at_map(txn_ids)
    local_ids = [contract.split_txn_id(t)[1] for t in txn_ids]
    edited = sync_state_repo.transactions_updated_at(local_ids)

    visible: List[Dict[str, str]] = []
    for correction in plan_corrections:
        pushed_at = synced.get(correction.txn_id)
        if pushed_at is None:
            continue
        changed_at = edited.get(contract.split_txn_id(correction.txn_id)[1])
        if changed_at is not None and changed_at > pushed_at:
            continue
        visible.append(
            {
                "txn_id": correction.txn_id,
                "column_name": correction.column_name,
                "sheet_value": correction.sheet_value,
                "app_value": correction.app_value,
            }
        )
    return visible


def _dispute_flag(raw: Optional[str]) -> Optional[str]:
    """Map a sheet cell to ``sync_row_state.dispute_flag``'s ``NULL``/``'Y'``/``'N'`` domain.

    The contract's truthy set (``TRUE``, ``X``, ``1``, ...) is wider than the
    column's check constraint, and ``TRUE`` is exactly what this app writes
    into the neighbouring ``Reviewed`` column — so a naive first-letter slice
    raises ``IntegrityError`` on a perfectly ordinary dispute cell.
    """
    text = (raw or "").strip()
    if not text:
        return None
    return "Y" if contract.parse_bool(text) else "N"


def _project_pull(
    result: engine.PullResult, period: str, slots: Dict[int, str]
) -> tuple[List[Dict[str, Any]], int]:
    """Shape the peer rows worth importing. Pure — no database write."""
    peer_params = []
    skipped = 0
    for row in result.peer_rows:
        mapped = projection.project_peer_row(
            row, period, slots, PERSON_1_NAME, PERSON_2_NAME
        )
        if mapped is None:
            skipped += 1
            continue
        peer_params.append(mapped)
    return peer_params, skipped


def _apply_pull(
    result: engine.PullResult, period: str, slots: Dict[int, str]
) -> tuple[int, int]:
    peer_params, skipped = _project_pull(result, period, slots)

    pulled = peer_transactions_repo.upsert_many(peer_params)

    for txn_id, values in result.my_disputes.items():
        sync_state_repo.set_disputes(
            txn_id,
            _dispute_flag(values.get("dispute")),
            values.get("dispute_by") or None,
            values.get("dispute_note") or None,
        )

    return pulled, skipped


def sync_period(
    gateway: SheetGateway, period: str, *, dry_run: bool = False
) -> SyncOutcome:
    outcome = SyncOutcome(period=period)
    run_id = sync_state_repo.start_run(period, "both")

    try:
        mine = _my_claim()

        # A dry run must not create or hide the ``_sync`` tab — ``read_claims``
        # already tolerates an absent worksheet, so it is safe to call bare.
        if not dry_run:
            sync_sheet.ensure_sync_worksheet(gateway)
        peers = [c for c in sync_sheet.read_claims(gateway) if c.user_id != mine.user_id]

        refusal = guards.check_claims(mine, peers)
        if refusal:
            return _refuse(outcome, run_id, refusal)

        if not dry_run:
            sync_sheet.write_claim(gateway, mine)
            _adopt_peers(peers)

        items = list(state.stored_transactions.items())
        desired, unpublishable = projection.project_push(
            items, period, mine.user_id, PERSON_1_NAME, PERSON_2_NAME
        )
        outcome.unpublishable = [u.__dict__ for u in unpublishable]

        title = worksheet.find_worksheet(gateway, period)
        if title is None:
            if not desired:
                sync_state_repo.finish_run(run_id, "ok")
                return outcome
            if dry_run:
                # Report the tab that would be created rather than creating it.
                outcome.title = worksheet.period_to_title(period)
                outcome.rows_pushed = len(desired)
                sync_state_repo.finish_run(
                    run_id, "ok", rows_pushed=outcome.rows_pushed
                )
                return outcome
            title = worksheet.ensure_worksheet(gateway, period)
        outcome.title = title

        rows = gateway.read_rows(title)
        if not rows:
            raise ValueError(f"Worksheet {title!r} has no header row")
        index = contract.header_index_map(rows[0], PERSON_1_NAME, PERSON_2_NAME)
        current = engine.read_sheet(rows, index)

        refusal = guards.check_duplicate_txn_ids(title, current)
        if refusal:
            return _refuse(outcome, run_id, refusal)

        slots = _slot_map(mine, peers)
        pull = engine.plan_pull(current, mine.user_id)
        if dry_run:
            peer_params, outcome.skipped_peer_rows = _project_pull(pull, period, slots)
            outcome.rows_pulled = len(peer_params)
        else:
            outcome.rows_pulled, outcome.skipped_peer_rows = _apply_pull(
                pull, period, slots
            )

        plan = engine.plan_push(desired, current, index, mine.user_id, rows[0])

        # Adopted rows have no local transaction by design — that absence must
        # never be read as "no longer shared". Without this filter engine.plan_push
        # sees them as owned-but-undesired and deletes them on the very next cycle.
        by_row_number = {r.row_number: r for r in current}
        delete_row_numbers = [
            row_number
            for row_number in plan.delete_row_numbers
            if not contract.split_txn_id(
                by_row_number[row_number].values["txn_id"]
            )[1].startswith(ADOPTED_ID_PREFIX)
        ]

        outcome.corrections = _visible_corrections(plan.corrections)
        outcome.rows_pushed = len(plan.appends) + len({u.row for u in plan.updates})
        outcome.rows_deleted = len(delete_row_numbers)

        if not dry_run:
            applier.apply_push(
                gateway, title, replace(plan, delete_row_numbers=delete_row_numbers)
            )
            for row in desired:
                sync_state_repo.mark_synced(
                    row.txn_id, contract.split_txn_id(row.txn_id)[1], period
                )
            sync_state_repo.record_corrections(period, outcome.corrections)
            sync_state_repo.delete_row_state(
                [r.values["txn_id"] for r in current
                 if r.row_number in set(delete_row_numbers)]
            )

        sync_state_repo.finish_run(
            run_id,
            "ok",
            rows_pushed=outcome.rows_pushed,
            rows_pulled=outcome.rows_pulled,
            rows_deleted=outcome.rows_deleted,
        )
        return outcome

    except Exception as e:
        logger.exception(f"[sync] {period} failed: {e}")
        outcome.status = "error"
        outcome.error_detail = str(e)
        outcome.rows_pushed = 0
        outcome.rows_deleted = 0
        outcome.rows_pulled = 0
        sync_state_repo.finish_run(run_id, "error", error_detail=str(e))
        return outcome


def _refuse(outcome: SyncOutcome, run_id: int, refusal: guards.Refusal) -> SyncOutcome:
    outcome.status = "refused"
    outcome.refusal_reason = refusal.reason
    outcome.refusal_message = refusal.message
    sync_state_repo.finish_run(run_id, "refused", refusal_reason=refusal.reason)
    logger.warning(f"[sync] {outcome.period} refused ({refusal.reason}): {refusal.message}")
    return outcome


def sync_all(
    gateway: SheetGateway,
    *,
    periods: Optional[List[str]] = None,
    dry_run: bool = False,
) -> List[SyncOutcome]:
    return [
        sync_period(gateway, period, dry_run=dry_run)
        for period in (periods or open_periods())
    ]


def build_gateway() -> SheetGateway:
    """The production gateway. Refuses unless sync is explicitly switched on."""
    if not SHEET_SYNC_ENABLED:
        raise SyncDisabled(
            "Shared-expense sync is disabled. Set SHEET_SYNC_ENABLED=true to "
            "let this instance write to the Google Sheet."
        )
    if not SPREADSHEET_ID:
        raise SyncDisabled("SPREADSHEET_ID is not configured.")

    from gsheet_integration import GoogleSheetsClient
    from sheet_sync.gateway import GspreadGateway

    client = GoogleSheetsClient().get_client()
    return GspreadGateway(client.open_by_key(SPREADSHEET_ID))


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


def status() -> Dict[str, Any]:
    """What ``GET /api/sync/status`` reports."""
    last = sync_state_repo.last_run()
    refusal = last if last and last["status"] == "refused" else None
    mine = _my_claim()
    pending = 0
    for period in open_periods():
        desired, _ = projection.project_push(
            list(state.stored_transactions.items()),
            period,
            mine.user_id,
            PERSON_1_NAME,
            PERSON_2_NAME,
        )
        pending += len(desired)

    return {
        "enabled": SHEET_SYNC_ENABLED,
        "open_periods": open_periods(),
        "last_run": last,
        "last_successful_pull": sync_state_repo.last_ok_run(),
        "publishable_rows": pending,
        "refusal": (
            {"reason": refusal["refusal_reason"]} if refusal else None
        ),
        "corrections": sync_state_repo.list_unacknowledged(),
        "disputes_against_me": sync_state_repo.list_disputes_against_me(),
    }
