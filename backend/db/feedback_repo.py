"""Repository for advisor_turn_feedback.

Stores 👍 / 👎 ratings the user attaches to individual assistant turns.
The reflection job reads positive-rated turns to derive "what voice the
user actually likes" as input to the style profile.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import text

from db.base import sync_engine

logger = logging.getLogger(__name__)


def record_feedback(turn_id: int, rating: int, note: str = "") -> bool:
    """Upsert a feedback row. Returns True on success, False if the
    turn_id doesn't exist (FK violation handled gracefully)."""
    if rating not in (-1, 1):
        raise ValueError(f"rating must be -1 or 1, got {rating}")
    try:
        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO advisor_turn_feedback "
                    "  (turn_id, rating, note) "
                    "VALUES (:tid, :r, :n) "
                    "ON CONFLICT (turn_id) DO UPDATE SET "
                    "  rating = EXCLUDED.rating, "
                    "  note = EXCLUDED.note, "
                    "  created_at = NOW()"
                ),
                {"tid": turn_id, "r": rating, "n": note or ""},
            )
        return True
    except Exception as e:
        logger.warning(f"[feedback_repo] insert failed for turn={turn_id}: {e}")
        return False


def get_positive_turn_contents(limit: int = 20) -> List[str]:
    """Return content of recently thumbed-up assistant turns, newest first."""
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT t.content "
                "FROM advisor_turn_feedback f "
                "JOIN conversation_turns t ON t.id = f.turn_id "
                "WHERE f.rating = 1 "
                "ORDER BY f.created_at DESC "
                "LIMIT :lim"
            ),
            {"lim": limit},
        ).fetchall()
    return [r[0] for r in rows if r[0]]


def get_feedback_for_turn(turn_id: int) -> Optional[int]:
    """Return the current rating for a turn (-1/+1), or None if unrated."""
    with sync_engine.connect() as conn:
        row = conn.execute(
            text("SELECT rating FROM advisor_turn_feedback WHERE turn_id = :t"),
            {"t": turn_id},
        ).fetchone()
    return int(row[0]) if row else None
