"""One-shot backfill: stamp ``category_source`` on stored transactions.

Rows ingested after provenance existed carry the field already; this fills
it in for older ones so ``categorization_service`` has a source to compare
against instead of falling back to its legacy default on every check.

The hard part is that the pre-provenance data cannot say who set a label.
The default reading protects your work: a categorized row that is also
``reviewed`` is one you looked at, so it reads as ``manual``; everything
else reads as ``bank``. Getting this wrong in the protective direction
means a feed re-sync won't refresh a stale label; getting it wrong the
other way silently discards a category you typed.

``--all-bank`` takes the other reading — every existing category becomes
``bank``, and re-syncs are free to overwrite all of them.

Idempotent: rows that already carry a valid ``category_source`` are skipped.

Usage (inside the backend container):

    python -m scripts.backfill_category_source --check      # dry run
    python -m scripts.backfill_category_source
    python -m scripts.backfill_category_source --all-bank
"""
import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import categorization_service  # noqa: E402
from store import PgStore  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main(check: bool, all_bank: bool) -> int:
    store = PgStore("transactions", "transactions")
    planned: Counter = Counter()
    skipped = 0
    uncategorized = 0

    for tid, txn in store.items():
        existing = (txn.get("category_source") or "").strip().lower()
        if existing in categorization_service.SOURCES:
            skipped += 1
            continue

        if not (txn.get("category") or "").strip():
            # No category means no owner to record; leave the field absent so
            # the first writer claims it.
            uncategorized += 1
            continue

        if all_bank or not txn.get("reviewed"):
            source = categorization_service.BANK
        else:
            source = categorization_service.MANUAL

        planned[source] += 1
        if not check:
            txn["category_source"] = source
            store[tid] = txn  # explicit write-back per PgStore contract

    total = sum(planned.values())
    mode = "would stamp" if check else "stamped"
    logger.info(
        f"{mode} {total} transactions "
        f"({skipped} already stamped, {uncategorized} uncategorized):"
    )
    for source, n in sorted(planned.items()):
        logger.info(f"  {source:8s} x{n}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="dry run — report without writing"
    )
    parser.add_argument(
        "--all-bank",
        action="store_true",
        help="stamp every existing category as bank-sourced, ignoring `reviewed`",
    )
    args = parser.parse_args()
    sys.exit(main(check=args.check, all_bank=args.all_bank))
