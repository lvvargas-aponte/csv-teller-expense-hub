"""Curated-seed loader.

Defaults ship in ``backend/data/seeds_default.json`` (versioned in git
so updates flow through ``git pull``).  Runtime overrides — user
additions and removals — live in two small Postgres tables created in
Alembic 0006.  This module produces the merged view both the
``/api/seeds`` endpoint and the URL-fetcher allowlist consume.

Merge rules:
* Defaults present in ``seed_removed_defaults`` are dropped.
* Custom seeds are appended to a "Custom" group at the end (or merged
  into an existing group when ``group_label`` matches).
* Each returned seed carries ``id`` (``"d:..."`` for defaults,
  ``"c:<int>"`` for custom) and ``is_custom`` so the frontend can
  decide whether to show a delete affordance.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import text

from db.base import sync_engine

logger = logging.getLogger(__name__)

_DEFAULTS_PATH = Path(__file__).parent / "data" / "seeds_default.json"


@lru_cache(maxsize=1)
def _load_defaults_raw() -> dict[str, Any]:
    """Read and cache the JSON file once per process.  Hot-reload during
    development is fine: the dev server restarts on file change, which
    blows the cache."""
    if not _DEFAULTS_PATH.exists():
        logger.warning(f"[seeds] defaults file missing: {_DEFAULTS_PATH}")
        return {"groups": []}
    return json.loads(_DEFAULTS_PATH.read_text(encoding="utf-8"))


def _fetch_overrides() -> tuple[set[str], list[dict[str, Any]]]:
    """Return ``(removed_default_ids, custom_seed_rows)`` from Postgres."""
    with sync_engine.connect() as conn:
        removed = {
            r[0] for r in conn.execute(
                text("SELECT default_id FROM seed_removed_defaults")
            ).fetchall()
        }
        custom_rows = conn.execute(
            text(
                "SELECT id, title, url, scope, category, why, "
                "       group_label, manual_only, created_at "
                "FROM seed_custom ORDER BY created_at ASC"
            )
        ).fetchall()
    customs = [
        {
            "id": f"c:{r[0]}",
            "custom_pk": int(r[0]),
            "title": r[1],
            "url": r[2],
            "scope": r[3],
            "category": r[4],
            "why": r[5] or "",
            "group_label": r[6] or "Custom",
            "manual_only": bool(r[7]),
            "is_custom": True,
            "created_at": r[8].isoformat() if r[8] else None,
        }
        for r in custom_rows
    ]
    return removed, customs


def list_seed_groups() -> list[dict[str, Any]]:
    """Return the merged list of groups consumed by the Knowledge tab.

    Shape:
        [
          {
            "label": str, "hint": str, "note": str | None,
            "seeds": [
              {"id": "d:...", "title": ..., "url": ..., ..., "is_custom": False},
              {"id": "c:42",  ...,                          "is_custom": True},
            ],
          },
          ...
        ]
    """
    raw = _load_defaults_raw()
    removed, customs = _fetch_overrides()

    # Index defaults by group_label so custom seeds with a matching
    # label can be appended to that group rather than spawning a new one.
    groups: list[dict[str, Any]] = []
    by_label: dict[str, dict[str, Any]] = {}
    for grp in raw.get("groups", []):
        seeds = []
        for s in grp.get("seeds", []):
            did = s.get("default_id")
            if not did or did in removed:
                continue
            seeds.append({
                "id": did,
                "title": s["title"],
                "url": s["url"],
                "scope": s.get("scope", "external"),
                "category": s.get("category", "literacy"),
                "why": s.get("why", ""),
                "group_label": grp["label"],
                "manual_only": bool(s.get("manual_only", False)),
                "is_custom": False,
            })
        out_grp = {
            "label": grp["label"],
            "hint": grp.get("hint", ""),
            "note": grp.get("note"),
            "seeds": seeds,
        }
        groups.append(out_grp)
        by_label[grp["label"]] = out_grp

    # Drop any groups that were emptied by removals so the UI doesn't
    # render an orphaned heading.  Keep the first appearance order.
    groups = [g for g in groups if g["seeds"] or by_label.get(g["label"]) in (g,)]

    for c in customs:
        target = by_label.get(c["group_label"])
        if target is None:
            target = {
                "label": c["group_label"],
                "hint": "",
                "note": None,
                "seeds": [],
            }
            groups.append(target)
            by_label[c["group_label"]] = target
        target["seeds"].append({
            "id": c["id"],
            "title": c["title"],
            "url": c["url"],
            "scope": c["scope"],
            "category": c["category"],
            "why": c["why"],
            "group_label": c["group_label"],
            "manual_only": c["manual_only"],
            "is_custom": True,
        })

    # Final pass: drop any group with zero seeds (could happen if all
    # defaults were removed and the group has no customs yet).
    return [g for g in groups if g["seeds"]]


# ---------------------------------------------------------------------------
# Mutations — used by the ``/api/seeds`` endpoints.
# ---------------------------------------------------------------------------


def add_custom_seed(
    *,
    title: str,
    url: str,
    scope: str,
    category: str,
    why: str = "",
    group_label: str = "Custom",
    manual_only: bool = False,
) -> int:
    """Insert a custom seed.  Auto-adds the URL's host to
    ``allowlist_hosts`` so the URL fetcher will accept it.  Returns the
    new ``seed_custom.id``.  Raises ``ValueError`` if URL is invalid or
    already exists in ``seed_custom``.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("URL must use https://")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("URL has no host")

    with sync_engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM seed_custom WHERE url = :u"),
            {"u": url},
        ).fetchone()
        if existing:
            raise ValueError(f"Seed with URL {url} already exists (id={existing[0]})")

        new_id = conn.execute(
            text(
                "INSERT INTO seed_custom "
                "  (title, url, scope, category, why, group_label, manual_only) "
                "VALUES (:title, :url, :scope, :category, :why, :group, :manual) "
                "RETURNING id"
            ),
            {
                "title": title,
                "url": url,
                "scope": scope,
                "category": category,
                "why": why,
                "group": group_label,
                "manual": manual_only,
            },
        ).scalar_one()

        # Auto-allowlist the host so the URL fetcher will accept this seed.
        # Skip if it's already there (either base set or runtime additions).
        conn.execute(
            text(
                "INSERT INTO allowlist_hosts (host, origin) "
                "VALUES (:h, 'custom_seed') "
                "ON CONFLICT (host) DO NOTHING"
            ),
            {"h": host},
        )
    return int(new_id)


def remove_seed(seed_id: str) -> bool:
    """Remove either a default (by ``"d:..."`` id) or a custom (by
    ``"c:<int>"``).  For defaults this inserts a row in
    ``seed_removed_defaults``; for customs this deletes from
    ``seed_custom``.  Returns True if anything changed."""
    if seed_id.startswith("d:"):
        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO seed_removed_defaults (default_id) "
                    "VALUES (:id) ON CONFLICT (default_id) DO NOTHING"
                ),
                {"id": seed_id},
            )
        return True
    if seed_id.startswith("c:"):
        try:
            pk = int(seed_id[2:])
        except ValueError:
            return False
        with sync_engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM seed_custom WHERE id = :id"),
                {"id": pk},
            )
        return (result.rowcount or 0) > 0
    return False


def restore_default(default_id: str) -> bool:
    """Un-hide a previously-removed default.  Returns True if a row was
    deleted from ``seed_removed_defaults``."""
    if not default_id.startswith("d:"):
        return False
    with sync_engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM seed_removed_defaults WHERE default_id = :id"),
            {"id": default_id},
        )
    return (result.rowcount or 0) > 0


def list_hidden_defaults() -> list[dict[str, Any]]:
    """Return defaults the user has hidden via DELETE /api/seeds/d:...

    Used by the UI's "Hidden defaults" expandable section so the user can
    see what's been hidden and restore individual entries.  Returns the
    same per-seed shape as ``list_seed_groups`` (minus group nesting),
    so the frontend can render rows the same way.
    """
    raw = _load_defaults_raw()
    removed, _customs = _fetch_overrides()
    if not removed:
        return []
    out: list[dict[str, Any]] = []
    for grp in raw.get("groups", []):
        for s in grp.get("seeds", []):
            did = s.get("default_id")
            if did in removed:
                out.append({
                    "id": did,
                    "title": s["title"],
                    "url": s["url"],
                    "scope": s.get("scope", "external"),
                    "category": s.get("category", "literacy"),
                    "why": s.get("why", ""),
                    "group_label": grp["label"],
                    "manual_only": bool(s.get("manual_only", False)),
                    "is_custom": False,
                })
    return out


def list_runtime_allowed_hosts() -> set[str]:
    """Hosts added via custom seeds or direct API calls.  Unioned with
    ``url_fetcher.BASE_ALLOWED_HOSTS`` to form the effective allowlist.
    """
    try:
        with sync_engine.connect() as conn:
            rows = conn.execute(
                text("SELECT host FROM allowlist_hosts")
            ).fetchall()
        return {r[0] for r in rows}
    except Exception as e:
        # Tolerate the table missing (eg. tests that haven't migrated yet)
        # so the URL fetcher still works against the static base set.
        logger.warning(f"[seeds] runtime allowlist query failed: {e}")
        return set()
