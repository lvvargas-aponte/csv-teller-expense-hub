"""One-shot importer: ``backend/*.json`` sidecars → ``json_stores`` table.

Idempotent via ``INSERT ... ON CONFLICT DO NOTHING``. After a successful
real run (not ``--check``) each processed file is renamed to
``<name>.json.migrated`` so accidental re-runs are visible.

Usage (inside the backend container):

    python scripts/migrate_json_to_pg.py            # real run
    python scripts/migrate_json_to_pg.py --check    # dry-run row counts only

``teller_cache.json`` is NOT imported into ``balance_snapshots`` — it is a
point-in-time cache, not history. Its four top-level keys (``fetched_at``,
``teller_accounts``, ``teller_cash``, ``teller_credit_debt``) become four
rows in ``json_stores`` under ``store_name='balances_cache'``, matching the
Phase 2 PgStore layout.

Conversations keep their nested ``messages`` list inside the JSONB payload
for now — Phase 6 rewrites the advisor to explode them into
``conversation_turns`` when the RAG slice ships.
"""
import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure ``db.base`` resolves regardless of cwd. Script is usually invoked
# from /app (backend/) inside the container, but handle other cases too.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy import text  # noqa: E402

from db.base import sync_engine  # noqa: E402

logger = logging.getLogger("migrate_json_to_pg")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# (file_name, store_name) for every JsonStore that was live in state.py
# before Phase 2.
SOURCES: list[tuple[str, str]] = [
    ("transactions.json",    "transactions"),
    ("manual_accounts.json", "manual_accounts"),
    ("teller_cache.json",    "balances_cache"),
    ("conversations.json",   "conversations"),
    ("budgets.json",         "budgets"),
    ("goals.json",           "goals"),
    ("account_details.json", "account_details"),
]


def _load_json(path: Path) -> dict | None:
    """Return the file's top-level dict, or None if missing/invalid."""
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"[parse-error] {path.name}: {e}")
        return None
    if not isinstance(parsed, dict):
        logger.error(
            f"[shape-error] {path.name}: expected dict at top level, got {type(parsed).__name__}"
        )
        return None
    return parsed


def migrate_file(path: Path, store_name: str, dry_run: bool) -> tuple[int, int]:
    """Insert every top-level key/value as a ``json_stores`` row.

    Returns ``(inserted, already_present)``. In dry-run mode these are the
    counts the script would insert / skip if run for real.
    """
    data = _load_json(path)
    if data is None:
        logger.info(f"[skip] {path.name}")
        return (0, 0)
    if not data:
        logger.info(f"[empty] {path.name} — nothing to migrate")
        return (0, 0)

    inserted = 0
    already = 0
    with sync_engine.begin() as conn:
        for key, value in data.items():
            if dry_run:
                exists = conn.execute(
                    text(
                        "SELECT 1 FROM json_stores WHERE store_name=:s AND key=:k"
                    ),
                    {"s": store_name, "k": str(key)},
                ).fetchone()
                if exists:
                    already += 1
                else:
                    inserted += 1
                continue

            result = conn.execute(
                text(
                    "INSERT INTO json_stores (store_name, key, data, updated_at) "
                    "VALUES (:s, :k, CAST(:d AS JSONB), NOW()) "
                    "ON CONFLICT (store_name, key) DO NOTHING"
                ),
                {
                    "s": store_name,
                    "k": str(key),
                    "d": json.dumps(value, default=str),
                },
            )
            if result.rowcount == 1:
                inserted += 1
            else:
                already += 1

    verb = "would insert" if dry_run else "inserted"
    logger.info(
        f"[{store_name}] {verb} {inserted}, {already} already present ({path.name})"
    )
    return (inserted, already)


def rename_processed(path: Path) -> None:
    """Move ``foo.json`` to ``foo.json.migrated`` so a second run is visible."""
    target = path.with_name(path.name + ".migrated")
    if target.exists():
        logger.warning(f"[rename-skip] {target.name} already exists")
        return
    path.rename(target)
    logger.info(f"[rename] {path.name} → {target.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Dry-run: report counts without inserting and without renaming files.",
    )
    args = parser.parse_args()

    if args.check:
        logger.info("Dry-run mode — no rows will be written, no files renamed.")

    total_inserted = 0
    total_already = 0
    files_with_data: list[Path] = []

    for filename, store_name in SOURCES:
        path = _BACKEND_DIR / filename
        inserted, already = migrate_file(path, store_name, args.check)
        total_inserted += inserted
        total_already += already
        if inserted and path.exists():
            files_with_data.append(path)

    logger.info(
        f"Totals: {total_inserted} "
        f"{'would be inserted' if args.check else 'inserted'}, "
        f"{total_already} already present"
    )

    if not args.check:
        # Rename every file that exists (even empty ones) so the operator can
        # see at a glance what has been processed. Files that didn't exist are
        # skipped automatically.
        for filename, _ in SOURCES:
            path = _BACKEND_DIR / filename
            if path.exists():
                rename_processed(path)

    # Final DB state summary
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT store_name, COUNT(*) FROM json_stores "
                "GROUP BY store_name ORDER BY store_name"
            )
        ).fetchall()
    logger.info("--- json_stores row counts after run ---")
    if not rows:
        logger.info("  (empty)")
    for store, count in rows:
        logger.info(f"  {store}: {count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
