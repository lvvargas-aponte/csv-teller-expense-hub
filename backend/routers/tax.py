"""Tax-awareness routes — thin reads over ``tax.py``.

No response models: both payloads are estimates that carry their own
assumptions and an ``available`` flag, and pinning the shape twice would only
let the two drift.
"""
from typing import Any, Dict

from fastapi import APIRouter

import tax

router = APIRouter()


@router.get("/tax/after-tax-net-worth")
async def get_after_tax_net_worth() -> Dict[str, Any]:
    """Net worth less the deferred tax on pre-tax balances.

    ``available: false`` whenever the household has not opted in or has not
    stated a marginal rate — the reason says which.
    """
    return await tax.after_tax_net_worth()
