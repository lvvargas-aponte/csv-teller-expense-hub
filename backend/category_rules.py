"""Deterministic category rules — standing "always call this X" decisions.

The LLM suggester in ``categorizer.py`` proposes a category once, for one
transaction, and forgets it. A rule is the opposite: the user states a fact
about their own finances ("the Zelle to my landlord for $1,305.93 is Rent")
and every later import honours it without being asked again.

Rules live in the ``category_rules`` JSON store rather than a typed table —
the match kinds are open-ended and adding one shouldn't cost a migration.
Shape:

    {
      "id":               "rule_<hex12>",
      "match":            "description_contains" | "merchant_key",
      "value":            "Zelle payment to Luz Valeria",
      "amount":           1305.93 | None,             # None = any amount
      "transaction_type": "debit" | "credit" | None,  # None = either
      "category":         "Rent",
      "enabled":          True,
      "notes":            "",
      "created": iso, "updated": iso,
    }

Two deliberate choices:

* **Specificity-first evaluation** (see ``_sort_key``) — an amount-pinned
  rule beats an amount-less rule on the same merchant, ties breaking by
  creation time. Without that ordering, adding a broad catch-all later would
  silently start shadowing the precise rule the user wrote first.
* **Rules outrank the bank's own label.** SimpleFIN's category is a guess
  about a merchant; a rule is the account holder saying what the money was
  for. This matters on re-sync, where the incoming payload would otherwise
  overwrite the stored category every time (``routers/simplefin.py``).

``match_*`` takes an optional pre-loaded ``rules`` list so ingest loops read
the store once rather than once per transaction — the same shape
``properties.suggest_property_for_transactions`` uses for its rule matching.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import state

MATCH_TYPES = ("description_contains", "merchant_key")

# Half a cent. Amounts are two-decimal currency values that have round-tripped
# through JSON floats, so ``==`` is the wrong comparison: 1305.93 can arrive as
# 1305.9299999999998 and a rent payment would silently stop matching.
_AMOUNT_EPSILON = 0.005

# Cap on the ``changes`` list returned by ``apply_to_stored``. The counts are
# always exact; only the itemised preview is trimmed, so a first run over a
# multi-year history doesn't ship a 5,000-row payload to the browser.
_PREVIEW_LIMIT = 200


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def new_rule_id() -> str:
    return f"rule_{uuid.uuid4().hex[:12]}"


def _sort_key(rule: Dict[str, Any]) -> tuple:
    """Most specific first, then oldest first.

    Tier 0 = constrained by amount, tier 1 = merchant/description only.
    Creation time breaks ties so evaluation order is stable across restarts
    (dict ordering out of the store is not).
    """
    return (
        0 if rule.get("amount") is not None else 1,
        rule.get("created") or "",
        rule.get("id") or "",
    )


def list_rules(include_disabled: bool = True) -> List[Dict[str, Any]]:
    """Every rule, in evaluation order."""
    rules = list(state.category_rules.values())
    if not include_disabled:
        rules = [r for r in rules if r.get("enabled", True)]
    return sorted(rules, key=_sort_key)


def _amount_matches(rule_amount: Optional[float], txn_amount: Any) -> bool:
    """True when the rule doesn't constrain amount, or the amounts agree.

    Compares magnitudes: transactions are stored with a positive ``amount``
    and the direction carried in ``transaction_type``, so the user typing
    "1305.93" must match a $1,305.93 debit.
    """
    if rule_amount is None:
        return True
    try:
        txn = abs(float(txn_amount))
    except (TypeError, ValueError):
        return False
    return abs(txn - abs(float(rule_amount))) < _AMOUNT_EPSILON


def _type_matches(rule_type: Optional[str], txn_type: Any) -> bool:
    if not rule_type:
        return True
    return (txn_type or "").strip().lower() == rule_type


def _description_matches(rule: Dict[str, Any], description: Any) -> bool:
    value = (rule.get("value") or "").strip()
    if not value:
        return False
    text = description or ""
    if rule.get("match") == "merchant_key":
        # Same normalizer the recurring-charge grouping uses, so a rule keyed
        # on one month's description keeps matching when the bank appends a
        # different trailing reference number next month.
        from analytics import _normalize_merchant
        key = _normalize_merchant(text)
        return bool(key) and key == _normalize_merchant(value)
    return value.lower() in text.lower()


def match_rule(
    description: Any,
    amount: Any,
    transaction_type: Any = None,
    rules: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """First enabled rule matching all three constraints, or ``None``."""
    candidates = rules if rules is not None else list_rules()
    for rule in candidates:
        if not rule.get("enabled", True):
            continue
        if not _amount_matches(rule.get("amount"), amount):
            continue
        if not _type_matches(rule.get("transaction_type"), transaction_type):
            continue
        if _description_matches(rule, description):
            return rule
    return None


def match_category(
    description: Any,
    amount: Any,
    transaction_type: Any = None,
    rules: Optional[List[Dict[str, Any]]] = None,
) -> Optional[str]:
    """Category the rules assign to this transaction, or ``None``."""
    rule = match_rule(description, amount, transaction_type, rules=rules)
    return rule["category"] if rule else None


def apply_to_stored(
    rule_id: Optional[str] = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Run the rules across transactions already in the store.

    ``overwrite=False`` (the default) leaves any transaction that already has
    a category alone — a rule added today shouldn't quietly relabel a year of
    decisions someone made by hand. ``overwrite=True`` is the "no, I really do
    mean all of them" path the UI asks about explicitly.

    ``reviewed`` is never touched: assigning a category is prep work, not the
    review itself, which is the same contract the inline category editor and
    ``PUT /transactions/{id}`` follow.

    Returns ``{scanned, matched, changed, changes, truncated}`` where
    ``changes`` is capped at ``_PREVIEW_LIMIT`` items for display.
    """
    rules = list_rules(include_disabled=False)
    if rule_id:
        rules = [r for r in rules if r.get("id") == rule_id]

    scanned = 0
    matched = 0
    changes: List[Dict[str, Any]] = []
    pending: List[tuple] = []

    if rules:
        for tid, txn in state.stored_transactions.items():
            scanned += 1
            rule = match_rule(
                txn.get("description"),
                txn.get("amount"),
                txn.get("transaction_type"),
                rules=rules,
            )
            if rule is None:
                continue
            matched += 1

            current = (txn.get("category") or "").strip()
            target = rule["category"]
            if current.lower() == target.lower():
                continue          # already right — not a change
            if current and not overwrite:
                continue          # someone chose this; leave it

            pending.append((tid, txn, target))
            if len(changes) < _PREVIEW_LIMIT:
                changes.append({
                    "transaction_id": tid,
                    "date":           txn.get("date"),
                    "description":    txn.get("description"),
                    "amount":         txn.get("amount"),
                    "from_category":  current or None,
                    "to_category":    target,
                    "rule_id":        rule.get("id"),
                })

    if not dry_run:
        for tid, txn, target in pending:
            txn["category"] = target
            state.stored_transactions[tid] = txn   # explicit write-back per PgStore contract
        if pending:
            state._transactions_store.save()

    return {
        "scanned":   scanned,
        "matched":   matched,
        "changed":   len(pending),
        "changes":   changes,
        "truncated": len(pending) > len(changes),
    }
