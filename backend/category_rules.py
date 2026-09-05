"""User-authored merchant→category rules.

The single source of truth for both reading the rules and applying them.
``categorizer.suggest_category`` calls :func:`match` before it reaches for
Ollama, so a rule the user wrote always beats the model's guess and still
answers when Ollama is unreachable.

Two kinds, checked in that order:

``merchant``
    The whole normalized merchant key (``merchant_key.canonical``) must
    equal the pattern. This is what "always categorize CHIPOTLE as Dining"
    writes when you categorize a row — an exact statement about one
    merchant, immune to the store numbers and session ids banks append.

``contains``
    Case-insensitive substring against the raw description, in
    ``position`` order. What rules were before merchant keys, and the
    escape hatch for cases a merchant key misses. Deliberately not regex:
    these are typed into a settings field by hand, and a malformed pattern
    should fail to match rather than raise mid-categorization.

Merchant rules win because they are precise; a substring is a guess about
which fragment of a description is stable.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from sqlalchemy import text

import merchant_key
from db.base import sync_engine

logger = logging.getLogger(__name__)

MERCHANT = "merchant"
CONTAINS = "contains"
KINDS = (MERCHANT, CONTAINS)

_COLUMNS = (
    "id, kind, pattern, category, position, enabled, created_at, last_matched_at"
)


def _row_to_dict(r) -> Dict:
    return {
        "id": r[0],
        "kind": r[1],
        "pattern": r[2],
        "category": r[3],
        "position": r[4],
        "enabled": r[5],
        "created_at": r[6],
        "last_matched_at": r[7],
    }


def list_rules() -> List[Dict]:
    """Return every rule in evaluation order, disabled ones included.

    The settings page shows disabled rules so they can be turned back on;
    :func:`rules_for_matching` is what filters them out.
    """
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT {_COLUMNS} FROM category_rules "
                "ORDER BY kind = 'contains', position, id"
            )
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_rule(rule_id: int) -> Optional[Dict]:
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {_COLUMNS} FROM category_rules WHERE id = :id"),
            {"id": rule_id},
        ).fetchone()
    return _row_to_dict(row) if row else None


def find_by_merchant(pattern: str) -> Optional[Dict]:
    """The merchant rule for ``pattern``, or None.

    Drives the "offer to make a rule" prompt: a merchant that already has
    one must not be asked about again.
    """
    key = (pattern or "").strip().lower()
    if not key:
        return None
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(
                f"SELECT {_COLUMNS} FROM category_rules "
                "WHERE kind = 'merchant' AND pattern = :p"
            ),
            {"p": key},
        ).fetchone()
    return _row_to_dict(row) if row else None


def create_rule(pattern: str, category: str, kind: str = CONTAINS) -> Optional[Dict]:
    """Add one rule at the end of the order.

    Returns None when the pattern or category is blank — an empty pattern
    would substring-match every transaction. A merchant rule for a key that
    already has one updates it instead of erroring: the user's most recent
    statement about a merchant is the one they mean.
    """
    pattern = (pattern or "").strip()
    category = (category or "").strip()
    if not pattern or not category:
        return None
    if kind not in KINDS:
        raise ValueError(f"unknown rule kind {kind!r}; expected one of {KINDS}")
    if kind == MERCHANT:
        pattern = pattern.lower()

    with sync_engine.begin() as conn:
        next_position = conn.execute(
            text("SELECT COALESCE(MAX(position), -1) + 1 FROM category_rules")
        ).scalar()
        row = conn.execute(
            text(
                "INSERT INTO category_rules (kind, pattern, category, position) "
                "VALUES (:kind, :pattern, :category, :position) "
                "ON CONFLICT (pattern) WHERE kind = 'merchant' "
                "DO UPDATE SET category = EXCLUDED.category, enabled = TRUE "
                f"RETURNING {_COLUMNS}"
            ),
            {
                "kind": kind,
                "pattern": pattern,
                "category": category,
                "position": next_position,
            },
        ).fetchone()
    return _row_to_dict(row)


def update_rule(rule_id: int, **fields) -> Optional[Dict]:
    """Patch one rule. Accepts pattern, category, enabled and position."""
    allowed = {"pattern", "category", "enabled", "position"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_rule(rule_id)

    for key in ("pattern", "category"):
        if key in updates:
            cleaned = (updates[key] or "").strip()
            if not cleaned:
                return None
            updates[key] = cleaned

    assignments = ", ".join(f"{k} = :{k}" for k in updates)
    with sync_engine.begin() as conn:
        row = conn.execute(
            text(
                f"UPDATE category_rules SET {assignments} WHERE id = :id "
                f"RETURNING {_COLUMNS}"
            ),
            {**updates, "id": rule_id},
        ).fetchone()
    return _row_to_dict(row) if row else None


def delete_rule(rule_id: int) -> bool:
    with sync_engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM category_rules WHERE id = :id"), {"id": rule_id}
        )
    return result.rowcount > 0


def replace_all(rules: List[Dict]) -> List[Dict]:
    """Overwrite the substring rules with ``rules``, renumbering positions.

    A whole-list replace rather than per-row CRUD because the settings
    page's rule form saves at once — reordering, editing and deleting
    arrive together and must land atomically.

    Merchant rules are left alone: they are created one at a time from the
    transactions table and carry their own identity, so a form that does
    not show them must not delete them.

    Rules with a blank pattern or category are dropped: the UI's "+ Add
    rule" seeds an empty row, and an empty pattern would otherwise
    substring-match every transaction.
    """
    cleaned = [
        {
            "pattern": (r.get("pattern") or r.get("match") or "").strip(),
            "category": (r.get("category") or "").strip(),
            "enabled": bool(r.get("enabled", True)),
        }
        for r in rules
    ]
    cleaned = [r for r in cleaned if r["pattern"] and r["category"]]

    with sync_engine.begin() as conn:
        conn.execute(text("DELETE FROM category_rules WHERE kind = 'contains'"))
        for position, rule in enumerate(cleaned):
            conn.execute(
                text(
                    "INSERT INTO category_rules "
                    "(kind, pattern, category, position, enabled) "
                    "VALUES ('contains', :pattern, :category, :position, :enabled)"
                ),
                {**rule, "position": position},
            )
    return list_rules()


def rules_for_matching() -> List[Dict]:
    """Enabled rules for the categorization path, degrading to none on failure.

    Categorizing must not break because the rules table is unreachable —
    an unavailable rule list means "no rule matched", which falls through
    to the model. The GET endpoint deliberately uses :func:`list_rules`
    instead so a real failure surfaces there.
    """
    try:
        return [r for r in list_rules() if r["enabled"]]
    except Exception as e:
        logger.debug(f"[category_rules] read skipped: {e}")
        return []


def match_rule(
    description: str,
    rules: Optional[List[Dict]] = None,
    alias_map: Optional[Dict[str, str]] = None,
) -> Optional[Dict]:
    """Return the first rule matching ``description``, or None.

    ``rules`` and ``alias_map`` may be passed in to categorize a batch
    without re-reading either table once per transaction.
    """
    if not description:
        return None
    if rules is None:
        rules = rules_for_matching()
    if not rules:
        return None

    haystack = description.lower()
    key = merchant_key.canonical(description, alias_map)

    for rule in rules:
        if not rule.get("enabled", True):
            continue
        pattern = (rule.get("pattern") or "").strip().lower()
        if not pattern:
            continue
        if rule.get("kind") == MERCHANT:
            if key and pattern == key:
                return rule
        elif pattern in haystack:
            return rule
    return None


def match(
    description: str,
    rules: Optional[List[Dict]] = None,
    alias_map: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """The category of the first rule matching ``description``."""
    rule = match_rule(description, rules, alias_map)
    return rule.get("category") if rule else None


def touch(rule_ids: List[int]) -> None:
    """Record that these rules just matched something.

    Best-effort: the stamp drives a "last used" hint in the settings UI,
    and failing to write it must not fail the categorization that earned
    it.
    """
    if not rule_ids:
        return
    try:
        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE category_rules SET last_matched_at = NOW() "
                    "WHERE id = ANY(:ids)"
                ),
                {"ids": list(set(rule_ids))},
            )
    except Exception as e:
        logger.debug(f"[category_rules] last_matched_at skipped: {e}")
