"""Single source of truth for transaction-category normalization.

Both the one-shot backfill script (``scripts/normalize_categories.py``)
and the live ingest paths (``csv_parser.py`` Discover rows,
``routers/simplefin.py`` detail reads) call ``normalize()`` so the canonical
label set stays consistent regardless of which bank reported the row.

Mapping rules:
- Exact entries in ``NORMALIZATION_MAP`` are applied verbatim (case-sensitive
  source keys; users approved these).
- Anything else falls through ``_fallback_titlecase`` — preserves whatever
  the bank reported but titlecases it so new labels stay readable instead
  of arriving as ``"groceries"`` / ``"GROCERIES"`` mixes.
- Empty / None / whitespace → ``None`` (caller decides how to surface
  "uncategorized").
"""
from __future__ import annotations

from typing import Optional


# Canonical mapping approved 2026-05-28. Keep both halves of any synonym
# pair (e.g. SelfHelp + Self Help) here so future ingest collisions resolve
# to the same canonical label.
NORMALIZATION_MAP: dict[str, str] = {
    # Pure case fixes
    "groceries": "Groceries",
    "shopping": "Shopping",
    "utilities": "Utilities",
    "general": "General",
    "service": "Service",
    "home maintenance": "Home Maintenance",
    # Typo
    "Car Maintenace": "Car Maintenance",
    # Spacing / form
    "FoodDeliveryService": "Food Delivery",
    "Travel/ Entertainment": "Travel",
    "Drinking": "Drinks",
    "SelfHelp": "Self Help",
    # Synonym merges (approved)
    "fuel": "Gas",
    "Restaurants": "Dining",
    "Supermarkets": "Groceries",
    "Merchandise": "Shopping",
}


# Approved canonical labels that don't need mapping (already in use).
# Listed here so the titlecase fallback doesn't mangle them ("Zelle To" →
# "Zelle to", "Gifts and Donations" → "Gifts And Donations"). Anything not
# in this set falls through ``_fallback_titlecase``.
KNOWN_CANONICAL_LABELS: frozenset[str] = frozenset({
    "CC Payment", "Dining", "Drinks", "Subscriptions", "Payroll", "Interest",
    "Zelle To", "Zelle From", "Gifts and Donations", "Travel", "Savings",
    "Mortgage", "Parking", "Furniture", "Payments and Credits",
    "Car Insurance", "Entertainment", "Gym Fees", "Eastern Medicine",
    "Coffee", "Health Care", "Pharmacy", "Car Payment", "Hotel", "Gas",
    "Check Deposit", "ATM Withdraw", "Fees", "Tax Service", "HOA",
    "Souvenir", "Self Care", "Self Help", "Insurance", "Groceries",
    "Shopping", "Utilities", "General", "Service", "Home Maintenance",
    "Car Maintenance", "Food Delivery", "Other",
})


_LOWERCASE_JOINERS = {"and", "of", "the", "to", "from", "or", "for", "in", "on", "a"}


def _fallback_titlecase(raw: str) -> str:
    """Titlecase tokens, preserving fully-uppercase short tokens (HOA, ATM, CC)
    and keeping common joiners ("and", "of", ...) lowercase when not the
    first word.

    ``str.title()`` would mangle "HOA" → "Hoa" and "Gifts and Donations"
    → "Gifts And Donations", so we walk word-by-word.
    """
    out_parts: list[str] = []
    for i, tok in enumerate(raw.split()):
        if not tok:
            out_parts.append(tok)
            continue
        if tok.isupper() and len(tok) <= 4:
            out_parts.append(tok)
            continue
        if i > 0 and tok.lower() in _LOWERCASE_JOINERS:
            out_parts.append(tok.lower())
            continue
        out_parts.append(tok[:1].upper() + tok[1:].lower())
    return " ".join(out_parts)


# Case-insensitive lookup tables built once at import time.
# Banks report categories in arbitrary casing ("restaurants", "RESTAURANTS",
# "Restaurants") and we want them all to land at the same canonical label.
_MAP_LOWER: dict[str, str] = {k.lower(): v for k, v in NORMALIZATION_MAP.items()}
_CANONICAL_LOWER: dict[str, str] = {c.lower(): c for c in KNOWN_CANONICAL_LABELS}


def normalize(raw: Optional[str]) -> Optional[str]:
    """Return the canonical label for ``raw`` or None for empty input.

    Lookup order:
    1. Case-insensitive match against ``NORMALIZATION_MAP`` keys.
    2. Case-insensitive match against ``KNOWN_CANONICAL_LABELS``.
    3. Titlecase fallback (preserves short uppercase acronyms + lowercase
       joiners like "and").

    Idempotent: ``normalize(normalize(x)) == normalize(x)`` for every x.
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    key = s.lower()
    if key in _MAP_LOWER:
        return _MAP_LOWER[key]
    # Already-approved canonical label → return the canonical casing,
    # not whatever case the input arrived in.
    if key in _CANONICAL_LOWER:
        return _CANONICAL_LOWER[key]
    return _fallback_titlecase(s)
