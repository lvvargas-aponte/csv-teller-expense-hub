"""Transaction routes: CSV upload and transaction CRUD."""
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Form, HTTPException, UploadFile, File

import state
from csv_parser import CSVProcessorService
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
        for transaction in transactions:
            if resolved_account_id:
                transaction.account_id = resolved_account_id
            if transaction.transaction_id in state.stored_transactions:
                duplicates += 1
            else:
                state.stored_transactions[transaction.transaction_id] = transaction.to_dict()
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


@router.put("/transactions/bulk")
async def bulk_update_transactions(update: BulkTransactionUpdate):
    """Mark multiple transactions as shared or personal at once."""
    updated = []
    not_found = []

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

    state.stored_transactions[transaction_id] = transaction
    state._transactions_store.save()
    return transaction
