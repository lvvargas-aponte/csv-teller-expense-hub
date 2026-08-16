"""Instance identity — who this stack belongs to, and who it settles with.

The identity is created lazily on first read rather than at import time, so
unit tests (which run with no database) can import the app freely. The
``current_user_id`` / ``peer_user_id`` helpers never raise: callers on the
transaction write path must not fail because identity is unavailable.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from config import INSTANCE_PERSON_SLOT, PERSON_1_NAME, PERSON_2_NAME
from db import identity_repo

logger = logging.getLogger(__name__)


def _name_for_slot(slot: int) -> str:
    return PERSON_1_NAME if slot == 1 else PERSON_2_NAME


def _other_slot(slot: int) -> int:
    return 2 if slot == 1 else 1


def ensure_identity() -> Dict[str, Any]:
    """Create this instance's identity and its peer on first call.

    Idempotent: an existing identity is returned untouched, so a display-name
    edit made through the API is never reverted by a later call.
    """
    existing = identity_repo.get_identity()
    if existing is None:
        slot = INSTANCE_PERSON_SLOT
        existing = identity_repo.set_identity(
            user_id=str(uuid.uuid4()),
            display_name=_name_for_slot(slot),
            person_slot=slot,
        )
        logger.info(
            f"[identity] Bootstrapped instance identity for slot {slot} "
            f"({existing['display_name']})."
        )

    if not identity_repo.list_peers():
        peer_slot = _other_slot(existing["person_slot"])
        identity_repo.upsert_peer(
            user_id=str(uuid.uuid4()),
            display_name=_name_for_slot(peer_slot),
            person_slot=peer_slot,
        )

    return existing


def current_user_id() -> Optional[str]:
    """This instance's user id, or None if unavailable. Never raises."""
    try:
        identity = identity_repo.get_identity()
    except Exception as e:
        logger.debug(f"[identity] current_user_id unavailable: {e}")
        return None
    return identity["user_id"] if identity else None


def peer_user_id() -> Optional[str]:
    """The first peer's user id, or None if unavailable. Never raises."""
    try:
        peers = identity_repo.list_peers()
    except Exception as e:
        logger.debug(f"[identity] peer_user_id unavailable: {e}")
        return None
    return peers[0]["user_id"] if peers else None
