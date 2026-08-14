"""Repository for the singleton fact_reflection_state row — the watermark
that tells ``fact_reflection`` how far it has scanned the transcript.
Mirrors the single-row upsert pattern in ``style_profile_repo``."""
from __future__ import annotations

from sqlalchemy import text

from db.base import sync_engine

STATE_ID = "household"


def get_turn_count_at_last_scan() -> int:
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT turn_count_at_last_scan FROM fact_reflection_state "
                "WHERE id = :id"
            ),
            {"id": STATE_ID},
        ).fetchone()
    return int(row[0]) if row else 0


def set_turn_count_at_last_scan(turn_count: int) -> None:
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO fact_reflection_state "
                "  (id, turn_count_at_last_scan, updated_at) "
                "VALUES (:id, :tc, NOW()) "
                "ON CONFLICT (id) DO UPDATE SET "
                "  turn_count_at_last_scan = EXCLUDED.turn_count_at_last_scan, "
                "  updated_at = NOW()"
            ),
            {"id": STATE_ID, "tc": turn_count},
        )
