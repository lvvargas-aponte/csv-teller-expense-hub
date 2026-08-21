"""Shared-expense sync routes — the manual trigger and its status.

There is no background poll: sync writes to a spreadsheet holding years of
settled financial records, so a cycle happens when a person asks for one.
"""
import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import DBAPIError

import identity_service
from db import peer_transactions_repo, sync_state_repo
from sheet_sync import service, shared_view, worksheet

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


@router.post("/sync/corrections/{correction_id}/acknowledge")
async def acknowledge_correction(correction_id: int):
    if not sync_state_repo.acknowledge(correction_id):
        raise HTTPException(status_code=404, detail="No open correction with that id")
    return {"acknowledged": True}


class DisputeUpdate(BaseModel):
    flag: Optional[str] = None
    note: str = ""


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

    try:
        found = peer_transactions_repo.set_dispute(txn_id, update.flag, by, note)
    except DBAPIError:
        raise HTTPException(status_code=422, detail="flag must be 'Y', 'N', or null")

    if not found:
        raise HTTPException(status_code=404, detail="No peer row with that id")

    return peer_transactions_repo.get(txn_id)
