"""One-shot backfill: rewrite transaction categories to canonical labels.

Usage:
    # Dry run — print the diff, write nothing:
    docker compose run --rm backend python -m scripts.normalize_categories --check

    # Live run — apply the mapping in-place:
    docker compose run --rm backend python -m scripts.normalize_categories

The mapping lives in ``backend/category_normalizer.py`` (single source of
truth shared with live ingest paths). This script is idempotent: a second
run after a successful first finds zero rows to change.

Reads / writes ``state.stored_transactions`` (PgStore-backed). Honors the
PgStore live-dict contract by writing each row back explicitly after
mutating the ``category`` field.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

# Make the backend package importable when invoked as ``python scripts/...``.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import state  # noqa: E402
from category_normalizer import normalize  # noqa: E402


def _scan() -> tuple[list[tuple[str, str, str]], Counter, int]:
    """Walk every transaction; collect proposed (txn_id, before, after) changes."""
    changes: list[tuple[str, str, str]] = []
    delta: Counter = Counter()
    total = 0
    for txn_id, txn in state.stored_transactions.items():
        total += 1
        before = txn.get("category")
        after = normalize(before)
        if (before or None) != (after or None):
            changes.append((txn_id, before or "", after or ""))
            delta[(before or "<none>", after or "<none>")] += 1
    return changes, delta, total


def _print_diff(changes: list[tuple[str, str, str]], delta: Counter, total: int) -> None:
    print(f"Scanned {total} transactions; {len(changes)} would change.\n")
    if not changes:
        print("Nothing to do — categories are already canonical.")
        return
    print("Per-mapping rollup (before → after, count):")
    for (before, after), count in sorted(delta.items(), key=lambda kv: -kv[1]):
        print(f"  {before!r:30s} → {after!r:30s} ({count})")


def _apply(changes: list[tuple[str, str, str]]) -> int:
    """Write each changed transaction back via PgStore."""
    written = 0
    for txn_id, _before, after in changes:
        txn = state.stored_transactions[txn_id]
        txn["category"] = after or None
        state.stored_transactions[txn_id] = txn  # explicit write-back per PgStore contract
        written += 1
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="Dry run — print the proposed diff and exit without writing.",
    )
    args = parser.parse_args()

    changes, delta, total = _scan()
    _print_diff(changes, delta, total)

    if args.check or not changes:
        return 0

    print()
    written = _apply(changes)
    print(f"Wrote {written} transactions.")
    # Re-scan to confirm idempotency.
    after_changes, _, _ = _scan()
    if after_changes:
        print(
            f"WARNING: {len(after_changes)} rows would still change on a "
            "second pass — mapping may not be idempotent."
        )
        return 1
    print("Verified idempotent — second pass found no further changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
