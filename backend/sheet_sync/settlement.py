"""Settling a month: who says they're done, and who says it's paid.

Deliberately separate from ``service.py``'s push/pull cycle and from
``shared_view.py``'s row rendering: this module changes when the settlement
handshake changes, which is a different reason than either of those.

The handshake is ADVISORY. Each instance publishes its own position — "my rows
are complete, and here is the net I computed" — and either instance may declare
the month paid without the other agreeing. Nothing here blocks on the peer.
When the two sides computed different nets that disagreement is reported rather
than resolved: the app cannot know which side is missing a receipt.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import identity_service
from db import period_settlements_repo

logger = logging.getLogger(__name__)

# What ``state`` can be, in the order the page walks through them.
OPEN = "open"
READY = "ready"
SETTLED = "settled"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mine_and_theirs(
    period: str, my_user_id: str
) -> tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    records = period_settlements_repo.list_for_period(period)
    mine = next((r for r in records if r["user_id"] == my_user_id), None)
    theirs = [r for r in records if r["user_id"] != my_user_id]
    return mine, theirs


def _net_of(settlement: Optional[Dict[str, Any]]) -> Optional[float]:
    """The signed net a settlement block describes, from my point of view.

    Positive means the peer owes me. ``shared_view`` reports ``net`` as an
    absolute value plus a direction, which is right for display and useless for
    comparison, so it is re-signed here.
    """
    if not settlement:
        return None
    net = settlement.get("net")
    if settlement.get("direction") == "you_owe":
        return -float(net)
    return float(net)


def describe(period: str, settlement: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """This month's settlement position, for the page and the API.

    ``settlement`` is the live block from ``shared_view.shared_rows`` — the net
    as it stands right now. The stored ``net_amount`` is what was true when
    someone declared ready, so the two differing is meaningful: it means rows
    changed since.
    """
    me = identity_service.ensure_identity()
    mine, theirs = _mine_and_theirs(period, me["user_id"])

    paid_by = next((r for r in [mine, *theirs] if r and r["pif_at"]), None)
    if paid_by:
        state = SETTLED
    elif mine and mine["ready_at"]:
        state = READY
    else:
        state = OPEN

    live_net = _net_of(settlement)
    peer_ready = next((r for r in theirs if r["ready_at"]), None)

    # Both sides declared a net; if they disagree the page says so rather than
    # picking one. Compared at cent precision — these are money, not floats.
    disagreement = None
    if mine and peer_ready and mine["net_amount"] is not None and peer_ready["net_amount"] is not None:
        mine_cents = round(float(mine["net_amount"]) * 100)
        # A peer's net is signed from THEIR side, so ours is its negation.
        theirs_cents = -round(float(peer_ready["net_amount"]) * 100)
        if mine_cents != theirs_cents:
            disagreement = {
                "mine": round(mine_cents / 100, 2),
                "theirs": round(theirs_cents / 100, 2),
            }

    return {
        "state": state,
        "period": period,
        "you_ready": bool(mine and mine["ready_at"]),
        "peer_ready": bool(peer_ready),
        "peer_ready_name": _display_name(peer_ready),
        "paid_at": paid_by["pif_at"] if paid_by else None,
        "paid_note": paid_by["pif_note"] if paid_by else None,
        "paid_by_me": bool(paid_by and paid_by["user_id"] == me["user_id"]),
        "paid_by_name": _display_name(paid_by),
        "declared_net": float(mine["net_amount"]) if mine and mine["net_amount"] is not None else None,
        "live_net": live_net,
        "net_disagreement": disagreement,
    }


def _display_name(record: Optional[Dict[str, Any]]) -> Optional[str]:
    """Whose record this is, by name.

    ``period_settlements`` stores only the user id — names live in
    ``identity_repo``, the one place that knows them — so it is resolved here
    rather than denormalised into the settlement row.
    """
    if not record:
        return None
    from db import identity_repo

    me = identity_service.ensure_identity()
    if record["user_id"] == me["user_id"]:
        return me["display_name"]
    for peer in identity_repo.list_peers():
        if peer["user_id"] == record["user_id"]:
            return peer["display_name"] or None
    return None


def _write(period: str, **fields: Any) -> Dict[str, Any]:
    me = identity_service.ensure_identity()
    return period_settlements_repo.upsert(period, me["user_id"], **fields)


def _current(period: str) -> Dict[str, Any]:
    me = identity_service.ensure_identity()
    return period_settlements_repo.get(period, me["user_id"]) or {}


def mark_ready(period: str, settlement: Dict[str, Any]) -> Dict[str, Any]:
    """Declare my rows for ``period`` complete, recording the net I computed."""
    me = identity_service.ensure_identity()
    net = _net_of(settlement)
    debtor = None
    if net is not None and net != 0:
        debtor = _peer_user_id() if net > 0 else me["user_id"]

    existing = _current(period)
    return _write(
        period,
        ready_at=_now(),
        net_amount=net,
        debtor_user_id=debtor,
        pif_at=existing.get("pif_at"),
        pif_note=existing.get("pif_note"),
        closed_at=existing.get("closed_at"),
    )


def withdraw_ready(period: str) -> Dict[str, Any]:
    """Take back "my rows are complete" — a row turned up after all."""
    existing = _current(period)
    return _write(
        period,
        ready_at=None,
        net_amount=None,
        debtor_user_id=None,
        pif_at=existing.get("pif_at"),
        pif_note=existing.get("pif_note"),
        closed_at=existing.get("closed_at"),
    )


def mark_paid(
    period: str, settlement: Dict[str, Any], note: Optional[str] = None
) -> Dict[str, Any]:
    """Declare ``period`` paid in full.

    Never blocked on the peer: this instance may settle a month the other side
    has not agreed to, and marking paid implies ready even if it was never
    declared, because the two cannot meaningfully disagree once money moved.
    """
    existing = _current(period)
    now = _now()
    net = _net_of(settlement)
    return _write(
        period,
        ready_at=existing.get("ready_at") or now,
        net_amount=existing.get("net_amount") if existing.get("ready_at") else net,
        debtor_user_id=existing.get("debtor_user_id"),
        pif_at=now,
        pif_note=(note or "").strip() or None,
        closed_at=now,
    )


def reopen(period: str) -> Dict[str, Any]:
    """Undo my own "paid in full".

    Only ever clears THIS instance's record. If the peer also marked the month
    paid it stays settled until they reopen it on their side — the same
    one-sidedness that let either of us settle it in the first place.
    """
    existing = _current(period)
    return _write(
        period,
        ready_at=existing.get("ready_at"),
        net_amount=existing.get("net_amount"),
        debtor_user_id=existing.get("debtor_user_id"),
        pif_at=None,
        pif_note=None,
        closed_at=None,
    )


class AlreadySettled(Exception):
    """The month is already marked paid in full — by the peer, or by hand."""


def who_settled(period: str) -> Optional[str]:
    """The name on an existing "paid in full", or None if nobody has said so.

    Reads local records only. The sheet's own ``- PIF`` title is checked
    separately, at publish time, because a tab renamed by hand carries no
    author for us to name.
    """
    me = identity_service.ensure_identity()
    mine, theirs = _mine_and_theirs(period, me["user_id"])
    settled = next((r for r in [mine, *theirs] if r and r["pif_at"]), None)
    return _display_name(settled) if settled else None


def publish(period: str, *, settle: bool = False, method: Optional[str] = None) -> Dict[str, Any]:
    """Push this month's settlement to the spreadsheet.

    Two visible effects, both of which a person reads directly:
    the footer at the bottom of the month tab, and — once settled — the
    ``- PIF`` suffix on the tab's own title, the convention this spreadsheet
    has used since 2023.

    Never raises for a sheet problem: a settlement is a statement about a
    month, and failing to publish it must not lose the local record. The
    outcome is reported so the page can say what happened.
    """
    from sheet_sync import contract, footer, service, worksheet

    try:
        gateway = service.build_gateway()
    except Exception as e:
        # Google's exception strings carry spreadsheet ids and service-account
        # detail, and this reason is rendered on the page — log, don't echo.
        logger.warning(f"[settlement] {period} could not open the spreadsheet: {e}")
        return {"published": False, "reason": "Could not reach the spreadsheet."}

    try:
        from config import PERSON_1_NAME, PERSON_2_NAME

        title = worksheet.find_worksheet(gateway, period)
        if title is None:
            return {"published": False, "reason": f"No worksheet for {period} yet."}

        rows = gateway.read_rows(title)
        if not rows:
            return {"published": False, "reason": f"Worksheet {title!r} is empty."}
        index = contract.header_index_map(rows[0], PERSON_1_NAME, PERSON_2_NAME)

        written = footer.write(
            gateway, title, rows, index,
            person_1_name=PERSON_1_NAME,
            person_2_name=PERSON_2_NAME,
            method=method,
        )

        renamed = None
        wanted = footer.settled_title(title) if settle else footer.unsettled_title(title)
        if wanted != title:
            gateway.rename_worksheet(title, wanted)
            renamed = wanted

        sync_records(gateway, period)

        return {
            "published": True,
            "worksheet": renamed or title,
            "renamed": renamed,
            "line": written.sentence,
            "net": float(written.net),
        }
    except Exception as e:
        logger.warning(f"[settlement] {period} publish failed: {e}")
        return {"published": False, "reason": "Could not write to the spreadsheet."}


def sheet_is_settled(period: str) -> bool:
    """Whether the month's tab already carries the ``- PIF`` suffix."""
    from sheet_sync import service, worksheet

    try:
        gateway = service.build_gateway()
        title = worksheet.find_worksheet(gateway, period)
        return bool(title and worksheet.is_settled_title(title))
    except Exception as e:
        # Fails open so a Sheets outage can't block a settlement, but the
        # duplicate-payment guard is weaker while this is happening — say so.
        logger.warning(f"[settlement] {period} settled-title check failed: {e}")
        return False


def _peer_user_id() -> Optional[str]:
    from db import identity_repo

    peers = identity_repo.list_peers()
    return peers[0]["user_id"] if peers else None


def settled_periods() -> List[str]:
    return period_settlements_repo.settled_periods()


def sync_records(gateway, period: str) -> None:
    """Exchange settlement positions for ``period`` through the ``_sync`` tab.

    Pull first, then push, so a cycle that fails midway leaves the peer's
    position recorded rather than lost. Never raises: a settlement is
    bookkeeping about a month, and losing a sync of it must not fail the sync
    of the month's actual rows.
    """
    from sheet_sync import sync_sheet

    try:
        me = identity_service.ensure_identity()
        for record in sync_sheet.read_period_records(gateway):
            if record["period"] != period or record["user_id"] == me["user_id"]:
                continue
            period_settlements_repo.upsert(
                record["period"],
                record["user_id"],
                ready_at=record["ready_at"],
                closed_at=record["closed_at"],
                net_amount=record["net_amount"],
                debtor_user_id=record["debtor_user_id"],
                pif_at=record["pif_at"],
                pif_note=record["pif_note"],
            )

        mine = period_settlements_repo.get(period, me["user_id"])
        if mine:
            sync_sheet.write_period_record(
                gateway, {**mine, "display_name": me["display_name"]}
            )
    except Exception as e:
        logger.warning(f"[settlement] {period} record exchange failed: {e}")
