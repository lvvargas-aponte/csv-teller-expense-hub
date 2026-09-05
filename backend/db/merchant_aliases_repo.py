"""Repository for ``merchant_aliases`` — merchant keys folded into one.

Same shape as ``subscriptions_repo``: one SQL round-trip per function, no
business logic. ``analytics.detect_recurring_charges`` reads the mapping and
groups an alias's transactions under its canonical merchant.
"""
from __future__ import annotations

import logging
from typing import Dict, List

from sqlalchemy import text

from db.base import sync_engine

logger = logging.getLogger(__name__)


def list_aliases() -> Dict[str, str]:
    """``{alias_key: canonical_key}`` for every declared merge."""
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT alias_key, canonical_key FROM merchant_aliases")
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def upsert_alias(alias_key: str, canonical_key: str) -> Dict[str, str]:
    """Fold ``alias_key`` into ``canonical_key``.

    Two shapes are rejected outright rather than stored and resolved later:
    merging a merchant into itself, and merging into a key that is itself an
    alias — the second would need chain resolution, and the caller can just
    pass the end of the chain instead.
    """
    if alias_key == canonical_key:
        raise ValueError("a merchant cannot be an alias of itself")

    with sync_engine.begin() as conn:
        existing = conn.execute(
            text("SELECT canonical_key FROM merchant_aliases WHERE alias_key = :key"),
            {"key": canonical_key},
        ).fetchone()
        if existing:
            raise ValueError(
                f"{canonical_key!r} is itself an alias of {existing[0]!r}; "
                "merge into that instead"
            )
        # Anything already pointing at the alias follows it to its new home,
        # so a two-step merge (a→b, then b→c) leaves no dangling hop.
        conn.execute(
            text(
                "UPDATE merchant_aliases SET canonical_key = :canonical "
                "WHERE canonical_key = :alias"
            ),
            {"canonical": canonical_key, "alias": alias_key},
        )
        conn.execute(
            text(
                "INSERT INTO merchant_aliases (alias_key, canonical_key) "
                "VALUES (:alias, :canonical) "
                "ON CONFLICT (alias_key) DO UPDATE SET "
                "  canonical_key = EXCLUDED.canonical_key"
            ),
            {"alias": alias_key, "canonical": canonical_key},
        )
    return {"alias_key": alias_key, "canonical_key": canonical_key}


def delete_alias(alias_key: str) -> bool:
    with sync_engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM merchant_aliases WHERE alias_key = :key"),
            {"key": alias_key},
        )
    return result.rowcount > 0


def aliases_of(canonical_key: str) -> List[str]:
    """Every key folded into ``canonical_key``."""
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT alias_key FROM merchant_aliases "
                "WHERE canonical_key = :key ORDER BY alias_key"
            ),
            {"key": canonical_key},
        ).fetchall()
    return [r[0] for r in rows]
