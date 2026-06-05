"""REST surface for Fin's user-facts memory.

Backs the "Things Fin remembers" UI panel in the Advisor tab. Facts the
agent proposed via the ``remember_about_user`` tool land here with
``status='proposed'`` and stay quiet until the user confirms them.

The router is intentionally thin — every endpoint is one repo call. The
embedding lifecycle is handled by ``embeddings.embed_pending_user_facts``;
scheduled as a background task after writes so retrieval works the
moment the user confirms a fact.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response
from pydantic import BaseModel, Field

from db import user_facts_repo
from embeddings import embed_pending_user_facts

router = APIRouter()


class UserFactIn(BaseModel):
    fact: str = Field(..., min_length=1)
    category: str
    tags: List[str] = Field(default_factory=list)
    sensitive: bool = False


class UserFactPatch(BaseModel):
    fact: Optional[str] = None
    tags: Optional[List[str]] = None
    sensitive: Optional[bool] = None
    confidence: Optional[float] = None


@router.get("/user-facts")
async def list_user_facts(
    status: Optional[str] = None,
    category: Optional[str] = None,
) -> List[dict]:
    """List facts, optionally filtered by status and/or category."""
    return user_facts_repo.list_facts(status=status, category=category)


@router.post("/user-facts", status_code=201)
async def create_user_fact(req: UserFactIn, background_tasks: BackgroundTasks) -> dict:
    """Manually add a fact. Lands as 'confirmed' since the user typed it."""
    try:
        row = user_facts_repo.create_fact(
            fact=req.fact.strip(),
            category=req.category,
            tags=req.tags,
            sensitive=req.sensitive,
            status="confirmed",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    background_tasks.add_task(embed_pending_user_facts)
    return row


@router.put("/user-facts/{fact_id}")
async def update_user_fact(
    fact_id: int, req: UserFactPatch, background_tasks: BackgroundTasks
) -> dict:
    """Edit the fact text / tags / sensitive flag / confidence."""
    row = user_facts_repo.update_fact(
        fact_id,
        fact=req.fact,
        tags=req.tags,
        sensitive=req.sensitive,
        confidence=req.confidence,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Fact not found")
    # Re-embed only when the text changed (tags/sensitive don't affect vector).
    if req.fact is not None:
        # Drop the existing embedding so embed_pending sees this row as missing.
        from sqlalchemy import text as _sql
        from db.base import sync_engine
        with sync_engine.begin() as conn:
            conn.execute(
                _sql("DELETE FROM user_fact_embeddings WHERE fact_id = :id"),
                {"id": fact_id},
            )
        background_tasks.add_task(embed_pending_user_facts)
    return row


@router.post("/user-facts/{fact_id}/confirm")
async def confirm_user_fact(fact_id: int, background_tasks: BackgroundTasks) -> dict:
    row = user_facts_repo.set_status(fact_id, "confirmed")
    if row is None:
        raise HTTPException(status_code=404, detail="Fact not found")
    background_tasks.add_task(embed_pending_user_facts)
    return row


@router.post("/user-facts/{fact_id}/reject")
async def reject_user_fact(fact_id: int) -> dict:
    row = user_facts_repo.set_status(fact_id, "rejected")
    if row is None:
        raise HTTPException(status_code=404, detail="Fact not found")
    return row


@router.delete("/user-facts/{fact_id}", status_code=204, response_class=Response)
async def delete_user_fact(fact_id: int):
    if not user_facts_repo.delete_fact(fact_id):
        raise HTTPException(status_code=404, detail="Fact not found")
    return Response(status_code=204)
