"""Subscriptions review — detected recurring charges joined with the user's
keep/cancel/ignore decisions.

The detector (``analytics.detect_recurring_charges``) finds what repeats;
this router adds the judgment layer: which charges the user has blessed,
which they plan to cancel, and which need a (re-)review because they are
new or their price moved since the last decision.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import categories_service
from analytics import detect_recurring_charges, list_commitment_candidates
from db import merchant_aliases_repo, subscriptions_repo

router = APIRouter()

# A price move beyond this (either direction) since the last review
# resurfaces the merchant in the "needs review" queue.
_PRICE_REPROMPT_PCT = 10.0

# Overlap is flagged in the categories where 2+ concurrent subscriptions
# usually mean something to consolidate (two streaming services, two music
# apps) — the same ``subscription`` role the detector routes on, read from
# the category rows rather than repeated here.


class ReviewRequest(BaseModel):
    decision: str  # keep | cancel | ignore
    # Optional answers to the two questions the detector cannot settle on its
    # own: how often this bills, and what kind of commitment it is. Omitted
    # leaves any previous answer in place.
    declared_cadence: Optional[str] = None
    declared_type: Optional[str] = None


class MergeRequest(BaseModel):
    into: str  # the canonical merchant_key this one is folded into


def _price_change_since_review(
    entry: Dict[str, Any], review: Optional[Dict[str, Any]]
) -> Optional[float]:
    if not review or not review.get("reviewed_amount"):
        return None
    baseline = float(review["reviewed_amount"])
    if baseline <= 0:
        return None
    return round((entry["latest_amount"] - baseline) / baseline * 100.0, 1)


def _open_question(entry: Dict[str, Any], review: Optional[Dict[str, Any]]) -> Optional[str]:
    """The question the detector cannot answer for this merchant, if any.

    Two cases the heuristic genuinely cannot settle, and guessing at either
    one is what put dead charges and mis-priced renewals on the list:

    * an ``irregular`` cadence — two charges 45 days apart are either an
      annual renewal seen twice, an erratic bill, or a coincidence;
    * a merchant that has gone quiet past its own billing interval — either
      it ended, or it bills less often than we think.

    Answered once (``declared_cadence`` set, or the row dismissed as
    ``ignore``) the question stops being asked.
    """
    if review and review.get("declared_cadence"):
        return None
    if review and review.get("decision") == "ignore":
        return None
    if entry.get("cadence") == "irregular":
        return "cadence"
    if entry.get("status") in ("overdue", "dormant"):
        return "still_active"
    return None


@router.get("/subscriptions")
async def list_subscriptions() -> Dict[str, Any]:
    # Bills and plain recurring spend repeat too, but neither is something a
    # user reviews for cancellation — the detector separates them for us.
    detected = [
        e for e in detect_recurring_charges()
        if e.get("commitment_type") == "subscription"
    ]
    reviews = subscriptions_repo.list_reviews()

    # Overlap: 2+ non-dismissed recurring charges sharing a subscription-ish
    # category.
    overlap_categories = categories_service.names_with_role(
        categories_service.SUBSCRIPTION
    )
    by_category: Dict[str, List[str]] = {}
    for entry in detected:
        cat = (entry["category"] or "").strip().lower()
        if cat not in overlap_categories:
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
    dormant: List[Dict[str, Any]] = []
    active_monthly = 0.0
    cancel_monthly = 0.0
    needs_review_count = 0
    for entry in detected:
        review = reviews.get(entry["merchant_key"])
        change_pct = _price_change_since_review(entry, review)
        is_dormant = entry.get("status") == "dormant"
        question = _open_question(entry, review)
        needs_review = review is None or question is not None or (
            change_pct is not None and abs(change_pct) >= _PRICE_REPROMPT_PCT
        )
        decision = review["decision"] if review else None

        if decision == "ignore":
            needs_review = False
        elif decision == "cancel":
            cancel_monthly += entry["estimated_monthly_cost"]
        elif not is_dormant:
            # A merchant that stopped billing is not part of what you spend
            # each month, whatever it once cost.
            active_monthly += entry["estimated_monthly_cost"]

        row = {
            **entry,
            "review": review,
            "needs_review": needs_review,
            "open_question": question,
            "price_change_since_review_pct": change_pct,
            "overlap_group": overlap_keys.get(entry["merchant_key"]),
        }
        if is_dormant:
            dormant.append(row)
        else:
            if needs_review:
                needs_review_count += 1
            subscriptions.append(row)

    # Surface the review queue first, biggest spend on top within each group.
    subscriptions.sort(
        key=lambda s: (not s["needs_review"], -s["estimated_monthly_cost"])
    )
    dormant.sort(key=lambda s: s["last_seen"], reverse=True)
    return {
        "subscriptions": subscriptions,
        "dormant": dormant,
        "summary": {
            "active_monthly_cost": round(active_monthly, 2),
            "cancel_monthly_savings": round(cancel_monthly, 2),
            "needs_review_count": needs_review_count,
            "dormant_count": len(dormant),
            "as_of": detected[0].get("as_of") if detected else None,
        },
    }


@router.get("/subscriptions/candidates")
async def list_candidates(limit: int = 60) -> Dict[str, Any]:
    """Merchants available to declare as a commitment — see
    ``analytics.list_commitment_candidates``. Declaring one is a POST to the
    same review endpoint with a ``declared_cadence``.
    """
    return {"candidates": list_commitment_candidates(max(1, min(200, int(limit))))}


@router.post("/subscriptions/{merchant_key}/review")
async def review_subscription(merchant_key: str, req: ReviewRequest) -> Dict[str, Any]:
    if req.decision not in subscriptions_repo.VALID_DECISIONS:
        raise HTTPException(
            status_code=422,
            detail=f"decision must be one of {subscriptions_repo.VALID_DECISIONS}",
        )
    if req.declared_cadence is not None and (
        req.declared_cadence not in subscriptions_repo.VALID_CADENCES
    ):
        raise HTTPException(
            status_code=422,
            detail=f"declared_cadence must be one of {subscriptions_repo.VALID_CADENCES}",
        )
    if req.declared_type is not None and (
        req.declared_type not in subscriptions_repo.VALID_TYPES
    ):
        raise HTTPException(
            status_code=422,
            detail=f"declared_type must be one of {subscriptions_repo.VALID_TYPES}",
        )
    entry = next(
        (e for e in detect_recurring_charges() if e["merchant_key"] == merchant_key),
        None,
    )
    review = subscriptions_repo.upsert_review(
        merchant_key,
        req.decision,
        reviewed_amount=entry["latest_amount"] if entry else None,
        declared_cadence=req.declared_cadence,
        declared_type=req.declared_type,
    )
    return {"review": review}


@router.post("/subscriptions/{merchant_key}/merge")
async def merge_merchant(merchant_key: str, req: MergeRequest) -> Dict[str, Any]:
    """Fold ``merchant_key`` into ``req.into``.

    The two keys' transactions group as one merchant from here on, so a
    service that renamed itself keeps a single history instead of appearing
    twice with half of it each.
    """
    try:
        alias = merchant_aliases_repo.upsert_alias(merchant_key, req.into)
    except ValueError as e:
        # The repository raises this deliberately with a message written for
        # the user ("'a' is itself an alias of 'b'; merge into that instead"),
        # so it is forwarded rather than replaced — it names the fix.
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"alias": alias}


@router.delete("/subscriptions/{merchant_key}/merge", status_code=204)
async def unmerge_merchant(merchant_key: str) -> None:
    if not merchant_aliases_repo.delete_alias(merchant_key):
        raise HTTPException(status_code=404, detail="That merchant is not merged")


@router.delete("/subscriptions/{merchant_key}/review", status_code=204)
async def clear_subscription_review(merchant_key: str) -> None:
    if not subscriptions_repo.delete_review(merchant_key):
        raise HTTPException(status_code=404, detail="No review for that merchant")