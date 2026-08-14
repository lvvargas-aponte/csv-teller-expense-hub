"""Weekly digest routes — lazily generated, stored, marked read.

No scheduler: ``GET /digest/latest`` regenerates when the newest stored
digest is older than 7 days (or missing), so the digest is always at most
a week stale the moment anyone looks at it.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from db import digests_repo
from digest import build_digest

logger = logging.getLogger(__name__)
router = APIRouter()

_REGENERATE_AFTER = timedelta(days=7)


def _is_stale(row: Dict[str, Any]) -> bool:
    generated = datetime.fromisoformat(row["generated_at"])
    return datetime.now(timezone.utc) - generated >= _REGENERATE_AFTER


@router.get("/digest/latest")
async def latest_digest(force: bool = False) -> Dict[str, Any]:
    row = digests_repo.latest()
    if force or row is None or _is_stale(row):
        payload = await build_digest()
        row = digests_repo.insert(payload)
    return row


@router.post("/digest/{digest_id}/read", status_code=204)
async def mark_digest_read(digest_id: int) -> None:
    if not digests_repo.mark_read(digest_id):
        raise HTTPException(status_code=404, detail="Digest not found")