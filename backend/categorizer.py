"""LLM-backed category suggester.

Used by the ``POST /api/transactions/{id}/suggest-category`` endpoint to
recommend a category for a transaction the user is about to review. The
allowed list is the union of a built-in default set and the user's
configured budget categories, so suggestions always land in a bucket the
rest of the app already understands.

Design choices:

* **Closed-world prompt** — the LLM is told "reply with ONLY one of: ...".
  If it returns anything outside the list, we drop it and return ``None``.
  Keeps spelling / case consistent across the aggregate downstream.
* **Single-shot via ``ask_ollama``** — no conversation context needed; one
  merchant → one label. Mirrors the cheapest possible Ollama call shape.
* **Graceful degrade** — Ollama unreachable → endpoint still returns 200
  with ``ai_available=false`` and the client decides whether to show a
  "service unavailable" hint; the transaction isn't mutated either way.
"""
from __future__ import annotations

from typing import List, Optional

import state
from llm_client import ask_ollama

DEFAULT_CATEGORIES: List[str] = [
    "Groceries",
    "Dining",
    "Gas",
    "Utilities",
    "Rent",
    "Subscriptions",
    "Health",
    "Travel",
    "Shopping",
    "Entertainment",
    "Transport",
    "Insurance",
    "Income",
    "Fees",
    "Other",
]


def known_categories() -> List[str]:
    """Return the union of default categories + user's budget categories.

    Dedup is case-insensitive, preserving the casing of whichever entry
    is seen first. Budget-defined categories take precedence so the
    user's naming wins over the defaults.
    """
    seen_lower: dict[str, str] = {}
    budget_categories = list(state.budgets.keys()) if state.budgets else []
    for name in budget_categories + DEFAULT_CATEGORIES:
        key = (name or "").strip()
        if not key:
            continue
        if key.lower() not in seen_lower:
            seen_lower[key.lower()] = key
    return list(seen_lower.values())


def _build_prompt(description: str, amount: float, known: List[str]) -> str:
    """Format the single-shot categorization prompt."""
    amount_str = f"${amount:.2f}" if amount >= 0 else f"-${abs(amount):.2f}"
    listing = ", ".join(known)
    return (
        "You categorize personal-finance transactions.\n"
        f"Allowed categories: {listing}\n\n"
        f"Transaction: {description}\n"
        f"Amount: {amount_str}\n\n"
        "Reply with ONLY the single best-matching category name from the allowed "
        "list above, exactly as written. If no category fits, reply with the "
        "single word NONE. Do not add any other text."
    )


def _parse_response(raw: Optional[str], known: List[str]) -> Optional[str]:
    """Map LLM text back to a known category; return ``None`` if invalid.

    Tolerates surrounding whitespace and punctuation the model may add.
    Case-insensitive match, returns the canonical casing from ``known``.
    """
    if not raw:
        return None
    cleaned = raw.strip().strip(".").strip()
    if not cleaned or cleaned.upper() == "NONE":
        return None
    by_lower = {k.lower(): k for k in known}
    return by_lower.get(cleaned.lower())


async def suggest_category(
    description: str,
    amount: float,
    known: Optional[List[str]] = None,
) -> dict:
    """Ask Ollama for a category suggestion.

    Returns ``{"category": str|None, "ai_available": bool, "candidates": list[str]}``.
    ``candidates`` is the same list the LLM was constrained to, so the
    client can also show it as a datalist for manual entry.
    """
    candidates = known if known is not None else known_categories()
    if not candidates:
        return {"category": None, "ai_available": False, "candidates": []}

    prompt = _build_prompt(description, amount, candidates)
    result = await ask_ollama(prompt)
    if not result["ai_available"]:
        return {"category": None, "ai_available": False, "candidates": candidates}

    picked = _parse_response(result.get("text"), candidates)
    return {"category": picked, "ai_available": True, "candidates": candidates}
