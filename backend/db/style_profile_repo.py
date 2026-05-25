"""Repository for the singleton advisor_style_profile row.

The profile holds a freeform paragraph that the reflection job writes
after summarizing recent user messages + thumbed-up replies. The advisor
router reads it on every turn and injects it into the system prompt.
"""
from __future__ import annotations

import logging
from typing import Optional, TypedDict

from sqlalchemy import text

from db.base import sync_engine

logger = logging.getLogger(__name__)

PROFILE_ID = "household"


class StyleProfile(TypedDict):
    id: str
    style_notes: str
    turn_count_at_last_update: int
    updated_at: Optional[str]


def get_profile() -> Optional[StyleProfile]:
    """Return the singleton style profile, or None if it has never been written."""
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, style_notes, turn_count_at_last_update, updated_at "
                "FROM advisor_style_profile WHERE id = :id"
            ),
            {"id": PROFILE_ID},
        ).fetchone()
    if row is None:
        return None
    return StyleProfile(
        id=row[0],
        style_notes=row[1] or "",
        turn_count_at_last_update=row[2] or 0,
        updated_at=row[3].isoformat() if row[3] else None,
    )


def upsert_profile(style_notes: str, turn_count: int) -> None:
    """Insert or overwrite the singleton profile row."""
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO advisor_style_profile "
                "  (id, style_notes, turn_count_at_last_update, updated_at) "
                "VALUES (:id, :notes, :tc, NOW()) "
                "ON CONFLICT (id) DO UPDATE SET "
                "  style_notes = EXCLUDED.style_notes, "
                "  turn_count_at_last_update = EXCLUDED.turn_count_at_last_update, "
                "  updated_at = NOW()"
            ),
            {"id": PROFILE_ID, "notes": style_notes, "tc": turn_count},
        )


def total_user_turn_count() -> int:
    """Count of user messages persisted so far — used to trigger reflection."""
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT COUNT(*) FROM conversation_turns WHERE role = 'user'"
            )
        ).fetchone()
    return int(row[0]) if row else 0
