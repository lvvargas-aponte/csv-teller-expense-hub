"""Shared-expense sync routes — the manual trigger and its status.

There is no background poll: sync writes to a spreadsheet holding years of
settled financial records, so a cycle happens when a person asks for one.
"""
import logging
import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator

import identity_service
from db import peer_transactions_repo, sync_state_repo
from sheet_sync import service, settlement, shared_view, worksheet

logger = logging.getLogger(__name__)
router = APIRouter()

_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class SyncRequest(BaseModel):
    period: Optional[str] = None
    dry_run: bool = False

    @field_validator("period")
    @classmethod
    def _well_formed(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _PERIOD_RE.match(v):
            raise ValueError("period must be YYYY-MM")
        return v


def _reject_before_cutover(period: str) -> None:
    if period < worksheet.CUTOVER_PERIOD:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{period} is before the {worksheet.CUTOVER_PERIOD} cutover. "
                "Earlier months are hand-maintained and are never touched by sync."
            ),
        )


def _validate_period(period: str) -> None:
    """Well-formed, and inside the range sync is allowed to touch."""
    if not _PERIOD_RE.match(period):
        raise HTTPException(status_code=422, detail="period must be YYYY-MM")
    _reject_before_cutover(period)


@router.post("/sync/shared")
async def sync_shared(req: Optional[SyncRequest] = None):
    """Run one sync cycle. Refusals return 200 with an explanation."""
    req = req or SyncRequest()

    if req.period:
        _reject_before_cutover(req.period)

    try:
        gateway = service.build_gateway()
    except service.SyncDisabled as e:
        raise HTTPException(status_code=503, detail=str(e))

    results = service.sync_all(
        gateway,
        periods=[req.period] if req.period else None,
        dry_run=req.dry_run,
    )

    statuses = {r.status for r in results}
    overall = "error" if "error" in statuses else "refused" if "refused" in statuses else "ok"
    return {"status": overall, "results": [r.as_dict() for r in results]}


@router.get("/sync/shared-rows")
async def shared_rows(period: str = Query(..., pattern=_PERIOD_RE.pattern)):
    _reject_before_cutover(period)
    return shared_view.shared_rows(period)


@router.get("/sync/status")
async def sync_status():
    return service.status()


class PaidRequest(BaseModel):
    note: Optional[str] = None


def _settlement_state(period: str, block: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The period's position, recomputed from the rows as they stand now.

    ``block`` lets a handler that already projected the month reuse that work:
    marking a period ready or paid changes the settlement *records*, never the
    rows they were computed from, so only ``describe`` has to run again.
    """
    if block is None:
        block = shared_view.shared_rows(period)["settlement"]
    return {
        "settlement": block,
        "settlement_state": settlement.describe(period, block),
    }


@router.post("/sync/periods/{period}/ready")
async def mark_period_ready(period: str) -> Dict[str, Any]:
    """Declare this instance's rows for ``period`` complete.

    Publishes the footer straight away rather than waiting for the next sync
    cycle: the point of saying "I'm done" is that the other person can see it.
    """
    _validate_period(period)
    block = shared_view.shared_rows(period)["settlement"]
    settlement.mark_ready(period, block)
    published = settlement.publish(period)
    return {**_settlement_state(period, block), "published": published}


@router.delete("/sync/periods/{period}/ready")
async def withdraw_period_ready(period: str) -> Dict[str, Any]:
    _validate_period(period)
    settlement.withdraw_ready(period)
    return _settlement_state(period)


@router.post("/sync/periods/{period}/paid")
async def mark_period_paid(period: str, req: Optional[PaidRequest] = None) -> Dict[str, Any]:
    """Declare ``period`` paid in full.

    Deliberately not gated on the peer agreeing, or on the two instances having
    computed the same net: settlement here is advisory, and the person who
    moved the money is the one who knows. A disagreement is reported on the
    page, not enforced here.
    """
    _validate_period(period)

    # Someone got here first — the peer's instance, or a hand-renamed tab.
    # Say so instead of overwriting their record with ours.
    already = settlement.who_settled(period)
    if already or settlement.sheet_is_settled(period):
        raise HTTPException(
            status_code=409,
            detail=(
                f"This sheet is already marked paid in full by {already}."
                if already
                else "This sheet is already marked paid in full."
            ),
        )

    note = req.note if req else None
    block = shared_view.shared_rows(period)["settlement"]
    settlement.mark_paid(period, block, note=note)
    published = settlement.publish(period, settle=True, method=note)
    return {**_settlement_state(period, block), "published": published}


@router.delete("/sync/periods/{period}/paid")
async def reopen_period(period: str) -> Dict[str, Any]:
    """Undo this instance's "paid in full". Only ever clears our own record."""
    _validate_period(period)
    settlement.reopen(period)
    # Drops the ``- PIF`` suffix again and refreshes the footer.
    published = settlement.publish(period)
    return {**_settlement_state(period), "published": published}


@router.post("/sync/corrections/{correction_id}/acknowledge")
async def acknowledge_correction(correction_id: int):
    if not sync_state_repo.acknowledge(correction_id):
        raise HTTPException(status_code=404, detail="No open correction with that id")
    return {"acknowledged": True}


class DisputeUpdate(BaseModel):
    flag: Optional[str] = None
    note: Optional[str] = None

    @field_validator("flag")
    @classmethod
    def _valid_flag(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("Y", "N"):
            raise ValueError("flag must be 'Y', 'N', or null")
        return v


@router.put("/sync/peer-rows/{txn_id}/dispute")
async def update_dispute(txn_id: str, update: DisputeUpdate):
    """Raise, edit or clear a dispute on a row this instance does not own.

    ``dispute_by`` always comes from our own identity, never the request body
    — who authored a dispute is not something a caller gets to assert.
    """
    me = identity_service.ensure_identity()
    if txn_id.startswith(f"{me['user_id']}:"):
        raise HTTPException(
            status_code=422,
            detail="Cannot dispute a row this instance owns.",
        )

    by = me["display_name"] if update.flag is not None else None
    note = update.note if update.flag is not None else None

    found = peer_transactions_repo.set_dispute(txn_id, update.flag, by, note)

    if not found:
        raise HTTPException(status_code=404, detail="No peer row with that id")

    return peer_transactions_repo.get(txn_id)
