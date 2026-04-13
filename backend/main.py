import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import (
    TELLER_APP_ID, TELLER_ACCESS_TOKENS, TELLER_ENVIRONMENT,
    TELLER_CERT_PATH, TELLER_KEY_PATH, SPREADSHEET_ID, SHEET_NAME,
    PERSON_1_NAME, PERSON_2_NAME, CREDENTIALS_FILE,
)
from csv_parser import parse_csv, Transaction as CsvTransaction, BankType
from gsheet_integration import append_to_sheet, get_sheet_headers

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Teller mTLS setup
# ---------------------------------------------------------------------------
_TELLER_CERT = None
if TELLER_CERT_PATH and TELLER_KEY_PATH:
    if os.path.exists(TELLER_CERT_PATH) and os.path.exists(TELLER_KEY_PATH):
        _TELLER_CERT = (TELLER_CERT_PATH, TELLER_KEY_PATH)
        logger.info(f"[Teller] mTLS certificates loaded: {TELLER_CERT_PATH}")
    else:
        logger.warning("[Teller] cert paths set but files not found — running without mTLS")
else:
    logger.info("[Teller] No certificates configured (sandbox mode or not required)")


def teller_client() -> httpx.AsyncClient:
    """Return an httpx client pre-configured with Teller mTLS certs and a sensible timeout."""
    kwargs: Dict[str, Any] = {"timeout": httpx.Timeout(30.0, connect=10.0)}
    if _TELLER_CERT:
        kwargs["cert"] = _TELLER_CERT
    return httpx.AsyncClient(**kwargs)


TELLER_BASE_URL = "https://api.teller.io"

# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not SPREADSHEET_ID:
        logger.warning("SPREADSHEET_ID not configured — Google Sheets export will not work")
    if not TELLER_ACCESS_TOKENS:
        logger.warning("TELLER_API_KEY not configured — Teller sync will not work")
    if not CREDENTIALS_FILE.exists():
        logger.warning(
            f"credentials.json not found at {CREDENTIALS_FILE} — Google Sheets export will fail"
        )
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Bank Statement API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for parsed transactions (use a database in production)
stored_transactions: Dict[str, Dict[str, Any]] = {}

# Maps enrollment_id -> access_token so broken enrollments can be re-authenticated
_enrollment_token_map: Dict[str, str] = {}

# ---------------------------------------------------------------------------
# Token persistence helpers  (SRP: all .env / log I/O lives here)
# ---------------------------------------------------------------------------

_ENV_PATH = Path(__file__).parent.parent / ".env"
_LOG_PATH = Path(__file__).parent.parent / "teller-tokens.log"


def _get_enrollment_id(token: str) -> Optional[str]:
    """Reverse-lookup: return the enrollment_id associated with an access token."""
    return next((eid for eid, tok in _enrollment_token_map.items() if tok == token), None)


def _env_add_token(token: str) -> None:
    """Append an access token to TELLER_API_KEY in .env, creating the entry if absent."""
    try:
        env_text = _ENV_PATH.read_text(encoding="utf-8") if _ENV_PATH.exists() else ""
        if re.search(r"^TELLER_API_KEY=", env_text, re.MULTILINE):
            match = re.search(r"^TELLER_API_KEY=(.*)$", env_text, re.MULTILINE)
            existing = [t.strip() for t in (match.group(1) if match else "").split(",") if t.strip()]
            if token not in existing:
                existing.append(token)
            env_text = re.sub(
                r"^TELLER_API_KEY=.*$",
                "TELLER_API_KEY=" + ",".join(existing),
                env_text,
                flags=re.MULTILINE,
            )
        else:
            sep = "\n" if env_text and not env_text.endswith("\n") else ""
            env_text = env_text + sep + f"\nTELLER_API_KEY={token}\n"
        _ENV_PATH.write_text(env_text, encoding="utf-8")
        logger.info("[Teller] .env updated — token added.")
    except OSError as e:
        logger.error(f"[Teller] Could not write to .env: {e}")


def _env_remove_token(token: str) -> None:
    """Remove a specific access token from TELLER_API_KEY in .env."""
    try:
        if not _ENV_PATH.exists():
            return
        env_text = _ENV_PATH.read_text(encoding="utf-8")
        match = re.search(r"^TELLER_API_KEY=(.*)$", env_text, re.MULTILINE)
        if match:
            remaining = [t.strip() for t in match.group(1).split(",") if t.strip() and t.strip() != token]
            env_text = re.sub(
                r"^TELLER_API_KEY=.*$",
                "TELLER_API_KEY=" + ",".join(remaining),
                env_text,
                flags=re.MULTILINE,
            )
            _ENV_PATH.write_text(env_text, encoding="utf-8")
            logger.info("[Teller] .env updated — token removed.")
    except OSError as e:
        logger.error(f"[Teller] Could not update .env while removing token: {e}")


def _log_token_event(*, token: str, enrollment_id: str, institution: str, note: str = "") -> None:
    """Append an audit line to teller-tokens.log."""
    try:
        ts = datetime.now(timezone.utc).isoformat()
        parts = [
            ts,
            f"Env: {TELLER_ENVIRONMENT}",
            f"Institution: {institution}",
            f"Enrollment: {enrollment_id}",
            f"Token: {token}",
        ]
        if note:
            parts.append(f"Note: {note}")
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(" | ".join(parts) + "\n")
    except OSError as e:
        logger.warning(f"[Teller] Could not write to teller-tokens.log: {e}")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ConnectTokenRequest(BaseModel):
    user_id: str


class RegisterTokenRequest(BaseModel):
    access_token: str
    enrollment_id: str
    institution: str = ""


class ReplaceTokenRequest(BaseModel):
    old_enrollment_id: str   # identifies the broken token to remove
    new_access_token: str
    new_enrollment_id: str
    institution: str = ""


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
    person_1_owes: Optional[float] = None
    person_2_owes: Optional[float] = None
    notes: Optional[str] = None


class BulkTransactionUpdate(BaseModel):
    transaction_ids: List[str]
    is_shared: bool
    who: Optional[str] = None
    what: Optional[str] = None
    notes: Optional[str] = None
    split_evenly: bool = True  # if True, auto-calculate 50/50 from each transaction's amount


class TellerSyncRequest(BaseModel):
    from_date: Optional[str] = None         # YYYY-MM-DD; defaults to first day of previous month
    to_date: Optional[str] = None           # YYYY-MM-DD; defaults to last day of previous month
    count: int = 500                        # max transactions to fetch per account before date filtering
    account_ids: Optional[List[str]] = None # if set, only sync these account IDs (None = all)


class SendToSheetRequest(BaseModel):
    sheet_name:   Optional[str] = None   # overrides SHEET_NAME env var when provided
    filter_month: Optional[str] = None   # "YYYY-MM" — restrict to transactions in this month

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _previous_month_range():
    """Return (from_date, to_date) strings for the previous calendar month."""
    today = date.today()
    last = date(today.year, today.month, 1) - timedelta(days=1)
    first = date(last.year, last.month, 1)
    return first.isoformat(), last.isoformat()


def _decode_csv_bytes(raw: bytes) -> str:
    """Try common encodings in order; latin-1 never raises so it is the safe fallback."""
    for encoding in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode CSV file — unsupported encoding")


def _parse_month_key(date_str: str) -> Optional[str]:
    """Return 'YYYY-MM' from a MM/DD/YYYY or YYYY-MM-DD date string, or None."""
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m")
        except ValueError:
            continue
    return None

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {"message": "Bank Statement API is running"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "environment": TELLER_ENVIRONMENT}


@app.get("/api/config/teller")
async def get_teller_config():
    """Expose Teller public configuration to the frontend."""
    if not TELLER_APP_ID:
        raise HTTPException(status_code=503, detail="TELLER_APP_ID is not configured on the server.")
    return {"application_id": TELLER_APP_ID, "environment": TELLER_ENVIRONMENT}


@app.post("/api/teller/register-token", status_code=201)
async def register_teller_token(req: RegisterTokenRequest):
    """
    Persist a new Teller access token received from the frontend after enrollment.
    Adds to the in-memory token list (effective immediately), persists to .env,
    and appends an audit entry to teller-tokens.log.
    """
    token = req.access_token.strip()
    if not token:
        raise HTTPException(status_code=422, detail="access_token must not be empty.")

    if token in TELLER_ACCESS_TOKENS:
        logger.info(f"[Teller] Token {token[:8]}... already registered — skipping.")
        return {"registered": False, "reason": "duplicate", "total_tokens": len(TELLER_ACCESS_TOKENS)}

    TELLER_ACCESS_TOKENS.append(token)
    _enrollment_token_map[req.enrollment_id] = token
    logger.info(f"[Teller] New token {token[:8]}... added ({len(TELLER_ACCESS_TOKENS)} total).")

    _env_add_token(token)
    _log_token_event(token=token, enrollment_id=req.enrollment_id, institution=req.institution)

    return {"registered": True, "total_tokens": len(TELLER_ACCESS_TOKENS)}


@app.post("/api/teller/replace-token", status_code=200)
async def replace_teller_token(req: ReplaceTokenRequest):
    """
    Replace a broken token with a fresh one obtained via Teller Connect re-auth.
    Looks up the old token by enrollment_id, removes it, then registers the new one.
    """
    new_token = req.new_access_token.strip()
    if not new_token:
        raise HTTPException(status_code=422, detail="new_access_token must not be empty.")

    # 1. Find and remove the old token
    old_token = _enrollment_token_map.get(req.old_enrollment_id)
    if old_token and old_token in TELLER_ACCESS_TOKENS:
        TELLER_ACCESS_TOKENS.remove(old_token)
        logger.info(f"[Teller] Removed stale token {old_token[:8]}... for enrollment {req.old_enrollment_id}.")
        _env_remove_token(old_token)

    # 2. Register the new token (skip if already present — same token returned by Teller)
    if new_token not in TELLER_ACCESS_TOKENS:
        TELLER_ACCESS_TOKENS.append(new_token)

    # Update enrollment map; clean up old entry if the id changed
    _enrollment_token_map[req.new_enrollment_id] = new_token
    if req.old_enrollment_id != req.new_enrollment_id:
        _enrollment_token_map.pop(req.old_enrollment_id, None)

    _env_add_token(new_token)
    _log_token_event(
        token=new_token,
        enrollment_id=req.new_enrollment_id,
        institution=req.institution,
        note=f"replaced: {req.old_enrollment_id}",
    )
    logger.info(f"[Teller] Token replaced for enrollment {req.old_enrollment_id} → {req.new_enrollment_id}.")

    return {"replaced": True, "total_tokens": len(TELLER_ACCESS_TOKENS)}


@app.post("/api/connect-token")
async def create_connect_token(request: ConnectTokenRequest):
    """Generate a Teller Connect token for account linking"""
    if not TELLER_APP_ID:
        raise HTTPException(status_code=500, detail="TELLER_APP_ID not configured")

    async with teller_client() as client:
        try:
            response = await client.post(
                f"{TELLER_BASE_URL}/connect/token",
                headers={"Content-Type": "application/json"},
                json={"user_id": request.user_id, "application_id": TELLER_APP_ID},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Teller API error: {e.response.text}",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Connection error: {str(e)}")


@app.get("/api/accounts")
async def get_accounts():
    """Fetch bank accounts across all stored access tokens"""
    if not TELLER_ACCESS_TOKENS:
        return []

    def _error_entry(token: str, status_code=None) -> dict:
        return {
            "id": f"_error_{token[:8]}{token[-4:]}",
            "name": "Unknown account",
            "type": "",
            "subtype": "",
            "institution": {"name": "—"},
            "balance": {},
            "_connection_error": True,
            "_error_status": status_code,
            "_enrollment_id": _get_enrollment_id(token),
        }

    seen_ids: set = set()
    all_accounts = []
    async with teller_client() as client:
        for token in TELLER_ACCESS_TOKENS:
            try:
                response = await client.get(
                    f"{TELLER_BASE_URL}/accounts",
                    auth=(token, ""),
                )
                response.raise_for_status()
                accounts = response.json()
                for acct in accounts:
                    if acct["id"] not in seen_ids:
                        seen_ids.add(acct["id"])
                        acct["_teller_token"] = token
                        all_accounts.append(acct)
            except httpx.HTTPStatusError as e:
                logger.warning(
                    f"[Teller] Token {token[:8]}... failed ({e.response.status_code}): {e.response.text}"
                )
                all_accounts.append(_error_entry(token, e.response.status_code))
            except Exception as e:
                logger.warning(f"[Teller] Token {token[:8]}... error: {str(e)}")
                all_accounts.append(_error_entry(token))

    return all_accounts


@app.get("/api/accounts/{account_id}/transactions", response_model=List[Dict])
async def get_transactions(account_id: str, count: int = 100, access_token: Optional[str] = None):
    """Fetch transactions for a specific account"""
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
                    continue
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"Failed to fetch transactions: {e.response.text}",
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Connection error: {str(e)}")

    raise HTTPException(status_code=401, detail="No valid Teller token found for this account.")


@app.get("/api/accounts/{account_id}/balance")
async def get_balance(account_id: str, access_token: Optional[str] = None):
    """Get account balance"""
    tokens_to_try = ([access_token] if access_token else []) + TELLER_ACCESS_TOKENS
    if not tokens_to_try:
        raise HTTPException(status_code=500, detail="No Teller access token available.")

    async with teller_client() as client:
        for token in tokens_to_try:
            try:
                response = await client.get(
                    f"{TELLER_BASE_URL}/accounts/{account_id}/balances",
                    auth=(token, ""),
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    continue
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"Failed to fetch balance: {e.response.text}",
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to fetch balance: {str(e)}")

    raise HTTPException(status_code=401, detail="No valid Teller token found for this account.")


@app.post("/api/teller/sync")
async def sync_teller_transactions(req: TellerSyncRequest = None):
    """Pull transactions from ALL stored access tokens, filtered by date range."""
    if req is None:
        req = TellerSyncRequest()

    if not TELLER_ACCESS_TOKENS:
        raise HTTPException(
            status_code=500,
            detail="No Teller access tokens configured. Set TELLER_API_KEY in your .env file.",
        )

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
                )
                acct_resp.raise_for_status()
                accounts = acct_resp.json()

                for account in accounts:
                    if req.account_ids is not None and account["id"] not in req.account_ids:
                        continue
                    acct_name = (
                        f"{account.get('institution', {}).get('name', 'Bank')} "
                        f"– {account.get('name', account['id'])}"
                    )
                    try:
                        txn_resp = await client.get(
                            f"{TELLER_BASE_URL}/accounts/{account['id']}/transactions",
                            auth=(token, ""),
                            params={"count": min(req.count, 500)},
                        )
                        txn_resp.raise_for_status()
                        all_txns = txn_resp.json()

                        filtered = [
                            t for t in all_txns
                            if from_date <= t.get("date", "") <= to_date
                        ]

                        added = 0
                        acct_institution = account.get("institution", {}).get("name", "")
                        acct_type     = account.get("subtype", "") or account.get("type", "")
                        acct_category = account.get("type", "")   # broad: "depository" | "credit"

                        # Build running_balance sequence so we can infer CR/DR for depository
                        # accounts, where balance up = deposit (credit), balance down = withdrawal (debit).
                        # Credit accounts are excluded: their balance represents debt as a negative
                        # number, so a payment (money out) increases the balance and would be
                        # mislabelled as "credit" by the delta logic.
                        #
                        # IMPORTANT: Do NOT sort by date here. Teller's running_balance is only
                        # valid in Teller's native sequence. Sorting by date scrambles same-day
                        # transactions and breaks the balance chain (e.g. two payments on the same
                        # date end up in the wrong order, making the delta report the wrong sign).
                        # Teller returns transactions newest-first; reversing gives oldest-first,
                        # which preserves the running_balance chain correctly.
                        all_txns_sorted = list(reversed(all_txns))
                        balance_seq = [
                            (t["id"], float(t["running_balance"]))
                            for t in all_txns_sorted
                            if t.get("running_balance") is not None
                        ]
                        balance_index = {tid: i for i, (tid, _) in enumerate(balance_seq)}

                        def infer_txn_type(t, raw_amount):
                            tid = t.get("id")
                            idx = balance_index.get(tid)
                            teller_type = t.get("type", "")  # e.g. "card_payment", "ach", "transfer"
                            desc = t.get("description", "")

                            # Depository accounts: running_balance delta is the most reliable signal.
                            if acct_category == "depository" and idx is not None and idx > 0:
                                prev_bal = balance_seq[idx - 1][1]
                                curr_bal = balance_seq[idx][1]
                                result = "credit" if curr_bal > prev_bal else "debit"
                                logger.debug(f"[CR/DR] DELTA  | {desc!r:50s} | acct={acct_category} teller_type={teller_type!r} raw={raw_amount:+.2f} | idx={idx} prev={prev_bal:.2f} curr={curr_bal:.2f} → {result}")
                                return result

                            # Credit accounts: amount sign distinguishes charges (+) from
                            # credits (−). But negative amounts can be either a merchant
                            # refund OR a bill payment from the cardholder's bank.
                            # Heuristic: Teller uses type "card_payment" for both charges and
                            # merchant refunds (card-originated). Bill payments arrive via ACH /
                            # transfer / wire — a different type. If negative AND not card_payment,
                            # treat as a bill payment → debit (money left the cardholder's wallet).
                            if acct_category == "credit" and raw_amount < 0:
                                if teller_type == "card_payment":
                                    logger.debug(f"[CR/DR] CREDIT_REFUND | {desc!r:50s} | acct={acct_category} teller_type={teller_type!r} raw={raw_amount:+.2f} → credit")
                                    return "credit"   # merchant refund
                                logger.debug(f"[CR/DR] CREDIT_PMT   | {desc!r:50s} | acct={acct_category} teller_type={teller_type!r} raw={raw_amount:+.2f} → debit")
                                return "debit"        # bill payment from bank

                            # Fallback when running_balance is unavailable (pending txns,
                            # or first transaction in the window with no prior balance).
                            # Sign convention differs by account category:
                            #   depository: negative = withdrawal (debit), positive = deposit (credit)
                            #   credit:     negative = refund/payment (credit), positive = charge (debit)
                            if acct_category == "depository":
                                result = "debit" if raw_amount < 0 else "credit"
                                logger.debug(f"[CR/DR] FALLBACK| {desc!r:50s} | acct={acct_category} teller_type={teller_type!r} raw={raw_amount:+.2f} idx={idx} → {result}")
                                return result
                            result = "credit" if raw_amount < 0 else "debit"
                            logger.debug(f"[CR/DR] FALLBACK| {desc!r:50s} | acct={acct_category} teller_type={teller_type!r} raw={raw_amount:+.2f} idx={idx} → {result}")
                            return result

                        for t in filtered:
                            raw_amount = float(t.get("amount", 0))
                            txn = CsvTransaction(
                                date=t.get("date", ""),
                                description=t.get("description", ""),
                                amount=abs(raw_amount),
                                source=BankType.TELLER,
                                transaction_id=t.get("id"),
                                category=t.get("details", {}).get("category"),
                                institution=acct_institution,
                                transaction_type=infer_txn_type(t, raw_amount),
                                account_type=acct_type,
                            )
                            if txn.transaction_id not in stored_transactions:
                                stored_transactions[txn.transaction_id] = txn.to_dict()
                                added += 1
                            else:
                                # Upsert Teller-derived fields so logic fixes apply on re-sync
                                # without requiring a backend restart. User-edited fields are
                                # preserved (is_shared, who, what, notes, person_1_owes, person_2_owes).
                                existing = stored_transactions[txn.transaction_id]
                                for field in ("transaction_type", "account_type", "category",
                                              "institution", "description", "amount", "date"):
                                    existing[field] = getattr(txn, field)

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
                            enrollment_status = e.response.headers.get(
                                "teller-enrollment-status", ""
                            )
                        results.append({
                            "account": acct_name,
                            "error": str(e),
                            "enrollment_status": enrollment_status or None,
                        })

            except httpx.HTTPStatusError as e:
                results.append(
                    {"token": masked, "error": f"Auth failed ({e.response.status_code}): {e.response.text}"}
                )
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


@app.delete("/api/accounts/{account_id}")
async def delete_account(account_id: str):
    """Disconnect a specific Teller account from its enrollment."""
    if not TELLER_ACCESS_TOKENS:
        raise HTTPException(status_code=500, detail="No Teller access tokens configured.")

    # Error-placeholder accounts (id starts with "_error_") have no real Teller account to
    # call; just remove the broken token from memory and .env directly.
    if account_id.startswith("_error_"):
        # Find the token whose first-8 + last-4 chars match the id suffix
        suffix = account_id[len("_error_"):]   # e.g. "tok1234abcd"
        token_to_remove = next(
            (t for t in TELLER_ACCESS_TOKENS if f"{t[:8]}{t[-4:]}" == suffix),
            None,
        )
        if not token_to_remove:
            raise HTTPException(status_code=404, detail="No matching token found for this error account.")
        TELLER_ACCESS_TOKENS.remove(token_to_remove)
        enrollment_id = _get_enrollment_id(token_to_remove)
        if enrollment_id:
            _enrollment_token_map.pop(enrollment_id, None)
        _env_remove_token(token_to_remove)
        logger.info(f"[Teller] Removed broken token {token_to_remove[:8]}... (error account deleted).")
        return {"deleted": account_id}

    async with teller_client() as client:
        for token in TELLER_ACCESS_TOKENS:
            try:
                resp = await client.delete(
                    f"{TELLER_BASE_URL}/accounts/{account_id}",
                    auth=(token, ""),
                )
                if resp.status_code in (200, 204):
                    return {"deleted": account_id}
                if resp.status_code in (401, 403):
                    continue
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                continue
            except Exception as e:
                logger.warning(f"[Teller] Error deleting account {account_id}: {e}")
                continue

    raise HTTPException(status_code=404, detail="Account not found or no valid token could disconnect it.")


@app.post("/api/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    """Upload and parse bank statement CSV"""
    try:
        content = await file.read()
        content_str = _decode_csv_bytes(content)
        transactions = parse_csv(content_str, file.filename)

        new_transactions = []
        duplicates = 0
        for transaction in transactions:
            if transaction.transaction_id in stored_transactions:
                duplicates += 1
            else:
                stored_transactions[transaction.transaction_id] = transaction.to_dict()
                new_transactions.append(transaction)

        return {
            "message": f"Parsed {len(transactions)} transactions: {len(new_transactions)} new, {duplicates} already loaded",
            "count": len(new_transactions),
            "duplicates": duplicates,
            "transactions": [t.to_dict() for t in new_transactions],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse CSV: {str(e)}")


@app.get("/api/transactions/all")
async def get_all_transactions():
    """Get all transactions (CSV + Teller combined)"""
    return list(stored_transactions.values())


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
        "transactions": updated,
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
    """Export shared transactions in Google Sheet format (preview only, does not send)"""
    shared_transactions = [
        t for t in stored_transactions.values() if t.get("is_shared", False)
    ]

    rows = [
        {
            "Transaction Date": t["date"],
            "Description": t["description"],
            "Amount": t["amount"],
            "Who": t.get("who", ""),
            "What": t.get("what", ""),
            f"{PERSON_1_NAME} Owes": t.get("person_1_owes", 0.0),
            f"{PERSON_2_NAME} Owes": t.get("person_2_owes", 0.0),
            "Notes": t.get("notes", ""),
        }
        for t in shared_transactions
    ]

    return {
        "headers": [
            "Transaction Date", "Description", "Amount", "Who", "What",
            f"{PERSON_1_NAME} Owes", f"{PERSON_2_NAME} Owes", "Notes",
        ],
        "rows": rows,
    }


@app.post("/api/send-to-gsheet")
async def send_to_google_sheet(req: Optional[SendToSheetRequest] = None):
    """Send shared transactions directly to Google Sheet and clear them from the queue.

    Optional body fields:
    - sheet_name:   target worksheet name (overrides SHEET_NAME env var)
    - filter_month: "YYYY-MM" — restrict to transactions in this calendar month only
    """
    if not SPREADSHEET_ID:
        raise HTTPException(
            status_code=500,
            detail="Google Sheet ID not configured. Set SPREADSHEET_ID environment variable.",
        )

    req = req or SendToSheetRequest()
    effective_sheet = req.sheet_name or SHEET_NAME

    shared_transactions = [
        t for t in stored_transactions.values()
        if t.get("is_shared", False)
        and (
            req.filter_month is None
            or _parse_month_key(t.get("date", "")) == req.filter_month
        )
    ]

    if not shared_transactions:
        return {"message": "No shared transactions to send", "count": 0, "sheet_name": effective_sheet}

    # Collect IDs before writing — only delete AFTER confirmed success to avoid data loss
    ids_to_delete = [t["id"] for t in shared_transactions]

    try:
        count = append_to_sheet(SPREADSHEET_ID, shared_transactions, effective_sheet)

        for tid in ids_to_delete:
            stored_transactions.pop(tid, None)

        return {
            "message": f"Successfully sent {count} transactions to Google Sheet",
            "count": count,
            "sheet_name": effective_sheet,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send to Google Sheet: {str(e)}",
        )


@app.get("/api/gsheet/verify")
async def verify_gsheet_connection():
    """Verify Google Sheet connection and show headers"""
    if not SPREADSHEET_ID:
        raise HTTPException(status_code=500, detail="Google Sheet ID not configured")

    try:
        headers = get_sheet_headers(SPREADSHEET_ID, SHEET_NAME)
        expected = [
            "Transaction Date", "Description", "Amount", "Who", "What",
            f"{PERSON_1_NAME} Owes", f"{PERSON_2_NAME} Owes", "Notes",
        ]
        return {
            "connected": True,
            "sheet_id": SPREADSHEET_ID,
            "sheet_name": SHEET_NAME or "Default",
            "headers": headers,
            "headers_match": headers == expected,
            "expected_headers": expected,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to verify Google Sheet: {str(e)}"
        )


@app.get("/api/config/person-names")
async def get_person_names():
    """Get configured person names for the frontend"""
    return {"person_1": PERSON_1_NAME, "person_2": PERSON_2_NAME}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
