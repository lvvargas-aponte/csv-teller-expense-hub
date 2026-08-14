"""Repository for the ``digests`` table — stored weekly digest snapshots."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from sqlalchemy import text

from db.base import sync_engine

logger = logging.getLogger(__name__)

_SELECT_COLS = "id, payload, generated_at, read_at"


def _row_to_dict(row) -> Dict[str, Any]:
    return {
        "id": int(row[0]),
        "payload": row[1],
        "generated_at": row[2].isoformat() if row[2] else None,
        "read": row[3] is not None,
    }


def latest() -> Optional[Dict[str, Any]]:
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {_SELECT_COLS} FROM digests ORDER BY generated_at DESC LIMIT 1")
        ).fetchone()
    return _row_to_dict(row) if row else None


def insert(payload: Dict[str, Any]) -> Dict[str, Any]:
    with sync_engine.begin() as conn:
        row = conn.execute(
            text(
                "INSERT INTO digests (payload) VALUES (CAST(:payload AS jsonb)) "
                f"RETURNING {_SELECT_COLS}"
            ),
            {"payload": json.dumps(payload)},
        ).fetchone()
    return _row_to_dict(row)


def mark_read(digest_id: int) -> bool:
    """Idempotent — re-marking an already-read digest keeps the original
    read_at and still reports success."""
    with sync_engine.begin() as conn:
        result = conn.execute(
            text(
                "UPDATE digests SET read_at = COALESCE(read_at, NOW()) "
                "WHERE id = :id"
            ),
            {"id": digest_id},
        )
    return result.rowcount > 0