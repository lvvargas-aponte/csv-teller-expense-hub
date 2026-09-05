"""Category routes — the label set as rows you can edit.

Thin: naming, merging and the role sets all live in
``backend/categories_service.py``, which is also what ``analytics`` reads to
decide whether a category marks a bill, a subscription, or money that never
left the household.

``GET /categories`` and ``DELETE /categories/{name}`` used to live in
``routers/transactions.py``; the paths are unchanged.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

import categories_service
from models import (
    CategoryCreate,
    CategoryMergeRequest,
    CategoryParentRequest,
    CategoryPatch,
    CategoryRenameRequest,
)

router = APIRouter()


@router.get("/categories")
async def list_categories(include_archived: bool = False) -> Dict[str, Any]:
    """Every category, with how many transactions carry each one.

    ``categories`` stays a bare list of names for the clients that only
    populate a picker with it; ``rows`` carries the editable detail.

    ``spend`` is the current calendar month per category, keyed by canonical
    name — a count alone doesn't say whether a category is worth the row it
    occupies. It reuses ``group_debit_spending``, so what counts as spending
    is the same gate the dashboard and the budgets use.
    """
    from datetime import date

    import analytics

    rows = categories_service.list_categories(include_archived=include_archived)
    today = date.today()
    month = analytics.group_debit_spending().get(
        f"{today.year:04d}-{today.month:02d}", {}
    )
    by_lower = {k.strip().lower(): v for k, v in month.items()}

    return {
        "categories": [c["name"] for c in rows],
        "counts": categories_service.counts(),
        "spend": {
            c["name"]: round(by_lower.get(c["name"].strip().lower(), 0.0), 2)
            for c in rows
        },
        "rows": rows,
        "roles": list(categories_service.ROLES),
    }


@router.post("/categories")
async def create_category(req: CategoryCreate) -> Dict[str, Any]:
    """Add a category. An existing name (any casing) is returned as-is."""
    try:
        row = categories_service.create(req.name, req.color, req.roles)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if row is None:
        raise HTTPException(status_code=422, detail="A category needs a name.")
    return row


@router.patch("/categories/{category_id}")
async def patch_category(category_id: int, req: CategoryPatch) -> Dict[str, Any]:
    """Change colour, roles, sort or archived state. Renaming has its own
    endpoint because it has to rewrite every reference."""
    try:
        row = categories_service.update(
            category_id,
            color=req.color,
            roles=req.roles,
            archived=req.archived,
            sort=req.sort,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"No category with id {category_id}."
        )
    return row


@router.post("/categories/{category_id}/rename")
async def rename_category(
    category_id: int, req: CategoryRenameRequest
) -> Dict[str, Any]:
    """Rename everywhere at once — transactions, budgets and rules.

    Renaming onto a name that already exists merges into it rather than
    failing, which is usually what was meant.
    """
    row = categories_service.rename(category_id, req.name)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No category with id {category_id}, or the new name was blank.",
        )
    return row


@router.post("/categories/{category_id}/merge")
async def merge_category(
    category_id: int, req: CategoryMergeRequest
) -> Dict[str, Any]:
    """Fold this category into another and delete it.

    Replaces editing ``category_normalizer.NORMALIZATION_MAP`` and
    redeploying. The survivor gains the union of both role sets.
    """
    row = categories_service.merge(category_id, req.into_id)
    if row is None:
        raise HTTPException(status_code=404, detail="One of those categories is gone.")
    return row


@router.post("/categories/{category_id}/parent")
async def set_category_parent(
    category_id: int, req: CategoryParentRequest
) -> Dict[str, Any]:
    """Group this category under a parent, or ungroup it with a null parent.

    One level deep. A category that already has children cannot be given a
    parent, and a parent cannot itself be nested — 422 rather than writing a
    tree that silently loses a level.
    """
    row = categories_service.set_parent(category_id, req.parent_id)
    if row is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Categories group one level deep: a parent cannot itself have "
                "a parent, and a category with children cannot be nested."
            ),
        )
    return row


@router.delete("/categories/id/{category_id}")
async def delete_category_by_id(category_id: int) -> Dict[str, Any]:
    """Delete a category and clear it from every transaction using it.

    Any budget under that name survives — it is a number the user set, and
    the category row never owned it. ``budget_exists`` says so.
    """
    result = categories_service.delete(category_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"No category with id {category_id}."
        )
    return result


@router.delete("/categories/{name}")
async def delete_category(name: str) -> Dict[str, Any]:
    """Delete by name — the shape the transactions table's category picker
    has always used."""
    target = (name or "").strip()
    if not target:
        raise HTTPException(status_code=422, detail="Category name is required.")
    row = categories_service.find_by_name(target)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No category named {name!r}.")
    return categories_service.delete(row["id"])


@router.get("/categories/roles")
async def list_roles() -> List[str]:
    """The role vocabulary, for building the editor's checkboxes."""
    return list(categories_service.ROLES)
