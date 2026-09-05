"""Who is allowed to set a transaction's category, and who wins.

A category can arrive from four places, and until now the last writer won:
a SimpleFIN re-sync overwrote a label you typed (``routers/simplefin.py``
refreshes ``category`` on every seen transaction), and the Ollama suggester
had nothing stopping it either. That made automation unsafe — re-running
rules over history could quietly undo your work.

Every category write goes through :func:`apply`, which records where the
label came from in ``category_source`` and refuses a downgrade:

    manual > rule > bank > ai

Same-rank writes are allowed, so a bank re-sync still corrects a
bank-sourced label and you can always change your own mind.

The functions mutate the passed dict and do not persist. Callers hold a
snapshot out of ``state.stored_transactions`` and must write it back
themselves — see the PgStore live-dict contract.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

MANUAL = "manual"
RULE = "rule"
BANK = "bank"
AI = "ai"

SOURCES = (MANUAL, RULE, BANK, AI)

_RANK: Dict[str, int] = {AI: 0, BANK: 1, RULE: 2, MANUAL: 3}

# A row categorized before provenance existed carries no source. It came from
# a feed or a CSV, so it reads as BANK — the backfill script stamps the same
# value, and an unrecognized string is treated the same way rather than
# raising mid-ingest.
_LEGACY_SOURCE = BANK


def _clean(category: Optional[str]) -> Optional[str]:
    """Normalize a category argument; ``None`` and ``""`` both mean clear."""
    if category is None:
        return None
    stripped = category.strip()
    return stripped or None


def current_source(txn: Dict[str, Any]) -> Optional[str]:
    """The source now owning ``txn``'s category, or ``None`` if it has none."""
    if not _clean(txn.get("category")):
        return None
    raw = (txn.get("category_source") or "").strip().lower()
    return raw if raw in _RANK else _LEGACY_SOURCE


def can_assign(txn: Dict[str, Any], source: str) -> bool:
    """Whether ``source`` outranks whatever owns ``txn``'s category today.

    An uncategorized transaction is free for anyone to claim.
    """
    holder = current_source(txn)
    if holder is None:
        return True
    return _RANK.get(source, 0) >= _RANK[holder]


def apply(txn: Dict[str, Any], category: Optional[str], source: str) -> bool:
    """Set ``txn``'s category and provenance when ``source`` is allowed to.

    Returns whether the write happened, so a bulk caller can report how many
    rows a rule actually touched rather than how many it matched.

    Passing ``None`` or ``""`` clears the category, and clearing obeys the
    same precedence — the AI does not get to erase a label you typed.
    """
    if source not in _RANK:
        raise ValueError(f"unknown category source {source!r}; expected one of {SOURCES}")
    if not can_assign(txn, source):
        return False

    cleaned = _clean(category)
    txn["category"] = cleaned
    txn["category_source"] = source if cleaned else None
    return True


def stamp_ingest(txn: Dict[str, Any]) -> Dict[str, Any]:
    """Mark a freshly ingested row's category as bank-sourced.

    For the CSV and feed paths, which build a transaction dict from scratch
    rather than updating one — there is no prior owner to outrank.
    """
    txn["category_source"] = BANK if _clean(txn.get("category")) else None
    return txn


# ---------------------------------------------------------------------------
# Applying a rule to transactions that already exist
# ---------------------------------------------------------------------------
#
# A rule the user writes today is usually about spending they have already
# imported, so both the "…and 23 past transactions" count in the prompt and
# the sweep behind it live here — the precedence check is what makes the
# sweep safe to offer at all.


def _matches(txn: Dict[str, Any], rule: Dict[str, Any], alias_map) -> bool:
    import category_rules

    matched = category_rules.match_rule(
        txn.get("description") or "", [rule], alias_map
    )
    return matched is not None


def preview_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    """How many existing transactions ``rule`` would claim, and a sample.

    ``matched`` counts every transaction the rule describes; ``claimable``
    excludes the ones a higher source already owns, which is the number the
    user actually cares about before pressing apply.
    """
    import merchant_key
    import state

    alias_map = merchant_key.aliases()
    matched = 0
    claimable = 0
    sample: list = []

    for txn in state.stored_transactions.values():
        if not _matches(txn, rule, alias_map):
            continue
        matched += 1
        if can_assign(txn, RULE):
            claimable += 1
            if len(sample) < 5:
                sample.append({
                    "id": txn.get("id") or txn.get("transaction_id"),
                    "date": txn.get("date"),
                    "description": txn.get("description"),
                    "amount": txn.get("amount"),
                    "category": txn.get("category"),
                })

    return {
        "matched": matched,
        "claimable": claimable,
        "protected": matched - claimable,
        "sample": sample,
    }


def apply_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    """Set ``rule``'s category on every transaction it claims.

    Rows owned by a higher source are counted and skipped, never
    overwritten — that is the whole reason provenance exists. Returns the
    same shape as :func:`preview_rule` minus the sample, with ``updated``
    being what actually changed.
    """
    import merchant_key
    import state

    alias_map = merchant_key.aliases()
    matched = 0
    updated = 0

    for tid, txn in list(state.stored_transactions.items()):
        if not _matches(txn, rule, alias_map):
            continue
        matched += 1
        if apply(txn, rule.get("category"), RULE):
            state.stored_transactions[tid] = txn  # write-back per PgStore contract
            updated += 1

    if updated:
        import category_rules

        category_rules.touch([rule["id"]] if rule.get("id") else [])

    return {"matched": matched, "updated": updated, "protected": matched - updated}
