"""Categories as rows — the single source of truth for the label set.

Before this, a category existed only as a string repeated across every
transaction that used it, so the operations that matter were impossible:
you could not rename one without rewriting history by hand, and merging two
spellings of the same thing meant editing a dict in ``category_normalizer``
and redeploying.

Every mutation here is atomic across all three places a category name is
written — transactions (jsonb in ``json_stores``), budgets (keyed *by*
category), and the ``category`` column on ``category_rules`` — because a
rename that lands in one and not the others silently drops a budget or
orphans a rule.

Roles are the other half. Five constants in ``analytics`` and one in
``routers/subscriptions`` used to compare category *names* to decide whether
a merchant is a bill, a subscription, or not spending at all. Renaming a
category would have quietly changed recurring detection with nothing raising.
Those sets live on the row now, so the behavior follows the rename.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import text

from db.base import sync_engine

logger = logging.getLogger(__name__)

NON_SPENDING = "non_spending"
ALWAYS_RECURRING = "always_recurring"
BILL = "bill"
SUBSCRIPTION = "subscription"
NON_COMMITMENT = "non_commitment"

ROLES = (NON_SPENDING, ALWAYS_RECURRING, BILL, SUBSCRIPTION, NON_COMMITMENT)

# The roles each name carried when they were hardcoded sets in ``analytics``.
# One table, two jobs: it seeds a fresh install (:func:`ensure_seeded`) and it
# is the answer when the table cannot be read. Analytics has to degrade to the
# behavior it had before this table existed rather than to "nothing is a
# bill", which would silently reclassify every commitment the user has.
#
# Names not in the seed list ("Groceries", "Dining", …) carry no role: they
# describe what something was for, not how the app should treat it.
_DEFAULT_ROLES: Dict[str, tuple] = {
    "utilities":           (ALWAYS_RECURRING, BILL),
    "insurance":           (ALWAYS_RECURRING, BILL),
    "rent":                (ALWAYS_RECURRING, BILL),
    "mortgage":            (ALWAYS_RECURRING, BILL),
    "phone":               (ALWAYS_RECURRING, BILL),
    "internet":            (ALWAYS_RECURRING, BILL),
    "subscription":        (ALWAYS_RECURRING, BILL, SUBSCRIPTION),
    "subscriptions":       (ALWAYS_RECURRING, BILL, SUBSCRIPTION),
    "loan":                (BILL,),
    "loans":               (BILL,),
    "childcare":           (BILL,),
    "entertainment":       (SUBSCRIPTION,),
    "streaming":           (SUBSCRIPTION,),
    "music":               (SUBSCRIPTION,),
    "cc payment":          (NON_SPENDING,),
    "credit card payment": (NON_SPENDING,),
    "payments and credits": (NON_SPENDING,),
    "zelle out":           (NON_SPENDING,),
    "transfer":            (NON_SPENDING,),
    "transfers":           (NON_SPENDING,),
    "interest":            (NON_COMMITMENT,),
    "fees":                (NON_COMMITMENT,),
}

_FALLBACK: Dict[str, frozenset] = {
    role: frozenset(n for n, roles in _DEFAULT_ROLES.items() if role in roles)
    for role in ROLES
}

# The categorizer's built-in seed list — the vocabulary a fresh install
# offers before anything has been imported.
DEFAULT_NAMES = (
    "Groceries", "Dining", "Gas", "Utilities", "Rent", "Subscriptions",
    "Health", "Travel", "Shopping", "Entertainment", "Transport",
    "Insurance", "Income", "Fees", "Other",
)


def default_roles_for(name: str) -> List[str]:
    """The roles a category gets when nobody has said otherwise."""
    return list(_DEFAULT_ROLES.get((name or "").strip().lower(), ()))


def ensure_seeded() -> None:
    """Populate an empty categories table with the default vocabulary.

    Alembic 0032 seeds from what was already in use; this covers the cases
    that migration cannot — a fresh install with no data yet, and the test
    suite, which truncates between tests and needs every test to start from
    the same known set.
    """
    with sync_engine.begin() as conn:
        if conn.execute(text("SELECT EXISTS (SELECT 1 FROM categories)")).scalar():
            return
        for sort, name in enumerate(sorted(DEFAULT_NAMES, key=str.lower)):
            conn.execute(
                text(
                    "INSERT INTO categories (name, roles, sort) "
                    "VALUES (:name, :roles, :sort) ON CONFLICT DO NOTHING"
                ),
                {"name": name, "roles": default_roles_for(name), "sort": sort},
            )
    _invalidate()


_COLUMNS = "id, name, color, roles, archived, sort, created_at, parent_id"

# Role lookups happen inside per-transaction loops, so they are cached for
# the life of the process and dropped whenever a category changes. A stale
# read here would misclassify a commitment, so every writer calls
# :func:`_invalidate` rather than relying on a timeout.
_roles_cache: Optional[Dict[str, Set[str]]] = None

# How long to stop trying after the table proves unreachable. These reads sit
# inside per-transaction loops, so retrying a dead connection once per row
# turns a DB outage into a timeout per row. Short enough that a blip costs
# one window of degraded classification, not a restart.
_UNAVAILABLE_BACKOFF_SECONDS = 30.0
_unavailable_until: float = 0.0


def _invalidate() -> None:
    global _roles_cache
    _roles_cache = None


def reset_caches() -> None:
    """Drop the role cache and any unavailability backoff.

    For the test suite, which truncates and re-seeds between tests: without
    this, one test simulating a DB outage leaves the backoff armed and every
    test that follows inside the window silently reads the fallback.
    """
    global _unavailable_until
    _unavailable_until = 0.0
    _invalidate()


def _mark_unavailable() -> None:
    global _unavailable_until
    _unavailable_until = time.monotonic() + _UNAVAILABLE_BACKOFF_SECONDS


def _is_unavailable() -> bool:
    return time.monotonic() < _unavailable_until


def _row(r) -> Dict[str, Any]:
    return {
        "id": r[0],
        "name": r[1],
        "color": r[2],
        "roles": list(r[3] or []),
        "archived": r[4],
        "sort": r[5],
        "created_at": r[6],
        "parent_id": r[7],
    }


def list_categories(include_archived: bool = True) -> List[Dict[str, Any]]:
    where = "" if include_archived else "WHERE NOT archived "
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT {_COLUMNS} FROM categories {where}ORDER BY sort, lower(name)")
        ).fetchall()
    return [_row(r) for r in rows]


def get_category(category_id: int) -> Optional[Dict[str, Any]]:
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {_COLUMNS} FROM categories WHERE id = :id"),
            {"id": category_id},
        ).fetchone()
    return _row(row) if row else None


def find_by_name(name: str) -> Optional[Dict[str, Any]]:
    cleaned = (name or "").strip()
    if not cleaned:
        return None
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {_COLUMNS} FROM categories WHERE lower(name) = lower(:n)"),
            {"n": cleaned},
        ).fetchone()
    return _row(row) if row else None


def names(include_archived: bool = False) -> List[str]:
    """Category names for the suggester and the client's pickers.

    Archived categories are excluded by default: archiving means "stop
    offering this", not "erase the history that used it".

    Returns an empty list when the table is unreachable, so the caller can
    fall back rather than fail — the suggester's vocabulary narrowing is a
    better outcome than the endpoint erroring.
    """
    if _is_unavailable():
        return []
    try:
        return [c["name"] for c in list_categories(include_archived)]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[categories] name lookup skipped: {e}")
        _mark_unavailable()
        return []


def names_with_role(role: str) -> frozenset:
    """Lowercased names carrying ``role``, for the classification sites.

    Returns the pre-table constant when the table cannot be read, so a DB
    hiccup degrades recurring detection to its old behavior rather than
    reclassifying everything.
    """
    global _roles_cache
    if role not in _FALLBACK:
        raise ValueError(f"unknown category role {role!r}; expected one of {ROLES}")

    if _roles_cache is None:
        if _is_unavailable():
            return _FALLBACK[role]
        try:
            with sync_engine.connect() as conn:
                rows = conn.execute(text("SELECT name, roles FROM categories")).fetchall()
        except Exception as e:
            logger.warning(f"[categories] role lookup fell back to defaults: {e}")
            _mark_unavailable()
            return _FALLBACK[role]

        # An empty table means "not seeded yet", not "the user cleared every
        # role" — treating it as the latter would reclassify every bill and
        # subscription the moment the table went missing.
        if not rows:
            return _FALLBACK[role]

        built: Dict[str, Set[str]] = {r: set() for r in ROLES}
        for name, roles in rows:
            for r in (roles or []):
                if r in built:
                    built[r].add((name or "").strip().lower())
        _roles_cache = built

    return frozenset(_roles_cache.get(role, set()))


def ensure_many(names) -> int:
    """Register any of ``names`` that has no row yet, and report how many.

    Called after an import: a bank sends labels nobody has seen before
    ("Supermarkets", "FoodDeliveryService"), and if those never become rows
    they cannot be renamed, merged or archived — which is exactly the drift
    that produced two spellings of the same category in the first place.

    Roles come from :func:`default_roles_for`, so a bank that starts sending
    "Transfers" is treated as non-spending immediately rather than counting
    as spending until someone notices.

    Best-effort: this runs inside the import and the categorize paths, and
    failing to register a label must never fail the import itself. Returns 0
    when the table is unreachable.
    """
    wanted = {
        (n or "").strip(): (n or "").strip().lower()
        for n in names
        if (n or "").strip()
    }
    if not wanted:
        return 0

    if _is_unavailable():
        return 0
    try:
        added = _insert_missing(wanted)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[categories] registration skipped: {e}")
        _mark_unavailable()
        return 0
    if added:
        _invalidate()
    return added


def _insert_missing(wanted: Dict[str, str]) -> int:
    added = 0
    with sync_engine.begin() as conn:
        existing = {
            r[0]
            for r in conn.execute(
                text("SELECT lower(name) FROM categories WHERE lower(name) = ANY(:names)"),
                {"names": list(wanted.values())},
            ).fetchall()
        }
        next_sort = conn.execute(
            text("SELECT COALESCE(MAX(sort), -1) + 1 FROM categories")
        ).scalar()
        for name, lowered in wanted.items():
            if lowered in existing:
                continue
            conn.execute(
                text(
                    "INSERT INTO categories (name, roles, sort) "
                    "VALUES (:name, :roles, :sort) ON CONFLICT DO NOTHING"
                ),
                {"name": name, "roles": default_roles_for(name), "sort": next_sort},
            )
            next_sort += 1
            added += 1
    return added


def create(name: str, color: Optional[str] = None, roles: Optional[List[str]] = None):
    cleaned = (name or "").strip()
    if not cleaned:
        return None
    existing = find_by_name(cleaned)
    if existing:
        return existing

    with sync_engine.begin() as conn:
        next_sort = conn.execute(
            text("SELECT COALESCE(MAX(sort), -1) + 1 FROM categories")
        ).scalar()
        row = conn.execute(
            text(
                "INSERT INTO categories (name, color, roles, sort) "
                f"VALUES (:name, :color, :roles, :sort) RETURNING {_COLUMNS}"
            ),
            {
                "name": cleaned,
                "color": color,
                "roles": _clean_roles(roles),
                "sort": next_sort,
            },
        ).fetchone()
    _invalidate()
    return _row(row)


def _clean_roles(roles: Optional[List[str]]) -> List[str]:
    if not roles:
        return []
    unknown = [r for r in roles if r not in ROLES]
    if unknown:
        raise ValueError(f"unknown category role(s) {unknown}; expected {ROLES}")
    return list(dict.fromkeys(roles))


def update(
    category_id: int,
    *,
    color: Optional[str] = None,
    roles: Optional[List[str]] = None,
    archived: Optional[bool] = None,
    sort: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Change everything except the name — :func:`rename` owns that.

    Kept apart because a rename has to touch four tables and this does not.
    """
    updates: Dict[str, Any] = {}
    if color is not None:
        updates["color"] = color
    if roles is not None:
        updates["roles"] = _clean_roles(roles)
    if archived is not None:
        updates["archived"] = archived
    if sort is not None:
        updates["sort"] = sort
    if not updates:
        return get_category(category_id)

    assignments = ", ".join(f"{k} = :{k}" for k in updates)
    with sync_engine.begin() as conn:
        row = conn.execute(
            text(
                f"UPDATE categories SET {assignments} WHERE id = :id "
                f"RETURNING {_COLUMNS}"
            ),
            {**updates, "id": category_id},
        ).fetchone()
    _invalidate()
    return _row(row) if row else None


def set_parent(category_id: int, parent_id: Optional[int]) -> Optional[Dict[str, Any]]:
    """Group ``category_id`` under ``parent_id``, or ungroup it with None.

    One level only. A category that already has children cannot be given a
    parent, and a category with a parent cannot become one — arbitrary depth
    would mean recursive rollups for a distinction nobody managing a
    household budget has asked for. Both refusals return None so the caller
    can say why rather than writing a tree that silently loses a level.
    """
    current = get_category(category_id)
    if current is None:
        return None

    if parent_id is None:
        return _write_parent(category_id, None)

    if parent_id == category_id:
        return None
    parent = get_category(parent_id)
    if parent is None or parent.get("parent_id") is not None:
        return None
    if children_of(category_id):
        return None

    return _write_parent(category_id, parent_id)


def _write_parent(category_id: int, parent_id: Optional[int]):
    with sync_engine.begin() as conn:
        row = conn.execute(
            text(
                "UPDATE categories SET parent_id = :parent WHERE id = :id "
                f"RETURNING {_COLUMNS}"
            ),
            {"parent": parent_id, "id": category_id},
        ).fetchone()
    _invalidate()
    return _row(row) if row else None


def children_of(category_id: int) -> List[Dict[str, Any]]:
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT {_COLUMNS} FROM categories WHERE parent_id = :id "
                 "ORDER BY sort, lower(name)"),
            {"id": category_id},
        ).fetchall()
    return [_row(r) for r in rows]


def rollup_map() -> Dict[str, str]:
    """``{child name lowercased: parent name}`` for every grouped category.

    The one thing the aggregations need: a lookup that turns a transaction's
    own category into the bucket it rolls up to. Categories with no parent
    are absent, so a caller falls back to the category's own name.

    Empty when the table is unreachable — an ungrouped rollup is the same
    answer this returned before grouping existed.
    """
    if _is_unavailable():
        return {}
    try:
        with sync_engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT c.name, p.name FROM categories c "
                    "JOIN categories p ON p.id = c.parent_id"
                )
            ).fetchall()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[categories] rollup lookup skipped: {e}")
        _mark_unavailable()
        return {}
    return {(child or "").strip().lower(): parent for child, parent in rows}


def roll_up(name: str, mapping: Optional[Dict[str, str]] = None) -> str:
    """The bucket ``name`` belongs to — its parent, or itself."""
    cleaned = (name or "").strip()
    if not cleaned:
        return cleaned
    if mapping is None:
        mapping = rollup_map()
    return mapping.get(cleaned.lower(), cleaned)


def rename(category_id: int, new_name: str) -> Optional[Dict[str, Any]]:
    """Rename a category everywhere it is written.

    Transactions keep the label denormalized, budgets are keyed by it, and
    rules target it by name — so all four writes land together or none do.
    Renaming onto a name that already exists is a merge, and says so rather
    than failing on the unique index.
    """
    cleaned = (new_name or "").strip()
    if not cleaned:
        return None
    current = get_category(category_id)
    if current is None:
        return None
    if cleaned.lower() == current["name"].lower():
        # Same category, different spelling: just restyle the label.
        return _write_name(category_id, current["name"], cleaned)

    clash = find_by_name(cleaned)
    if clash:
        return merge(category_id, clash["id"])
    return _write_name(category_id, current["name"], cleaned)


def _write_name(category_id: int, old_name: str, new_name: str):
    with sync_engine.begin() as conn:
        row = conn.execute(
            text(
                "UPDATE categories SET name = :new WHERE id = :id "
                f"RETURNING {_COLUMNS}"
            ),
            {"new": new_name, "id": category_id},
        ).fetchone()
        _relabel(conn, old_name, new_name)
    _invalidate()
    return _row(row) if row else None


def _relabel(conn, old_name: str, new_name: str) -> None:
    """Point every reference to ``old_name`` at ``new_name``.

    Case-insensitive on the way in, because the whole reason two labels
    diverge is that an import spelled one of them differently.
    """
    conn.execute(
        text(
            # CAST rather than ``:new::text`` — the ``::`` runs into the bind
            # parameter and text() reads it as part of the name.
            "UPDATE json_stores "
            "SET data = jsonb_set(data, '{category}', to_jsonb(CAST(:new AS text))) "
            "WHERE store_name = 'transactions' "
            "AND lower(trim(data->>'category')) = lower(:old)"
        ),
        {"new": new_name, "old": old_name},
    )
    # Budgets are keyed by category name, so a rename is a re-key. A budget
    # already under the new name wins — merging two caps by adding them would
    # invent a number the user never set.
    conn.execute(
        text(
            "DELETE FROM json_stores WHERE store_name = 'budgets' "
            "AND lower(trim(key)) = lower(:old) "
            "AND EXISTS (SELECT 1 FROM json_stores b WHERE b.store_name = 'budgets' "
            "            AND lower(trim(b.key)) = lower(:new))"
        ),
        {"old": old_name, "new": new_name},
    )
    # A budget carries its category in the row key *and* again inside the
    # payload, which is what the status endpoint reads — re-keying only half
    # of it leaves a budget that renders under its old name forever.
    conn.execute(
        text(
            "UPDATE json_stores SET key = :new, "
            "  data = jsonb_set(data, '{category}', to_jsonb(CAST(:new AS text))) "
            "WHERE store_name = 'budgets' AND lower(trim(key)) = lower(:old)"
        ),
        {"new": new_name, "old": old_name},
    )
    conn.execute(
        text(
            "UPDATE category_rules SET category = :new "
            "WHERE lower(trim(category)) = lower(:old)"
        ),
        {"new": new_name, "old": old_name},
    )


def merge(from_id: int, into_id: int) -> Optional[Dict[str, Any]]:
    """Fold one category into another and delete the empty one.

    This is what replaces editing ``category_normalizer.NORMALIZATION_MAP``
    and redeploying. The surviving row keeps its own name and color and
    gains the union of both role sets, since a role describes behavior the
    user chose and dropping half of it on a merge would change results.
    """
    if from_id == into_id:
        return get_category(into_id)
    source = get_category(from_id)
    target = get_category(into_id)
    if source is None or target is None:
        return None

    merged_roles = list(dict.fromkeys([*target["roles"], *source["roles"]]))
    with sync_engine.begin() as conn:
        _relabel(conn, source["name"], target["name"])
        conn.execute(
            text("DELETE FROM categories WHERE id = :id"), {"id": from_id}
        )
        row = conn.execute(
            text(
                "UPDATE categories SET roles = :roles WHERE id = :id "
                f"RETURNING {_COLUMNS}"
            ),
            {"roles": merged_roles, "id": into_id},
        ).fetchone()
    _invalidate()
    return _row(row) if row else None


def delete(category_id: int) -> Optional[Dict[str, Any]]:
    """Remove a category and clear it from every transaction using it.

    Budgets are left alone deliberately — a budget is a number the user set,
    and silently deleting it because its category went away loses data the
    category row never owned. The caller reports whether one survived.
    """
    current = get_category(category_id)
    if current is None:
        return None

    with sync_engine.begin() as conn:
        cleared = conn.execute(
            text(
                "UPDATE json_stores "
                "SET data = data - 'category' - 'category_source' "
                "WHERE store_name = 'transactions' "
                "AND lower(trim(data->>'category')) = lower(:name)"
            ),
            {"name": current["name"]},
        ).rowcount
        conn.execute(
            text(
                "DELETE FROM category_rules "
                "WHERE lower(trim(category)) = lower(:name)"
            ),
            {"name": current["name"]},
        )
        budget_exists = conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM json_stores WHERE store_name = 'budgets' "
                "AND lower(trim(key)) = lower(:name))"
            ),
            {"name": current["name"]},
        ).scalar()
        conn.execute(text("DELETE FROM categories WHERE id = :id"), {"id": category_id})
    _invalidate()
    return {
        "removed": current["name"],
        "cleared_txn_count": cleared,
        "budget_exists": bool(budget_exists),
    }


def counts() -> Dict[str, int]:
    """How many transactions carry each category, keyed by canonical name."""
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.name, count(j.*) FROM categories c "
                "LEFT JOIN json_stores j ON j.store_name = 'transactions' "
                "  AND lower(trim(j.data->>'category')) = lower(c.name) "
                "GROUP BY c.name"
            )
        ).fetchall()
    return {name: int(n or 0) for name, n in rows}
