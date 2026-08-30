"""Category-rule routes — the user's merchant→category matching list.

Thin: ordering, matching, and validation all live in
``backend/category_rules.py``, which is also what the categorizer calls.
"""
from typing import List

from fastapi import APIRouter

import category_rules as rules_service
from models import CategoryRule, CategoryRulesReplace

router = APIRouter()


@router.get("/category-rules", response_model=List[CategoryRule])
async def list_category_rules() -> List[dict]:
    """Return the rules in evaluation order (first match wins)."""
    return rules_service.list_rules()


@router.put("/category-rules", response_model=List[CategoryRule])
async def replace_category_rules(req: CategoryRulesReplace) -> List[dict]:
    """Replace the whole ordered list.

    Whole-list rather than per-row because the settings page saves every
    edit, reorder, and deletion together — they have to land atomically
    or the surviving order is nonsense. Blank rows are dropped server-side.
    """
    return rules_service.replace_all([r.model_dump() for r in req.rules])
