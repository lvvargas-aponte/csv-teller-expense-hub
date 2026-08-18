"""Shared-expense sync routes — the manual trigger and its status.

There is no background poll: sync writes to a spreadsheet holding years of
settled financial records, so a cycle happens when a person asks for one.
"""
import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from db import sync_state_repo
from sheet_sync import service, worksheet

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


@router.post("/sync/shared")
async def sync_shared(req: Optional[SyncRequest] = None):
    """Run one sync cycle. Refusals return 200 with an explanation."""
    req = req or SyncRequest()

    if req.period and req.period < worksheet.CUTOVER_PERIOD:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{req.period} is before the {worksheet.CUTOVER_PERIOD} cutover. "
                "Earlier months are hand-maintained and are never touched by sync."
            ),
        )

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


@router.get("/sync/status")
async def sync_status():
    return service.status()


@router.post("/sync/corrections/{correction_id}/acknowledge")
async def acknowledge_correction(correction_id: int):
    if not sync_state_repo.acknowledge(correction_id):
        raise HTTPException(status_code=404, detail="No open correction with that id")
    return {"acknowledged": True}
