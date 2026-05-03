"""Dashboard layout persistence — stores user's drag-and-drop grid layout.

Single-row JSON store (key: "default") holding the layout array and the
list of hidden card IDs. Reuses the existing ``json_stores`` table via
``PgStore`` so no new migration is required.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from store import PgStore

router = APIRouter()

_layout_store = PgStore("dashboard_layout", "dashboard-layout")
_LAYOUT_KEY = "default"


class LayoutItem(BaseModel):
    i: str
    x: int
    y: int
    w: int
    h: int
    minW: Optional[int] = None
    minH: Optional[int] = None


class DashboardLayout(BaseModel):
    layout: List[LayoutItem]
    hidden: List[str] = []


@router.get("/dashboard/layout")
async def get_layout() -> Dict[str, Any]:
    """Return saved layout, or empty payload if none — UI applies its own default."""
    try:
        saved = _layout_store[_LAYOUT_KEY]
    except KeyError:
        return {"layout": [], "hidden": []}
    return {
        "layout": saved.get("layout", []),
        "hidden": saved.get("hidden", []),
    }


@router.put("/dashboard/layout")
async def save_layout(payload: DashboardLayout) -> Dict[str, Any]:
    _layout_store[_LAYOUT_KEY] = {
        "layout": [item.model_dump() for item in payload.layout],
        "hidden": payload.hidden,
    }
    return {"ok": True}


@router.delete("/dashboard/layout", status_code=204)
async def reset_layout() -> None:
    """Drop saved layout so the UI falls back to its default."""
    try:
        del _layout_store[_LAYOUT_KEY]
    except KeyError:
        pass
