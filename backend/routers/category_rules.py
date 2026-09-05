"""Category-rule routes — the user's merchant→category matching list.

Thin: ordering, matching and validation live in ``backend/category_rules.py``,
which is also what the categorizer calls; sweeping a rule over transactions
already imported lives in ``backend/categorization_service.py``, which owns
the precedence that makes the sweep safe.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

import categorization_service
import category_rules as rules_service
from models import (
    CategoryRule,
    CategoryRuleCreate,
    CategoryRulePatch,
    CategoryRulesReplace,
    RulePreviewRequest,
)

router = APIRouter()


@router.get("/category-rules", response_model=List[CategoryRule])
async def list_category_rules() -> List[dict]:
    """Return the rules in evaluation order (merchant rules first)."""
    return rules_service.list_rules()


@router.put("/category-rules", response_model=List[CategoryRule])
async def replace_category_rules(req: CategoryRulesReplace) -> List[dict]:
    """Replace the settings form's substring rules as one list.

    Whole-list rather than per-row because the form saves every edit,
    reorder and deletion together — they have to land atomically or the
    surviving order is nonsense. Blank rows are dropped server-side, and
    merchant rules are untouched: the form does not show them, so it does
    not get to delete them.
    """
    return rules_service.replace_all([r.model_dump() for r in req.rules])


@router.post("/category-rules", response_model=Dict[str, Any])
async def create_category_rule(req: CategoryRuleCreate) -> Dict[str, Any]:
    """Create one rule, optionally sweeping the transactions already imported.

    This is what "always categorize CHIPOTLE as Dining" posts. Re-stating a
    merchant you already have a rule for updates it rather than failing —
    the most recent statement is the one you mean.
    """
    try:
        rule = rules_service.create_rule(req.pattern, req.category, req.kind)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if rule is None:
        raise HTTPException(
            status_code=422, detail="A rule needs both a pattern and a category."
        )

    applied = None
    if req.apply_to_existing:
        applied = categorization_service.apply_rule(rule)

    return {"rule": rule, "applied": applied}


@router.post("/category-rules/preview", response_model=Dict[str, Any])
async def preview_category_rule(req: RulePreviewRequest) -> Dict[str, Any]:
    """What a rule would do to existing transactions, without writing.

    ``claimable`` is the number worth showing the user: ``matched`` minus
    the rows a higher source already owns.
    """
    return categorization_service.preview_rule(
        {"kind": req.kind, "pattern": req.pattern, "category": req.category,
         "enabled": True}
    )


@router.patch("/category-rules/{rule_id}", response_model=CategoryRule)
async def patch_category_rule(rule_id: int, req: CategoryRulePatch) -> dict:
    """Edit one rule in place — rename, recategorize, enable or reorder."""
    rule = rules_service.update_rule(rule_id, **req.model_dump())
    if rule is None:
        raise HTTPException(status_code=404, detail=f"No rule with id {rule_id}.")
    return rule


@router.delete("/category-rules/{rule_id}")
async def delete_category_rule(rule_id: int) -> Dict[str, Any]:
    """Remove one rule. Categories it already set are left alone."""
    if not rules_service.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail=f"No rule with id {rule_id}.")
    return {"deleted": rule_id}


@router.post("/category-rules/{rule_id}/apply", response_model=Dict[str, Any])
async def apply_category_rule(rule_id: int) -> Dict[str, Any]:
    """Sweep an existing rule over the transactions already imported."""
    rule = rules_service.get_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"No rule with id {rule_id}.")
    return categorization_service.apply_rule(rule)


@router.get("/category-rules/for-merchant", response_model=Dict[str, Any])
async def rule_for_merchant(description: str) -> Dict[str, Any]:
    """The merchant key for ``description``, and any rule already on it.

    The client asks this after you categorize a row, to decide whether the
    "always categorize…" prompt is worth showing.
    """
    import merchant_key

    key = merchant_key.canonical(description)
    return {
        "merchant_key": key,
        "rule": rules_service.find_by_merchant(key) if key else None,
    }
