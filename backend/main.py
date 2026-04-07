from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import os
from typing import List, Dict, Any, Optional
import base64
import json
from csv_parser import parse_csv, Transaction as CsvTransaction, transactions_to_google_sheet_format, BankType
from gsheet_integration import append_to_sheet, get_sheet_headers
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

app = FastAPI(title="Bank Statement API", version="1.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Environment variables
TELLER_APP_ID = os.getenv("TELLER_APP_ID")
_raw_teller_key = os.getenv("TELLER_API_KEY", "")
TELLER_ACCESS_TOKENS = [t.strip() for t in _raw_teller_key.split(",") if t.strip()]
TELLER_ENVIRONMENT = os.getenv("TELLER_ENVIRONMENT", "development")
TELLER_CERT_PATH = os.getenv("TELLER_CERT_PATH")
TELLER_KEY_PATH = os.getenv("TELLER_KEY_PATH")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SHEET_NAME = os.getenv("SHEET_NAME")
PERSON_1_NAME = os.getenv("PERSON_1_NAME", "Person 1")
PERSON_2_NAME = os.getenv("PERSON_2_NAME", "Person 2")

# Build mTLS cert tuple once at startup — Teller requires client certs in non-sandbox mode
_TELLER_CERT = None
if TELLER_CERT_PATH and TELLER_KEY_PATH:
    if os.path.exists(TELLER_CERT_PATH) and os.path.exists(TELLER_KEY_PATH):
        _TELLER_CERT = (TELLER_CERT_PATH, TELLER_KEY_PATH)
        print(f"[Teller] mTLS certificates loaded: {TELLER_CERT_PATH}")
    else:
        print(f"[Teller] WARNING: cert paths set but files not found — running without mTLS")
else:
    print(f"[Teller] No certificates configured (sandbox mode or not required)")


def teller_client() -> httpx.AsyncClient:
    """Return an httpx client pre-configured with Teller mTLS certs and a sensible timeout."""
    kwargs = {"timeout": httpx.Timeout(30.0, connect=10.0)}
    if _TELLER_CERT:
        kwargs["cert"] = _TELLER_CERT
    return httpx.AsyncClient(**kwargs)

# Teller API base URL
TELLER_BASE_URL = "https://api.teller.io"

class ConnectTokenRequest(BaseModel):
    user_id: str

class Account(BaseModel):
    id: str
    name: str
    type: str
    subtype: str
    balance: Dict[str, Any]
    institution: Dict[str, Any]

class TransactionUpdate(BaseModel):
    is_shared: bool
    who: Optional[str] = None
    what: Optional[str] = None
    person_1_owes: Optional[float] = None  # Generic name
    person_2_owes: Optional[float] = None  # Generic name
    notes: Optional[str] = None

# In-memory storage for parsed transactions (use a database in production)
stored_transactions: Dict[str, Dict[str, Any]] = {}

@app.get("/")
async def root():
    return {"message": "Bank Statement API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "environment": TELLER_ENVIRONMENT}

@app.post("/api/connect-token")
async def create_connect_token(request: ConnectTokenRequest):
    """Generate a Teller Connect token for account linking"""

    if not TELLER_APP_ID:
        raise HTTPException(
            status_code=500,
            detail="TELLER_APP_ID not configured"
        )

    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "user_id": request.user_id,
        "application_id": TELLER_APP_ID
    }

    async with teller_client() as client:
        try:
            response = await client.post(
                f"{TELLER_BASE_URL}/connect/token",
                headers=headers,
                json=payload,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Teller API error: {e.response.text}"
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Connection error: {str(e)}")

@app.get("/api/accounts")
async def get_accounts():
    """Fetch bank accounts across all stored access tokens (reads TELLER_API_KEY from env)"""

    if not TELLER_ACCESS_TOKENS:
        raise HTTPException(
            status_code=500,
            detail="No Teller access tokens configured. Set TELLER_API_KEY in your .env file."
        )

    all_accounts = []
    async with teller_client() as client:
        for token in TELLER_ACCESS_TOKENS:
            try:
                response = await client.get(
                    f"{TELLER_BASE_URL}/accounts",
                    auth=(token, ""),
                    timeout=30.0
                )
                response.raise_for_status()
                accounts = response.json()
                # Tag each account with which token owns it (needed for transaction fetches)
                for acct in accounts:
                    acct["_teller_token"] = token
                all_accounts.extend(accounts)
            except httpx.HTTPStatusError as e:
                print(f"[Teller] Token {token[:8]}... failed ({e.response.status_code}): {e.response.text}")
            except Exception as e:
                print(f"[Teller] Token {token[:8]}... error: {str(e)}")

    return all_accounts


@app.get("/api/accounts/{account_id}/transactions", response_model=List[Dict])
async def get_transactions(account_id: str, count: int = 100, access_token: Optional[str] = None):
    """Fetch transactions for a specific account using stored tokens (or optional override token)"""

    # Prefer an explicitly passed token; fall back to first stored token
    tokens_to_try = ([access_token] if access_token else []) + TELLER_ACCESS_TOKENS
    if not tokens_to_try:
        raise HTTPException(status_code=500, detail="No Teller access token available.")

    params = {"count": min(count, 500)}

    async with teller_client() as client:
        for token in tokens_to_try:
            try:
                response = await client.get(
                    f"{TELLER_BASE_URL}/accounts/{account_id}/transactions",
                    auth=(token, ""),
                    params=params,
                    timeout=30.0
                )
                response.raise_for_status()
                teller_transactions = response.json()

                for t in teller_transactions:
                    transaction = CsvTransaction(
                        date=t.get("date", ""),
                        description=t.get("description", ""),
                        amount=float(t.get("amount", 0)),
                        source=BankType.TELLER,
                        transaction_id=t.get("id"),
                        category=t.get("details", {}).get("category"),
                    )
                    stored_transactions[transaction.transaction_id] = transaction.to_dict()

                return teller_transactions
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    continue  # try next token
                raise HTTPException(status_code=e.response.status_code,
                                    detail=f"Failed to fetch transactions: {e.response.text}")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Connection error: {str(e)}")

    raise HTTPException(status_code=401, detail="No valid Teller token found for this account.")


@app.get("/api/accounts/{account_id}/balance")
async def get_balance(account_id: str, access_token: Optional[str] = None):
    """Get account balance using stored tokens (or optional override token)"""

    tokens_to_try = ([access_token] if access_token else []) + TELLER_ACCESS_TOKENS
    if not tokens_to_try:
        raise HTTPException(status_code=500, detail="No Teller access token available.")

    async with teller_client() as client:
        for token in tokens_to_try:
            try:
                response = await client.get(
                    f"{TELLER_BASE_URL}/accounts/{account_id}/balances",
                    auth=(token, ""),
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    continue
                raise HTTPException(status_code=e.response.status_code,
                                    detail=f"Failed to fetch balance: {e.response.text}")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to fetch balance: {str(e)}")

    raise HTTPException(status_code=401, detail="No valid Teller token found for this account.")


class TellerSyncRequest(BaseModel):
    from_date: Optional[str] = None   # YYYY-MM-DD; if omitted, defaults to first day of previous month
    to_date: Optional[str] = None     # YYYY-MM-DD; if omitted, defaults to last day of previous month
    count: int = 500                  # max transactions to fetch per account before date filtering


def _previous_month_range():
    """Return (from_date, to_date) strings for the previous calendar month — mirrors index.js logic."""
    from datetime import date
    today = date.today()
    # last day of previous month
    last = date(today.year, today.month, 1) - __import__('datetime').timedelta(days=1)
    first = date(last.year, last.month, 1)
    return first.isoformat(), last.isoformat()


@app.post("/api/teller/sync")
async def sync_teller_transactions(req: TellerSyncRequest = None):
    """Pull transactions from ALL stored access tokens, filtered by date range.

    Mirrors the date-range logic from scripts/teller/index.js:
    - Teller returns all transactions; we filter client-side by date (same as JS).
    - Defaults to the previous calendar month when no dates are provided.
    - Skips duplicates already in the review queue.
    """
    if req is None:
        req = TellerSyncRequest()

    if not TELLER_ACCESS_TOKENS:
        raise HTTPException(
            status_code=500,
            detail="No Teller access tokens configured. Set TELLER_API_KEY in your .env file."
        )

    # Resolve date range — default to previous month exactly like index.js
    from_date, to_date = _previous_month_range()
    if req.from_date:
        from_date = req.from_date
    if req.to_date:
        to_date = req.to_date

    total_fetched = 0
    total_added = 0
    results = []

    async with teller_client() as client:
        for token in TELLER_ACCESS_TOKENS:
            masked = f"{token[:8]}...{token[-4:]}"
            try:
                acct_resp = await client.get(
                    f"{TELLER_BASE_URL}/accounts",
                    auth=(token, ""),
                    timeout=30.0,
                )
                acct_resp.raise_for_status()
                accounts = acct_resp.json()

                for account in accounts:
                    acct_name = (
                        f"{account.get('institution', {}).get('name', 'Bank')} "
                        f"– {account.get('name', account['id'])}"
                    )
                    try:
                        txn_resp = await client.get(
                            f"{TELLER_BASE_URL}/accounts/{account['id']}/transactions",
                            auth=(token, ""),
                            params={"count": min(req.count, 500)},
                            timeout=30.0,
                        )
                        txn_resp.raise_for_status()
                        all_txns = txn_resp.json()

                        # Client-side date filter — exactly like index.js getTellerTransactions()
                        filtered = [
                            t for t in all_txns
                            if from_date <= t.get("date", "") <= to_date
                        ]

                        added = 0
                        for t in filtered:
                            txn = CsvTransaction(
                                date=t.get("date", ""),
                                description=t.get("description", ""),
                                amount=float(t.get("amount", 0)),
                                source=BankType.TELLER,
                                transaction_id=t.get("id"),
                                category=t.get("details", {}).get("category"),
                            )
                            if txn.transaction_id not in stored_transactions:
                                stored_transactions[txn.transaction_id] = txn.to_dict()
                                added += 1

                        total_fetched += len(filtered)
                        total_added += added
                        results.append({
                            "account": acct_name,
                            "fetched": len(filtered),
                            "new": added,
                            "date_range": f"{from_date} → {to_date}",
                        })

                    except Exception as e:
                        enrollment_status = ""
                        if hasattr(e, "response") and e.response is not None:
                            enrollment_status = e.response.headers.get("teller-enrollment-status", "")
                        results.append({
                            "account": acct_name,
                            "error": str(e),
                            "enrollment_status": enrollment_status or None,
                        })

            except httpx.HTTPStatusError as e:
                results.append({"token": masked, "error": f"Auth failed ({e.response.status_code}): {e.response.text}"})
            except Exception as e:
                results.append({"token": masked, "error": str(e)})

    return {
        "message": f"Teller sync complete. {total_added} new transactions added ({from_date} → {to_date}).",
        "from_date": from_date,
        "to_date": to_date,
        "total_fetched": total_fetched,
        "total_new": total_added,
        "details": results,
    }


@app.post("/api/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    """Upload and parse bank statement CSV"""
    try:
        content = await file.read()
        content_str = content.decode('utf-8')

        # Parse CSV
        transactions = parse_csv(content_str, file.filename)

        # Store transactions
        for transaction in transactions:
            stored_transactions[transaction.transaction_id] = transaction.to_dict()

        return {
            "message": f"Successfully parsed {len(transactions)} transactions",
            "count": len(transactions),
            "transactions": [t.to_dict() for t in transactions]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse CSV: {str(e)}")

@app.get("/api/transactions/all")
async def get_all_transactions():
    """Get all transactions (CSV + Teller combined)"""
    return list(stored_transactions.values())

class BulkTransactionUpdate(BaseModel):
    transaction_ids: List[str]
    is_shared: bool
    who: Optional[str] = None
    what: Optional[str] = None
    notes: Optional[str] = None
    split_evenly: bool = True  # if True, auto-calculate 50/50 from each transaction's amount

@app.put("/api/transactions/bulk")
async def bulk_update_transactions(update: BulkTransactionUpdate):
    """Mark multiple transactions as shared or personal at once"""
    updated = []
    not_found = []

    for tid in update.transaction_ids:
        if tid not in stored_transactions:
            not_found.append(tid)
            continue

        t = stored_transactions[tid]
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

        stored_transactions[tid] = t
        updated.append(t)

    return {
        "updated": len(updated),
        "not_found": not_found,
        "transactions": updated
    }


@app.put("/api/transactions/{transaction_id}")
async def update_transaction(transaction_id: str, update: TransactionUpdate):
    """Update transaction with shared expense info"""
    if transaction_id not in stored_transactions:
        raise HTTPException(status_code=404, detail="Transaction not found")

    transaction = stored_transactions[transaction_id]
    transaction["is_shared"] = update.is_shared
    transaction["who"] = update.who
    transaction["what"] = update.what
    transaction["person_1_owes"] = update.person_1_owes or 0.0
    transaction["person_2_owes"] = update.person_2_owes or 0.0
    transaction["notes"] = update.notes or ""

    stored_transactions[transaction_id] = transaction
    return transaction

@app.get("/api/export/google-sheet")
async def export_to_google_sheet():
    """Export shared transactions in Google Sheet format"""
    shared_transactions = [
        t for t in stored_transactions.values()
        if t.get("is_shared", False)
    ]

    # Convert to Google Sheet format
    rows = []
    for t in shared_transactions:
        rows.append({
            "Transaction Date": t["date"],
            "Description": t["description"],
            "Amount": t["amount"],
            "Who": t.get("who", ""),
            "What": t.get("what", ""),
            f"{PERSON_1_NAME} Owes": t.get("person_1_owes", 0.0),
            f"{PERSON_2_NAME} Owes": t.get("person_2_owes", 0.0),
            "Notes": t.get("notes", "")
        })

    return {
        "headers": ["Transaction Date", "Description", "Amount", "Who", "What",
                    f"{PERSON_1_NAME} Owes", f"{PERSON_2_NAME} Owes", "Notes"],
        "rows": rows
    }

@app.post("/api/send-to-gsheet")
async def send_to_google_sheet():
    """Send shared transactions directly to Google Sheet and clear them"""
    if not SPREADSHEET_ID:
        raise HTTPException(
            status_code=500,
            detail="Google Sheet ID not configured. Set SPREADSHEET_ID environment variable."
        )

    shared_transactions = [
        t for t in stored_transactions.values()
        if t.get("is_shared", False)
    ]

    if not shared_transactions:
        return {"message": "No shared transactions to send", "count": 0}

    try:
        # Send to Google Sheet
        count = append_to_sheet(SPREADSHEET_ID, shared_transactions, SHEET_NAME)

        # Remove sent transactions from storage
        for t in shared_transactions:
            if t["id"] in stored_transactions:
                del stored_transactions[t["id"]]

        return {
            "message": f"Successfully sent {count} transactions to Google Sheet",
            "count": count
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send to Google Sheet: {str(e)}"
        )

@app.get("/api/gsheet/verify")
async def verify_gsheet_connection():
    """Verify Google Sheet connection and show headers"""
    if not SPREADSHEET_ID:
        raise HTTPException(
            status_code=500,
            detail="Google Sheet ID not configured"
        )

    try:
        headers = get_sheet_headers(SPREADSHEET_ID, SHEET_NAME)
        expected = ["Transaction Date", "Description", "Amount", "Who", "What",
                    f"{PERSON_1_NAME} Owes", f"{PERSON_2_NAME} Owes", "Notes"]

        return {
            "connected": True,
            "sheet_id": SPREADSHEET_ID,
            "sheet_name": SHEET_NAME or "Default",
            "headers": headers,
            "headers_match": headers == expected,
            "expected_headers": expected
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to verify Google Sheet: {str(e)}"
        )

@app.get("/api/config/person-names")
async def get_person_names():
    """Get configured person names for the frontend"""
    return {
        "person_1": PERSON_1_NAME,
        "person_2": PERSON_2_NAME
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)