"""Seed-recommendation routes — runtime-editable curated reading list.

Defaults ship in JSON; users add/remove via these endpoints.  Adding a
custom seed auto-allowlists its host so the URL fetcher will accept
imports from that host immediately.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import seed_loader

router = APIRouter()


class SeedIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=8, max_length=2000)
    scope: str
    category: str
    why: str = ""
    group_label: str = "Custom"
    manual_only: bool = False


class Seed(BaseModel):
    id: str
    title: str
    url: str
    scope: str
    category: str
    why: str
    group_label: str
    manual_only: bool
    is_custom: bool


class SeedGroup(BaseModel):
    label: str
    hint: str
    note: Optional[str] = None
    seeds: list[Seed]


@router.get("/seeds", response_model=list[SeedGroup])
async def list_seeds() -> list[dict[str, Any]]:
    """Return the merged seed list (defaults minus removed, plus customs)."""
    return seed_loader.list_seed_groups()


@router.get("/seeds/hidden", response_model=list[Seed])
async def list_hidden() -> list[dict[str, Any]]:
    """Return defaults the user has hidden.  Powers the UI's expandable
    "Hidden defaults" section so individual entries can be restored."""
    return seed_loader.list_hidden_defaults()


@router.post("/seeds", response_model=Seed, status_code=201)
async def add_seed(req: SeedIn) -> dict[str, Any]:
    """Add a custom seed.  Auto-allowlists the URL's host."""
    if req.scope not in {"external", "personal"}:
        raise HTTPException(
            status_code=422,
            detail="scope must be 'external' or 'personal'",
        )
    try:
        new_id = seed_loader.add_custom_seed(
            title=req.title.strip(),
            url=req.url.strip(),
            scope=req.scope,
            category=req.category.strip(),
            why=req.why.strip(),
            group_label=req.group_label.strip() or "Custom",
            manual_only=req.manual_only,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return {
        "id": f"c:{new_id}",
        "title": req.title.strip(),
        "url": req.url.strip(),
        "scope": req.scope,
        "category": req.category.strip(),
        "why": req.why.strip(),
        "group_label": req.group_label.strip() or "Custom",
        "manual_only": req.manual_only,
        "is_custom": True,
    }


@router.delete("/seeds/{seed_id}", status_code=204)
async def delete_seed(seed_id: str):
    """Remove a seed.  ``d:...`` ids hide a default; ``c:<n>`` deletes a custom."""
    ok = seed_loader.remove_seed(seed_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Seed not found")


@router.post("/seeds/restore/{default_id}", status_code=204)
async def restore_default(default_id: str):
    """Un-hide a previously-removed default."""
    ok = seed_loader.restore_default(default_id)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail="Default not found or wasn't hidden",
        )
