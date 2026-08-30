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

from typing import Any, Dict, List, Optional

import category_rules
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
    """Return the union of distinct transaction categories + user's budget
    categories + the built-in defaults.

    Priority (first occurrence wins, case-insensitive): transaction-assigned
    categories → budgets → defaults. This way the LLM suggester picks from
    the labels the user has actually used elsewhere before falling back to
    the seed list.
    """
    seen_lower: dict[str, str] = {}
    txn_categories = [
        (t.get("category") or "")
        for t in state.stored_transactions.values()
    ] if state.stored_transactions else []
    budget_categories = list(state.budgets.keys()) if state.budgets else []
    for name in txn_categories + budget_categories + DEFAULT_CATEGORIES:
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
    rules: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Suggest a category — user rules first, then Ollama.

    Returns ``{"category": str|None, "ai_available": bool, "source":
    "rule"|"ai"|None, "candidates": list[str]}``. ``candidates`` is the
    same list the LLM was constrained to, so the client can also show it
    as a datalist for manual entry.

    ``ai_available`` carries the same meaning as everywhere else in this
    codebase (see ``llm_client``): whether Ollama answered. It says nothing
    when the model was never consulted — ``source == "rule"`` is how a caller
    knows that happened, and must not read the flag as a health signal then.

    A matching rule short-circuits the model entirely: it's the answer
    the user wrote down, it costs no round-trip, and it still works with
    Ollama down. ``rules`` can be passed in so a bulk caller reads the table
    once instead of once per transaction.
    """
    candidates = known if known is not None else known_categories()

    ruled = category_rules.match(description, rules)
    if ruled:
        return {
            "category": ruled,
            "ai_available": False,
            "source": "rule",
            "candidates": candidates,
        }

    if not candidates:
        return {
            "category": None, "ai_available": False,
            "source": None, "candidates": [],
        }

    prompt = _build_prompt(description, amount, candidates)
    result = await ask_ollama(prompt)
    if not result["ai_available"]:
        return {
            "category": None, "ai_available": False,
            "source": None, "candidates": candidates,
        }

    picked = _parse_response(result.get("text"), candidates)
    return {
        "category": picked,
        "ai_available": True,
        "source": "ai" if picked else None,
        "candidates": candidates,
    }
