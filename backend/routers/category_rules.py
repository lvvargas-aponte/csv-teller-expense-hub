"""Category-rule routes — CRUD plus a backfill over existing transactions.

The engine itself lives in ``category_rules.py``; this module is the HTTP
surface. Creating a rule deliberately does *not* touch stored transactions:
the client calls ``POST /category-rules/apply`` with ``mode="preview"`` and
shows the user what would change before anything is written. Silently
relabelling history as a side effect of saving a rule is the one behaviour
that would make the feature untrustworthy.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

import category_rules as rules_engine
import state
from models import ApplyCategoryRulesRequest, CategoryRule, CategoryRuleIn

router = APIRouter()


def _validate(req: CategoryRuleIn) -> None:
    if not req.value.strip():
        raise HTTPException(status_code=422, detail="Match value must not be empty")
    if not req.category.strip():
        raise HTTPException(status_code=422, detail="Category must not be empty")
    if req.amount is not None and req.amount <= 0:
        raise HTTPException(
            status_code=422,
            detail="amount must be > 0 (magnitude only — direction comes from transaction_type)",
        )


def _record(rule_id: str, req: CategoryRuleIn, created: str) -> Dict[str, Any]:
    return {
        "id":               rule_id,
        "match":            req.match,
        "value":            req.value.strip(),
        "category":         req.category.strip(),
        # Rounded to cents so a float typed into the form matches the
        # two-decimal amounts transactions actually carry.
        "amount":           None if req.amount is None else round(float(req.amount), 2),
        "transaction_type": req.transaction_type,
        "enabled":          req.enabled,
        "notes":            req.notes,
        "created":          created,
        "updated":          rules_engine._now_iso(),
    }


@router.get("/category-rules", response_model=List[CategoryRule])
async def list_category_rules():
    """All rules in evaluation order (most specific first)."""
    return rules_engine.list_rules()


@router.post("/category-rules", response_model=CategoryRule, status_code=201)
async def create_category_rule(req: CategoryRuleIn):
    """Add a rule. Applies to future imports; use /apply for existing rows."""
    _validate(req)
    rule_id = rules_engine.new_rule_id()
    record = _record(rule_id, req, rules_engine._now_iso())
    state.category_rules[rule_id] = record
    state._category_rules_store.save()
    return record


@router.put("/category-rules/{rule_id}", response_model=CategoryRule)
async def update_category_rule(rule_id: str, req: CategoryRuleIn):
    """Replace a rule in place — preserves its created timestamp."""
    if rule_id not in state.category_rules:
        raise HTTPException(status_code=404, detail="Rule not found")
    _validate(req)
    existing = state.category_rules[rule_id]
    record = _record(rule_id, req, existing.get("created") or rules_engine._now_iso())
    state.category_rules[rule_id] = record
    state._category_rules_store.save()
    return record


@router.delete("/category-rules/{rule_id}", status_code=204)
async def delete_category_rule(rule_id: str):
    """Remove a rule. Categories it already assigned stay as they are."""
    if rule_id not in state.category_rules:
        raise HTTPException(status_code=404, detail="Rule not found")
    del state.category_rules[rule_id]
    state._category_rules_store.save()


@router.post("/category-rules/apply")
async def apply_category_rules(req: ApplyCategoryRulesRequest) -> Dict[str, Any]:
    """Run the rules over transactions already in the store.

    ``mode="preview"`` writes nothing. ``overwrite=false`` skips any
    transaction that already has a category.
    """
    if req.rule_id and req.rule_id not in state.category_rules:
        raise HTTPException(status_code=404, detail="Rule not found")
    result = rules_engine.apply_to_stored(
        rule_id=req.rule_id,
        overwrite=req.overwrite,
        dry_run=(req.mode == "preview"),
    )
    result["mode"] = req.mode
    return result
