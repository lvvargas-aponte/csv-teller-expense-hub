"""Repository for ``instance_identity`` and ``peers``.

Same sync-engine pattern as ``scheduled_tasks_repo``. ``instance_identity`` is
a singleton enforced by an ``id = 1`` check constraint, so ``set_identity``
upserts on that fixed key rather than inserting.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text

from db.base import sync_engine

_IDENTITY_COLS = "user_id, display_name, person_slot, created_at"
_PEER_COLS = "user_id, display_name, person_slot, added_at"


def _identity_to_dict(row) -> Dict[str, Any]:
    return {
        "user_id": str(row[0]),
        "display_name": row[1],
        "person_slot": int(row[2]),
        "created_at": row[3].isoformat() if row[3] else None,
    }


def _peer_to_dict(row) -> Dict[str, Any]:
    return {
        "user_id": str(row[0]),
        "display_name": row[1],
        "person_slot": int(row[2]),
        "added_at": row[3].isoformat() if row[3] else None,
    }


def get_identity() -> Optional[Dict[str, Any]]:
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {_IDENTITY_COLS} FROM instance_identity WHERE id = 1")
        ).fetchone()
    return _identity_to_dict(row) if row else None


def set_identity(user_id: str, display_name: str, person_slot: int) -> Dict[str, Any]:
    """Bootstrap the singleton identity. Never reassigns an existing ``user_id``.

    ``user_id`` namespaces every sheet row this instance ever publishes, so a
    second caller racing the first bootstrap must not overwrite it. Uses
    ``ON CONFLICT ... DO NOTHING`` and always returns the row that exists,
    whichever caller won.
    """
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO instance_identity (id, user_id, display_name, person_slot) "
                "VALUES (1, CAST(:uid AS UUID), :name, :slot) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"uid": user_id, "name": display_name, "slot": person_slot},
        )
        row = conn.execute(
            text(f"SELECT {_IDENTITY_COLS} FROM instance_identity WHERE id = 1")
        ).fetchone()
    return _identity_to_dict(row)


def rename_identity(display_name: str) -> Optional[Dict[str, Any]]:
    """Update the display name only. ``user_id`` and ``person_slot`` are untouched."""
    with sync_engine.begin() as conn:
        row = conn.execute(
            text(
                "UPDATE instance_identity SET display_name = :name "
                f"WHERE id = 1 RETURNING {_IDENTITY_COLS}"
            ),
            {"name": display_name},
        ).fetchone()
    return _identity_to_dict(row) if row else None


def list_peers() -> List[Dict[str, Any]]:
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT {_PEER_COLS} FROM peers ORDER BY person_slot ASC")
        ).fetchall()
    return [_peer_to_dict(r) for r in rows]


def upsert_peer(user_id: str, display_name: str, person_slot: int) -> Dict[str, Any]:
    with sync_engine.begin() as conn:
        row = conn.execute(
            text(
                "INSERT INTO peers (user_id, display_name, person_slot) "
                "VALUES (CAST(:uid AS UUID), :name, :slot) "
                "ON CONFLICT (user_id) DO UPDATE SET "
                "  display_name = EXCLUDED.display_name, "
                "  person_slot = EXCLUDED.person_slot "
                f"RETURNING {_PEER_COLS}"
            ),
            {"uid": user_id, "name": display_name, "slot": person_slot},
        ).fetchone()
    return _peer_to_dict(row)


def delete_peer(user_id: str) -> bool:
    with sync_engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM peers WHERE user_id = CAST(:uid AS UUID)"),
            {"uid": user_id},
        )
    return result.rowcount > 0


def adopt_peer_identity(
    person_slot: int, real_user_id: str, display_name: str
) -> Dict[str, Any]:
    """Make ``real_user_id`` the sole peer at ``person_slot``.

    Bootstrap invents a placeholder id for the peer because their real one is
    generated on their own instance and only reaches us through the sheet. This
    swaps the placeholder out rather than leaving it behind as a rival row.
    """
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM peers "
                "WHERE person_slot = :slot AND user_id <> CAST(:uid AS UUID)"
            ),
            {"slot": person_slot, "uid": real_user_id},
        )
        row = conn.execute(
            text(
                "INSERT INTO peers (user_id, display_name, person_slot) "
                "VALUES (CAST(:uid AS UUID), :name, :slot) "
                "ON CONFLICT (user_id) DO UPDATE SET "
                "  display_name = EXCLUDED.display_name, "
                "  person_slot = EXCLUDED.person_slot "
                f"RETURNING {_PEER_COLS}"
            ),
            {"uid": real_user_id, "name": display_name, "slot": person_slot},
        ).fetchone()
    return _peer_to_dict(row)
