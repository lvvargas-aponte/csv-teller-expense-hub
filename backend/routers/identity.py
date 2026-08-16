"""Instance identity routes — who this instance is, and who it settles with."""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

import identity_service
from db import identity_repo

logger = logging.getLogger(__name__)
router = APIRouter()


class IdentityUpdate(BaseModel):
    display_name: str

    @field_validator("display_name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("display_name must not be blank")
        return v.strip()


@router.get("/identity")
async def get_identity():
    """Return this instance's identity and its peers, bootstrapping if needed."""
    try:
        me = identity_service.ensure_identity()
    except Exception as e:
        logger.error(f"Failed to resolve instance identity: {e}")
        raise HTTPException(status_code=500, detail="Failed to resolve instance identity")
    return {"me": me, "peers": identity_repo.list_peers()}


@router.put("/identity")
async def update_identity(update: IdentityUpdate):
    """Rename this instance's owner. The user id and person slot are immutable."""
    identity_service.ensure_identity()
    updated = identity_repo.rename_identity(update.display_name)
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to resolve instance identity")
    return updated
