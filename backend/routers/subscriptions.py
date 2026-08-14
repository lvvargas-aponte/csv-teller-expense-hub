"""Subscriptions review — detected recurring charges joined with the user's
keep/cancel/ignore decisions.

The detector (``analytics.detect_recurring_charges``) finds what repeats;
this router adds the judgment layer: which charges the user has blessed,
which they plan to cancel, and which need a (re-)review because they are
new or their price moved since the last decision.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from analytics import detect_recurring_charges
from db import subscriptions_repo

logger = logging.getLogger(__name__)
router = APIRouter()

# A price move beyond this (either direction) since the last review
# resurfaces the merchant in the "needs review" queue.
_PRICE_REPROMPT_PCT = 10.0

# Categories where 2+ concurrent subscriptions usually mean overlap the
# user may want to consolidate (two streaming services, two music apps).
_OVERLAP_CATEGORIES = frozenset({
    "entertainment",
    "subscription",
    "subscriptions",
    "streaming",
    "music",
})


class ReviewRequest(BaseModel):
    decision: str  # keep | cancel | ignore


def _price_change_since_review(
    entry: Dict[str, Any], review: Optional[Dict[str, Any]]
) -> Optional[float]:
    if not review or not review.get("reviewed_amount"):
        return None
    baseline = float(review["reviewed_amount"])
    if baseline <= 0:
        return None
    return round((entry["latest_amount"] - baseline) / baseline * 100.0, 1)


@router.get("/subscriptions")
async def list_subscriptions() -> Dict[str, Any]:
    detected = detect_recurring_charges()
    reviews = subscriptions_repo.list_reviews()

    # Overlap: 2+ non-dismissed recurring charges sharing a subscription-ish
    # category.
    by_category: Dict[str, List[str]] = {}
    for entry in detected:
        cat = (entry["category"] or "").strip().lower()
        if cat not in _OVERLAP_CATEGORIES:
            continue
        review = reviews.get(entry["merchant_key"])
        if review and review["decision"] in ("cancel", "ignore"):
            continue
        by_category.setdefault(cat, []).append(entry["merchant_key"])
    overlap_keys = {
        key: cat
        for cat, keys in by_category.items()
        if len(keys) >= 2
        for key in keys
    }

    subscriptions: List[Dict[str, Any]] = []
    active_monthly = 0.0
    cancel_monthly = 0.0
    needs_review_count = 0
    for entry in detected:
        review = reviews.get(entry["merchant_key"])
        change_pct = _price_change_since_review(entry, review)
        needs_review = review is None or (
            change_pct is not None and abs(change_pct) >= _PRICE_REPROMPT_PCT
        )
        decision = review["decision"] if review else None

        if decision == "ignore":
            needs_review = False
        elif decision == "cancel":
            cancel_monthly += entry["estimated_monthly_cost"]
        else:
            active_monthly += entry["estimated_monthly_cost"]
        if needs_review:
            needs_review_count += 1

        subscriptions.append({
            **entry,
            "review": review,
            "needs_review": needs_review,
            "price_change_since_review_pct": change_pct,
            "overlap_group": overlap_keys.get(entry["merchant_key"]),
        })

    # Surface the review queue first, biggest spend on top within each group.
    subscriptions.sort(
        key=lambda s: (not s["needs_review"], -s["estimated_monthly_cost"])
    )
    return {
        "subscriptions": subscriptions,
        "summary": {
            "active_monthly_cost": round(active_monthly, 2),
            "cancel_monthly_savings": round(cancel_monthly, 2),
            "needs_review_count": needs_review_count,
        },
    }


@router.post("/subscriptions/{merchant_key}/review")
async def review_subscription(merchant_key: str, req: ReviewRequest) -> Dict[str, Any]:
    if req.decision not in subscriptions_repo.VALID_DECISIONS:
        raise HTTPException(
            status_code=422,
            detail=f"decision must be one of {subscriptions_repo.VALID_DECISIONS}",
        )
    entry = next(
        (e for e in detect_recurring_charges() if e["merchant_key"] == merchant_key),
        None,
    )
    review = subscriptions_repo.upsert_review(
        merchant_key,
        req.decision,
        reviewed_amount=entry["latest_amount"] if entry else None,
    )
    return {"review": review}


@router.delete("/subscriptions/{merchant_key}/review", status_code=204)
async def clear_subscription_review(merchant_key: str) -> None:
    if not subscriptions_repo.delete_review(merchant_key):
        raise HTTPException(status_code=404, detail="No review for that merchant")