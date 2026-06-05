"""Repository for the ``user_facts`` table — Fin's structured memory.

Mirrors the sync-engine pattern used by ``style_profile_repo``. Each
function is a single SQL round-trip; no business logic here (the agent
tools and the REST router compose calls).

Field invariants enforced by the schema (Alembic 0010):
- ``category`` must be one of {preference, constraint, goal, life_event, pattern}
- ``status`` must be one of {proposed, confirmed, rejected}
- ``tags`` is a non-null TEXT[] (empty array, not NULL)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from db.base import sync_engine

logger = logging.getLogger(__name__)


VALID_CATEGORIES = ("preference", "constraint", "goal", "life_event", "pattern")
VALID_STATUSES = ("proposed", "confirmed", "rejected")


def _row_to_dict(row) -> Dict[str, Any]:
    return {
        "id": int(row[0]),
        "fact": row[1],
        "category": row[2],
        "tags": list(row[3] or []),
        "status": row[4],
        "sensitive": bool(row[5]),
        "confidence": float(row[6]) if row[6] is not None else 0.5,
        "source_turn_id": int(row[7]) if row[7] is not None else None,
        "created_at": row[8].isoformat() if row[8] else None,
        "updated_at": row[9].isoformat() if row[9] else None,
    }


_SELECT_COLS = (
    "id, fact, category, tags, status, sensitive, confidence, "
    "source_turn_id, created_at, updated_at"
)


def list_facts(
    status: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    where: List[str] = []
    params: Dict[str, Any] = {"lim": limit}
    if status is not None:
        where.append("status = :status")
        params["status"] = status
    if category is not None:
        where.append("category = :category")
        params["category"] = category
    sql = f"SELECT {_SELECT_COLS} FROM user_facts"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY confidence DESC, updated_at DESC LIMIT :lim"
    with sync_engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_fact(fact_id: int) -> Optional[Dict[str, Any]]:
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {_SELECT_COLS} FROM user_facts WHERE id = :id"),
            {"id": fact_id},
        ).fetchone()
    return _row_to_dict(row) if row else None


def create_fact(
    fact: str,
    category: str,
    tags: Optional[List[str]] = None,
    status: str = "proposed",
    sensitive: bool = False,
    confidence: float = 0.5,
    source_turn_id: Optional[int] = None,
) -> Dict[str, Any]:
    if category not in VALID_CATEGORIES:
        raise ValueError(f"category must be one of {VALID_CATEGORIES}")
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {VALID_STATUSES}")
    with sync_engine.begin() as conn:
        row = conn.execute(
            text(
                "INSERT INTO user_facts "
                "  (fact, category, tags, status, sensitive, confidence, source_turn_id) "
                "VALUES "
                "  (:fact, :category, :tags, :status, :sensitive, :confidence, :src) "
                f"RETURNING {_SELECT_COLS}"
            ),
            {
                "fact": fact, "category": category, "tags": list(tags or []),
                "status": status, "sensitive": sensitive,
                "confidence": confidence, "src": source_turn_id,
            },
        ).fetchone()
    return _row_to_dict(row)


def update_fact(
    fact_id: int,
    fact: Optional[str] = None,
    tags: Optional[List[str]] = None,
    sensitive: Optional[bool] = None,
    confidence: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    sets: List[str] = []
    params: Dict[str, Any] = {"id": fact_id}
    if fact is not None:
        sets.append("fact = :fact")
        params["fact"] = fact
    if tags is not None:
        sets.append("tags = :tags")
        params["tags"] = list(tags)
    if sensitive is not None:
        sets.append("sensitive = :sensitive")
        params["sensitive"] = sensitive
    if confidence is not None:
        sets.append("confidence = :confidence")
        params["confidence"] = confidence
    if not sets:
        return get_fact(fact_id)
    sets.append("updated_at = NOW()")
    with sync_engine.begin() as conn:
        row = conn.execute(
            text(
                f"UPDATE user_facts SET {', '.join(sets)} WHERE id = :id "
                f"RETURNING {_SELECT_COLS}"
            ),
            params,
        ).fetchone()
    return _row_to_dict(row) if row else None


def set_status(fact_id: int, status: str) -> Optional[Dict[str, Any]]:
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {VALID_STATUSES}")
    with sync_engine.begin() as conn:
        row = conn.execute(
            text(
                "UPDATE user_facts SET status = :status, updated_at = NOW() "
                f"WHERE id = :id RETURNING {_SELECT_COLS}"
            ),
            {"id": fact_id, "status": status},
        ).fetchone()
    return _row_to_dict(row) if row else None


def delete_fact(fact_id: int) -> bool:
    with sync_engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM user_facts WHERE id = :id"),
            {"id": fact_id},
        )
    return result.rowcount > 0
