from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import os
from typing import List, Dict, Any, Optional
import base64
import json
from csv_parser import parse_csv, Transaction, transactions_to_google_sheet_format, BankType
from gsheet_integration import append_to_sheet, get_sheet_headers

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
TELLER_API_KEY = os.getenv("TELLER_API_KEY")
TELLER_ENVIRONMENT = os.getenv("TELLER_ENVIRONMENT", "development")
TELLER_CERT_PATH = os.getenv("TELLER_CERT_PATH")
TELLER_KEY_PATH = os.getenv("TELLER_KEY_PATH")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SHEET_NAME = os.getenv("SHEET_NAME")
PERSON_1_NAME = os.getenv("PERSON_1_NAME", "Person 1")
PERSON_2_NAME = os.getenv("PERSON_2_NAME", "Person 2")

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

class Transaction(BaseModel):
    id: str
    account_id: str
    amount: str
    date: str
    description: str
    details: Dict[str, Any]
    status: str
    type: str

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

    if not TELLER_APP_ID or not TELLER_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Teller API credentials not configured"
        )

    # Create basic auth header
    credentials = base64.b64encode(f"{TELLER_APP_ID}:{TELLER_API_KEY}".encode()).decode()

    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json"
    }

    payload = {
        "user_id": request.user_id,
        "application_id": TELLER_APP_ID
    }

    async with httpx.AsyncClient() as client:
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

@app.get("/api/accounts", response_model=List[Account])
async def get_accounts(access_token: str):
    """Fetch user's bank accounts"""

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{TELLER_BASE_URL}/accounts",
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Failed to fetch accounts: {e.response.text}"
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Connection error: {str(e)}")

@app.get("/api/accounts/{account_id}/transactions", response_model=List[Dict])
async def get_transactions(account_id: str, access_token: str, count: int = 100):
    """Fetch transactions for a specific account and add to review queue"""

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    params = {"count": min(count, 500)}  # Limit to max 500

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{TELLER_BASE_URL}/accounts/{account_id}/transactions",
                headers=headers,
                params=params,
                timeout=30.0
            )
            response.raise_for_status()
            teller_transactions = response.json()

            # Convert Teller transactions to our format and store
            for t in teller_transactions:
                from csv_parser import Transaction, BankType

                transaction = Transaction(
                    date=t.get('date', ''),
                    description=t.get('description', ''),
                    amount=float(t.get('amount', 0)),
                    source=BankType.TELLER,
                    transaction_id=t.get('id'),
                    category=t.get('details', {}).get('category')
                )
                stored_transactions[transaction.transaction_id] = transaction.to_dict()

            return teller_transactions
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Failed to fetch transactions: {e.response.text}"
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Connection error: {str(e)}")

@app.get("/api/accounts/{account_id}/balance")
async def get_balance(account_id: str, access_token: str):
    """Get account balance"""

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{TELLER_BASE_URL}/accounts/{account_id}/balances",
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch balance: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

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