"""Transaction routes: CSV upload and transaction CRUD."""
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Form, HTTPException, UploadFile, File

import state
from csv_parser import CSVProcessorService, dedupe_key
from helpers import _decode_csv_bytes
from models import (
    TransactionUpdate,
    BulkTransactionUpdate,
    BulkSuggestRequest,
    ApplyCategoriesRequest,
)
from teller import _detail

logger = logging.getLogger(__name__)
router = APIRouter()


def _resolve_upload_account(
    *,
    account_id: Optional[str],
    institution: Optional[str],
    name: Optional[str],
    type_: Optional[str],
) -> Optional[str]:
    """Return the account id to attach this upload's transactions to.

    Three cases:
    * ``account_id`` supplied and exists in manual store → use it verbatim.
    * ``institution`` + ``name`` + ``type_`` supplied → create a new csv-synth
      account, register it in both the manual store and the structured
      accounts table, and return its new id.
    * Nothing supplied → return None and transactions stay unattached.
    """
    from db.accounts_repo import get_repo

    if account_id:
        if account_id not in state._manual_accounts:
            raise HTTPException(
                status_code=404,
                detail=f"account_id '{account_id}' not found among manual accounts",
            )
        return account_id

    if institution and name and type_:
        if type_ not in ("depository", "credit"):
            raise HTTPException(
                status_code=422,
                detail="type must be 'depository' or 'credit'",
            )
        new_id = f"csv_{uuid.uuid4().hex[:12]}"
        state._manual_accounts[new_id] = {
            "id":          new_id,
            "institution": institution,
            "name":        name,
            "type":        type_,
            "subtype":     "",
            "available":   0.0,
            "ledger":      0.0,
        }
        state._manual_accounts_store.save()
        get_repo().upsert_manual_account(
            account_id=new_id,
            institution=institution,
            name=name,
            type_=type_,
            source="csv",
        )
        return new_id

    return None


@router.post("/upload-csv")
async def upload_csv(
    file: UploadFile = File(...),
    account_id: Optional[str] = Form(None),
    institution: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    account_type: Optional[str] = Form(None, alias="type"),
    statement_balance: Optional[float] = Form(None),
    statement_date: Optional[str] = Form(None),
):
    """Upload and parse bank statement CSV.

    Optional statement metadata (``account_id`` OR ``institution``+``name``+
    ``type``, plus ``statement_balance`` and ``statement_date``) attaches
    the parsed transactions to an account and records a
    ``balance_snapshots`` row so the statement's closing balance shows up
    in timeseries dashboards. Omit all metadata for the pre-migration
    behavior (transactions stored with ``account_id = NULL``).
    """
    from db.accounts_repo import get_repo

    if file.content_type and file.content_type not in (
        "text/csv", "text/plain", "application/csv", "application/octet-stream"
    ):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")
    try:
        content = await file.read()
        if len(content) > state.CSV_UPLOAD_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large — maximum size is {state.CSV_UPLOAD_MAX_BYTES // (1024 * 1024)} MB.",
            )
        content_str = _decode_csv_bytes(content)
        processor = CSVProcessorService()
        transactions = processor.process_csv(content_str, file.filename)

        # Barclays CSVs embed the closing balance and date in the preamble.
        # Fall back to those values when the uploader didn't supply them.
        if statement_balance is None and processor.last_statement_balance is not None:
            statement_balance = processor.last_statement_balance
        if not statement_date and processor.last_statement_date:
            statement_date = processor.last_statement_date

        resolved_account_id = _resolve_upload_account(
            account_id=account_id,
            institution=institution,
            name=name,
            type_=account_type,
        )

        # Final fallback: if neither the form nor the CSV preamble supplied a
        # statement_balance, derive one by summing the parsed transactions.
        # ``amount`` is always positive — the sign comes from transaction_type.
        # For credit accounts the balance owed is debits − credits; for
        # depository accounts available cash is credits − debits.
        if (
            statement_balance is None
            and resolved_account_id
            and transactions
        ):
            acct_type = state._manual_accounts[resolved_account_id].get("type")
            if acct_type == "credit":
                derived = sum(
                    t.amount if t.transaction_type == "debit" else -t.amount
                    for t in transactions
                )
            else:
                derived = sum(
                    t.amount if t.transaction_type == "credit" else -t.amount
                    for t in transactions
                )
            statement_balance = round(derived, 2)

        new_transactions = []
        duplicates = 0
        # Build a snapshot of existing dedupe keys once so cross-source
        # duplicates (e.g. CSV row matching an already-Teller-imported txn) are
        # rejected even when transaction_ids differ. PgStore .values() is a
        # snapshot, so this is safe to read here.
        existing_keys = {
            dedupe_key(
                t.get("date"), t.get("amount"),
                t.get("description"), t.get("transaction_type"),
            )
            for t in state.stored_transactions.values()
        }
        for transaction in transactions:
            if resolved_account_id:
                transaction.account_id = resolved_account_id
            key = dedupe_key(
                transaction.date, transaction.amount,
                transaction.description, transaction.transaction_type,
            )
            if (
                transaction.transaction_id in state.stored_transactions
                or key in existing_keys
            ):
                duplicates += 1
            else:
                state.stored_transactions[transaction.transaction_id] = transaction.to_dict()
                existing_keys.add(key)
                new_transactions.append(transaction)

        if new_transactions:
            state._transactions_store.save()

        if resolved_account_id and statement_balance is not None:
            acct = state._manual_accounts[resolved_account_id]
            bal = float(statement_balance)
            if acct.get("type") == "credit":
                acct["ledger"] = bal
            else:
                acct["available"] = bal
            state._manual_accounts[resolved_account_id] = acct
            state._manual_accounts_store.save()

            get_repo().insert_balance_snapshot(
                account_id=resolved_account_id,
                source="csv",
                available=acct.get("available"),
                ledger=acct.get("ledger"),
                raw={
                    "statement_balance": bal,
                    "statement_date":    statement_date,
                    "filename":          file.filename,
                },
                captured_at=statement_date,
            )

        return {
            "message": (
                f"Parsed {len(transactions)} transactions: "
                f"{len(new_transactions)} new, {duplicates} already loaded"
            ),
            "count": len(new_transactions),
            "duplicates": duplicates,
            "account_id": resolved_account_id,
            "transactions": [t.to_dict() for t in new_transactions],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=_detail("Failed to parse CSV.", f"Failed to parse CSV: {str(e)}"),
        )


@router.get("/transactions/all")
async def get_all_transactions() -> List[Dict[str, Any]]:
    """Get all transactions (CSV + Teller combined)."""
    return list(state.stored_transactions.values())


def _purge_embeddings(transaction_ids: List[str]) -> None:
    """Best-effort cleanup of transaction_embeddings rows for deleted txns.

    Stale embedding rows are tolerated by the search path, so a DB failure
    here is logged and swallowed rather than failing the user's delete.
    """
    if not transaction_ids:
        return
    try:
        from db.base import sync_engine
        from sqlalchemy import text

        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM transaction_embeddings "
                    "WHERE transaction_id = ANY(:ids)"
                ),
                {"ids": transaction_ids},
            )
    except Exception as e:
        logger.warning(f"Failed to purge embeddings for {len(transaction_ids)} txns: {e}")


def _dedupe_winner(group: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pick which transaction to KEEP from a duplicate group.

    Priority: reviewed > has-category > is_shared > smallest id (stable).
    Higher-priority status survives so user edits are never lost to dedupe.
    """
    def rank(t: Dict[str, Any]) -> tuple:
        return (
            -1 if t.get("reviewed") else 0,
            -1 if (t.get("category") or "").strip() else 0,
            -1 if t.get("is_shared") else 0,
            str(t.get("transaction_id") or t.get("id") or ""),
        )
    return min(group, key=rank)


@router.post("/transactions/dedupe")
async def dedupe_transactions(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Find (and optionally remove) duplicate transactions.

    Two transactions are duplicates when they share the same canonical
    dedupe-key (date + 2dp amount + normalized description + direction) —
    catches the cross-source case where the same purchase exists as both a
    CSV row and a Teller-imported row with different transaction_ids.

    Modes:
      * ``preview`` (default) → returns groups, does not mutate.
      * ``apply``             → keeps the highest-priority txn per group
                                (reviewed > categorized > shared > smallest id)
                                and deletes the rest.
    """
    mode = (payload or {}).get("mode", "preview")
    if mode not in ("preview", "apply"):
        raise HTTPException(status_code=422, detail="mode must be 'preview' or 'apply'")

    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for tid, t in state.stored_transactions.items():
        key = dedupe_key(
            t.get("date"), t.get("amount"),
            t.get("description"), t.get("transaction_type"),
        )
        # Ensure the txn carries its own id in the snapshot for downstream use.
        t_with_id = dict(t)
        t_with_id.setdefault("transaction_id", tid)
        groups.setdefault(key, []).append(t_with_id)

    duplicate_groups = [g for g in groups.values() if len(g) > 1]

    if mode == "preview":
        return {
            "mode": "preview",
            "duplicate_count": sum(len(g) - 1 for g in duplicate_groups),
            "group_count": len(duplicate_groups),
            "groups": [
                {
                    "kept_id": _dedupe_winner(g).get("transaction_id"),
                    "transactions": g,
                }
                for g in duplicate_groups
            ],
        }

    removed_ids: List[str] = []
    for g in duplicate_groups:
        winner = _dedupe_winner(g)
        winner_id = winner.get("transaction_id")
        for t in g:
            tid = t.get("transaction_id")
            if tid and tid != winner_id and tid in state.stored_transactions:
                del state.stored_transactions[tid]
                removed_ids.append(tid)

    if removed_ids:
        state._transactions_store.save()
        _purge_embeddings(removed_ids)

    return {
        "mode": "apply",
        "removed_count": len(removed_ids),
        "group_count": len(duplicate_groups),
        "removed_ids": removed_ids,
    }


@router.delete("/transactions/{transaction_id}", status_code=204)
async def delete_transaction(transaction_id: str):
    """Remove a single transaction. Also drops its embedding row."""
    if transaction_id not in state.stored_transactions:
        raise HTTPException(status_code=404, detail="Transaction not found")
    del state.stored_transactions[transaction_id]
    state._transactions_store.save()
    _purge_embeddings([transaction_id])
    return None


@router.put("/transactions/bulk")
async def bulk_update_transactions(update: BulkTransactionUpdate):
    """Mark multiple transactions as shared or personal at once."""
    updated = []
    not_found = []

    transfer_target: Optional[str] = None
    if update.transfer_to_account_id is not None:
        target = update.transfer_to_account_id.strip()
        if target and target not in state._manual_accounts:
            raise HTTPException(
                status_code=422,
                detail=f"transfer_to_account_id '{target}' is not a manual account",
            )
        transfer_target = target or ""  # "" sentinel = clear

    for tid in update.transaction_ids:
        if tid not in state.stored_transactions:
            not_found.append(tid)
            continue

        t = state.stored_transactions[tid]
        t["is_shared"] = update.is_shared
        t["who"] = update.who or t.get("who", "")
        t["what"] = update.what or t.get("what", "")
        t["notes"] = update.notes or t.get("notes", "")

        if update.is_shared and update.split_evenly:
            half = round(abs(float(t.get("amount", 0))) / 2, 2)
            t["person_1_owes"] = half
            t["person_2_owes"] = half
        elif not update.is_shared:
            t["person_1_owes"] = 0.0
            t["person_2_owes"] = 0.0

        # Any user-initiated update (shared or personal) records intent → reviewed.
        t["reviewed"] = True if update.reviewed is None else bool(update.reviewed)

        if update.category is not None:
            t["category"] = update.category

        if transfer_target is not None:
            t["transfer_to_account_id"] = transfer_target or None

        state.stored_transactions[tid] = t
        updated.append(t)

    if updated:
        state._transactions_store.save()
    return {
        "updated": len(updated),
        "not_found": not_found,
        "transactions": updated,
    }


@router.post("/transactions/suggest-categories/bulk")
async def bulk_suggest_categories(req: BulkSuggestRequest):
    """Ask the local LLM to suggest categories for many transactions at once.

    Skips transactions that already have a non-empty category — this is a
    fill-in-the-blanks tool, not a re-categorizer. Mutates nothing; the
    caller previews the suggestions and confirms via PUT /transactions/categories.
    """
    from categorizer import suggest_category, known_categories

    candidates = known_categories()
    results: List[Dict[str, Any]] = []
    skipped_ids: List[str] = []
    not_found: List[str] = []
    ai_available = True

    for tid in req.transaction_ids:
        if tid not in state.stored_transactions:
            not_found.append(tid)
            continue
        txn = state.stored_transactions[tid]
        if (txn.get("category") or "").strip():
            skipped_ids.append(tid)
            continue

        try:
            amount = float(txn.get("amount") or 0.0)
        except (TypeError, ValueError):
            amount = 0.0

        out = await suggest_category(
            description=txn.get("description", "") or "",
            amount=amount,
            known=candidates,
        )
        if not out["ai_available"]:
            ai_available = False
        results.append({
            "id": tid,
            "description": txn.get("description", "") or "",
            "amount": amount,
            "suggested_category": out["category"],
        })

    return {
        "ai_available": ai_available,
        "candidates":   candidates,
        "results":      results,
        "skipped_ids":  skipped_ids,
        "not_found":    not_found,
    }


@router.put("/transactions/bulk/reviewed")
async def bulk_set_reviewed(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Flip the ``reviewed`` flag on many transactions at once.

    Touches only ``reviewed`` — leaves is_shared, owed amounts, category, etc.
    untouched. Used by the Current-view "Mark reviewed" bulk action and by
    the per-row ✓ toggle, which both treat reviewed as an independent
    triage state.
    """
    ids = payload.get("transaction_ids") or []
    if not isinstance(ids, list):
        raise HTTPException(status_code=422, detail="transaction_ids must be a list.")
    reviewed = bool(payload.get("reviewed", True))

    updated: List[Dict[str, Any]] = []
    not_found: List[str] = []
    for tid in ids:
        if tid not in state.stored_transactions:
            not_found.append(tid)
            continue
        t = state.stored_transactions[tid]
        t["reviewed"] = reviewed
        state.stored_transactions[tid] = t
        updated.append(t)

    if updated:
        state._transactions_store.save()
    return {"updated": len(updated), "not_found": not_found}


@router.get("/categories")
async def list_categories() -> Dict[str, List[str]]:
    """Return all known categories: union of distinct transaction categories,
    budget categories, and categorizer defaults. Case-insensitive dedup,
    sorted alphabetically.
    """
    from categorizer import known_categories

    return {"categories": sorted(known_categories(), key=str.lower)}


@router.delete("/categories/{name}")
async def delete_category(name: str) -> Dict[str, Any]:
    """Remove a category from circulation by clearing it on every transaction
    that uses it (case-insensitive). Leaves Budget rows alone — the caller
    can decide whether to also delete the budget.
    """
    target = (name or "").strip().lower()
    if not target:
        raise HTTPException(status_code=422, detail="Category name is required.")

    cleared = 0
    for tid, txn in list(state.stored_transactions.items()):
        current = (txn.get("category") or "").strip().lower()
        if current == target:
            txn["category"] = None
            state.stored_transactions[tid] = txn
            cleared += 1

    if cleared:
        state._transactions_store.save()

    budget_exists = bool(state.budgets) and any(
        (k or "").strip().lower() == target for k in state.budgets.keys()
    )

    return {
        "removed": name,
        "cleared_txn_count": cleared,
        "budget_exists": budget_exists,
    }


# Static-path PUT defined BEFORE the catch-all PUT below so FastAPI's
# in-order matching doesn't route /transactions/categories into
# /transactions/{transaction_id}.
@router.put("/transactions/categories")
async def apply_categories(req: ApplyCategoriesRequest):
    """Apply a list of {transaction_id, category} assignments.

    Each accepted assignment also flips ``reviewed=True`` because the user
    explicitly chose a category. Empty-string category clears.
    """
    updated: List[Dict[str, Any]] = []
    not_found: List[str] = []

    for item in req.items:
        if item.transaction_id not in state.stored_transactions:
            not_found.append(item.transaction_id)
            continue
        t = state.stored_transactions[item.transaction_id]
        t["category"] = item.category
        t["reviewed"] = True
        state.stored_transactions[item.transaction_id] = t
        updated.append(t)

    if updated:
        state._transactions_store.save()
    return {"updated": len(updated), "not_found": not_found}


@router.put("/transactions/{transaction_id}")
async def update_transaction(transaction_id: str, update: TransactionUpdate):
    """Update transaction with shared expense info."""
    if transaction_id not in state.stored_transactions:
        raise HTTPException(status_code=404, detail="Transaction not found")

    transaction = state.stored_transactions[transaction_id]
    transaction["is_shared"] = update.is_shared
    transaction["who"] = update.who or ""
    transaction["what"] = update.what or ""
    transaction["person_1_owes"] = update.person_1_owes or 0.0
    transaction["person_2_owes"] = update.person_2_owes or 0.0
    transaction["notes"] = update.notes or ""
    # Any user-initiated update records intent → reviewed (client may override).
    transaction["reviewed"] = True if update.reviewed is None else bool(update.reviewed)

    if update.category is not None:
        transaction["category"] = update.category

    if update.transaction_type is not None:
        transaction["transaction_type"] = update.transaction_type

    if update.transfer_to_account_id is not None:
        target = update.transfer_to_account_id.strip()
        if target and target not in state._manual_accounts:
            raise HTTPException(
                status_code=422,
                detail=f"transfer_to_account_id '{target}' is not a manual account",
            )
        transaction["transfer_to_account_id"] = target or None

    state.stored_transactions[transaction_id] = transaction
    state._transactions_store.save()
    return transaction
