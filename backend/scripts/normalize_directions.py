"""One-shot backfill: stamp the canonical ``direction`` field on stored transactions.

Records ingested after the field was added carry ``direction`` already; this
script fills it in for older rows using ``helpers.txn_direction``, which
encodes the legacy-Discover rule (purchases stored as ``credit`` are
outflows; only "Payments and Credits" rows are inflows).

Idempotent — rows that already have a valid ``direction`` are skipped.

Usage (inside the backend container):

    python -m scripts.normalize_directions --check    # dry-run, report only
    python -m scripts.normalize_directions            # real run
"""
import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from helpers import txn_direction  # noqa: E402
from store import PgStore  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main(check: bool) -> int:
    store = PgStore("transactions", "transactions")
    planned: Counter = Counter()
    skipped = 0
    for tid, txn in store.items():
        if txn.get("direction") in ("outflow", "inflow"):
            skipped += 1
            continue
        direction = txn_direction(txn)
        planned[(txn.get("source"), txn.get("transaction_type"), direction)] += 1
        if not check:
            txn["direction"] = direction
            store[tid] = txn

    total = sum(planned.values())
    mode = "would stamp" if check else "stamped"
    logger.info(f"{mode} {total} transactions ({skipped} already had direction):")
    for (source, ttype, direction), n in sorted(planned.items(), key=lambda kv: str(kv[0])):
        logger.info(f"  {source or '?':10s} {ttype or 'None':7s} -> {direction:8s} x{n}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="dry run — report without writing")
    sys.exit(main(check=parser.parse_args().check))