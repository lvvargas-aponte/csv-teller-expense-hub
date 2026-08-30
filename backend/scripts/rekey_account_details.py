"""One-shot repair: move orphaned ``account_details`` rows onto current account ids.

Account ids come from whichever aggregator produced them, so switching
providers (Teller's ``acc_*`` ids -> SimpleFIN's ``ACT-*`` ids) leaves every
stored APR / credit limit / minimum payment attached to an id no live account
has any more. The data is still in the store; nothing reads it, so the
Accounts page shows blank limits and 0% utilization.

Matching is by institution first, then name similarity, because the two
providers rarely spell an account the same way ("Prime Visa" vs "Amazon Prime
Rewards Visa Signature (5637)"). That makes this a *proposal* tool: it prints
what it would do and writes nothing unless you pass --apply.

Only orphans are considered as sources, and only accounts with no meaningful
details of their own are considered as targets, so re-running is safe.

Usage (inside the backend container):

    python -m scripts.rekey_account_details                    # dry run
    python -m scripts.rekey_account_details --apply            # write
    python -m scripts.rekey_account_details --apply \
        --map acc_old123=ACT-new456 --map acc_old789=ACT-new012
"""
import argparse
import logging
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from institution_normalizer import normalize as normalize_institution  # noqa: E402
from store import PgStore  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Fields that make a details row worth preserving. A row of all-None (the
# placeholder the details endpoint writes on first read) is not worth moving,
# and a target holding only such a row is still free to receive one.
VALUE_FIELDS = ("apr", "credit_limit", "minimum_payment", "statement_day", "due_day")

# Below this name-similarity score a same-institution pair is reported but not
# applied automatically — use --map to force it.
MIN_SCORE = 0.30

_NOISE_RE = re.compile(r"\(.*?\)|[^a-z0-9 ]+")


def has_values(record: Optional[Dict[str, Any]]) -> bool:
    if not record:
        return False
    if any(record.get(f) is not None for f in VALUE_FIELDS):
        return True
    return bool((record.get("notes") or "").strip())


def name_score(a: str, b: str) -> float:
    """Similarity of two account names, ignoring parenthetical masks and case."""
    ca = _NOISE_RE.sub(" ", (a or "").lower()).split()
    cb = _NOISE_RE.sub(" ", (b or "").lower()).split()
    if not ca or not cb:
        return 0.0
    overlap = len(set(ca) & set(cb)) / min(len(set(ca)), len(set(cb)))
    ratio = SequenceMatcher(None, " ".join(ca), " ".join(cb)).ratio()
    return max(overlap, ratio)


def live_accounts() -> List[Dict[str, Any]]:
    """Every account the app currently shows, across providers.

    Read from the balances cache and the manual store rather than the
    ``accounts`` table: SimpleFIN rows live only in the cache, which is
    exactly why their ids drifted out of ``account_details`` in the first
    place.
    """
    cache = PgStore("balances_cache", "balances-cache")

    out: List[Dict[str, Any]] = []
    for key in ("simplefin_accounts", "snaptrade_accounts"):
        for a in cache.get(key) or []:
            out.append({
                "id": a.get("id"),
                "name": a.get("name") or "",
                "institution": normalize_institution(a.get("institution")),
                "type": a.get("type") or "",
            })

    manual = PgStore("manual_accounts", "manual-accounts")
    for a in manual.values():
        out.append({
            "id": a.get("id"),
            "name": a.get("name") or "",
            "institution": normalize_institution(a.get("institution")),
            "type": a.get("type") or "",
        })
    return [a for a in out if a["id"]]


def account_label(store_key: str, accounts_by_id: Dict[str, Dict[str, Any]]) -> str:
    """Human-readable name for a details key, using the archived accounts table."""
    a = accounts_by_id.get(store_key)
    if not a:
        return "(unknown account)"
    return f"{a['institution']} / {a['name']}"


def archived_accounts() -> Dict[str, Dict[str, Any]]:
    """Everything we still know about retired accounts, for naming the orphans.

    The ``accounts`` table keeps rows from providers the user has since left;
    the balances cache keeps their last-synced payload under a per-provider
    key. Both are read so an orphan can be described even if only one survived.
    """
    from sqlalchemy import text
    from db.base import sync_engine

    known: Dict[str, Dict[str, Any]] = {}

    cache = PgStore("balances_cache", "balances-cache")
    for key in ("teller_accounts", "simplefin_accounts", "snaptrade_accounts"):
        for a in cache.get(key) or []:
            if a.get("id"):
                known[a["id"]] = {
                    "id": a["id"],
                    "name": a.get("name") or "",
                    "institution": normalize_institution(a.get("institution")),
                    "type": a.get("type") or "",
                }

    with sync_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, name, institution, type FROM accounts")
        ).fetchall()
    for r in rows:
        known.setdefault(r[0], {
            "id": r[0],
            "name": r[1] or "",
            "institution": normalize_institution(r[2]),
            "type": r[3] or "",
        })
    return known


def plan(
    forced: Dict[str, str],
) -> Tuple[List[Tuple[str, str, float, str]], List[str], List[str]]:
    """Return (pairs, unmatched_orphans, skipped_targets).

    ``pairs`` is (old_id, new_id, score, reason), best match per orphan.
    """
    details = PgStore("account_details", "account-details")
    stored = {k: v for k, v in details.items()}
    live = live_accounts()
    live_ids = {a["id"] for a in live}
    archived = archived_accounts()

    orphans = [k for k, v in stored.items() if k not in live_ids and has_values(v)]
    taken: Dict[str, str] = {}
    pairs: List[Tuple[str, str, float, str]] = []
    unmatched: List[str] = []
    skipped: List[str] = []

    # Repeated re-enrollments leave several orphans competing for one live
    # account. Offer the richest first, most-recently-edited breaking ties —
    # it claims the target and the rest are reported as unmatched.
    def filled_count(k: str) -> int:
        rec = stored.get(k) or {}
        return sum(1 for f in VALUE_FIELDS if rec.get(f) is not None)

    orphans.sort(key=lambda k: str((stored.get(k) or {}).get("updated") or ""), reverse=True)
    orphans.sort(key=filled_count, reverse=True)

    for old_id in orphans:
        if old_id in forced:
            new_id = forced[old_id]
            pairs.append((old_id, new_id, 1.0, "forced by --map"))
            taken[new_id] = old_id
            continue

        src = archived.get(old_id) or {"name": "", "institution": "", "type": ""}
        candidates = []
        for a in live:
            if a["id"] in taken:
                continue
            if has_values(stored.get(a["id"])):
                skipped.append(a["id"])
                continue
            if src["institution"] and a["institution"] != src["institution"]:
                continue
            if src["type"] and a["type"] and a["type"] != src["type"]:
                continue
            candidates.append((name_score(src["name"], a["name"]), a))

        if not candidates:
            unmatched.append(old_id)
            continue

        candidates.sort(key=lambda c: c[0], reverse=True)
        score, best = candidates[0]
        # A lone same-institution, same-type candidate is convincing even when
        # the two providers named it nothing alike.
        reason = "only candidate for institution" if len(candidates) == 1 else "best name match"
        if score < MIN_SCORE and len(candidates) > 1:
            unmatched.append(old_id)
            continue
        pairs.append((old_id, best["id"], score, reason))
        taken[best["id"]] = old_id

    return pairs, unmatched, sorted(set(skipped))


def main(apply: bool, forced: Dict[str, str]) -> int:
    details = PgStore("account_details", "account-details")
    archived = archived_accounts()
    pairs, unmatched, skipped = plan(forced)
    live_by_id = {a["id"]: a for a in live_accounts()}

    if not pairs and not unmatched:
        logger.info("No orphaned account_details rows — nothing to do.")
        return 0

    mode = "WOULD MOVE" if not apply else "MOVED"
    for old_id, new_id, score, reason in pairs:
        record = dict(details[old_id])
        values = ", ".join(
            f"{f}={record.get(f)}" for f in VALUE_FIELDS if record.get(f) is not None
        )
        logger.info(
            f"{mode}  {account_label(old_id, archived)}\n"
            f"          {old_id}\n"
            f"       -> {live_by_id.get(new_id, {}).get('institution', '?')} / "
            f"{live_by_id.get(new_id, {}).get('name', '?')}\n"
            f"          {new_id}   [{reason}, score {score:.2f}]\n"
            f"          {values}"
        )
        if apply:
            record["account_id"] = new_id
            details[new_id] = record
            del details[old_id]

    for old_id in unmatched:
        logger.info(
            f"UNMATCHED {account_label(old_id, archived)} ({old_id}) — "
            f"pass --map {old_id}=<new-id> to place it"
        )
    for target in skipped:
        logger.info(
            f"target {target} already has its own details — left alone"
        )

    if not apply:
        logger.info("\nDry run. Re-run with --apply to write these changes.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the changes")
    parser.add_argument(
        "--map", action="append", default=[], metavar="OLD=NEW",
        help="force a specific old-id -> new-id move (repeatable)",
    )
    args = parser.parse_args()
    forced_pairs: Dict[str, str] = {}
    for item in args.map:
        if "=" not in item:
            parser.error(f"--map expects OLD=NEW, got {item!r}")
        old, new = item.split("=", 1)
        forced_pairs[old.strip()] = new.strip()
    sys.exit(main(apply=args.apply, forced=forced_pairs))
