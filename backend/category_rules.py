"""User-authored merchant→category rules.

The single source of truth for both reading the rules and applying them.
``categorizer.suggest_category`` calls :func:`match` before it reaches for
Ollama, so a rule the user wrote always beats the model's guess and still
answers when Ollama is unreachable.

Matching is a case-insensitive substring test against the transaction
description, in ``position`` order — first match wins. Deliberately not
regex: these are typed into a settings field by hand, and a malformed
pattern should fail to match rather than raise mid-categorization.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from sqlalchemy import text

from db.base import sync_engine

logger = logging.getLogger(__name__)


def list_rules() -> List[Dict]:
    """Return every rule in evaluation order."""
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, match, category, position FROM category_rules "
                "ORDER BY position, id"
            )
        ).fetchall()
    return [
        {"id": r[0], "match": r[1], "category": r[2], "position": r[3]}
        for r in rows
    ]


def replace_all(rules: List[Dict]) -> List[Dict]:
    """Overwrite the rule list with ``rules``, renumbering positions.

    A whole-list replace rather than per-row CRUD because the settings
    page saves the entire form at once — reordering, editing, and
    deleting arrive together and must land atomically.

    Rules with a blank ``match`` or ``category`` are dropped: the UI's
    "+ Add rule" seeds an empty row, and an empty pattern would otherwise
    substring-match every transaction.
    """
    cleaned = [
        {
            "match": (r.get("match") or "").strip(),
            "category": (r.get("category") or "").strip(),
        }
        for r in rules
    ]
    cleaned = [r for r in cleaned if r["match"] and r["category"]]

    with sync_engine.begin() as conn:
        conn.execute(text("DELETE FROM category_rules"))
        for position, rule in enumerate(cleaned):
            conn.execute(
                text(
                    "INSERT INTO category_rules (match, category, position) "
                    "VALUES (:match, :category, :position)"
                ),
                {**rule, "position": position},
            )
    return list_rules()


def rules_for_matching() -> List[Dict]:
    """Rules for the categorization path, degrading to none on failure.

    Categorizing must not break because the rules table is unreachable —
    an unavailable rule list means "no rule matched", which falls through
    to the model. The GET endpoint deliberately uses :func:`list_rules`
    instead so a real failure surfaces there.
    """
    try:
        return list_rules()
    except Exception as e:
        logger.debug(f"[category_rules] read skipped: {e}")
        return []


def match(description: str, rules: Optional[List[Dict]] = None) -> Optional[str]:
    """Return the category of the first rule matching ``description``.

    ``rules`` may be passed in to categorize a batch without re-reading
    the table per transaction.
    """
    if not description:
        return None
    if rules is None:
        rules = rules_for_matching()

    haystack = description.lower()
    for rule in rules:
        needle = (rule.get("match") or "").strip().lower()
        if needle and needle in haystack:
            return rule.get("category")
    return None
