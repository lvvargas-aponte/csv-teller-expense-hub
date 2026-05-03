"""Google Sheets routes: export preview, send, and connection verify."""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

import state
from config import SPREADSHEET_ID, SHEET_NAME, PERSON_1_NAME, PERSON_2_NAME
from gsheet_integration import append_to_sheet, get_sheet_headers
from helpers import _parse_month_key
from models import SendToSheetRequest
from teller import _detail

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/export/google-sheet")
async def export_to_google_sheet():
    """Export shared transactions in Google Sheet format (preview only, does not send)."""
    shared_transactions = [
        t for t in state.stored_transactions.values() if t.get("is_shared", False)
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


@router.post("/send-to-gsheet")
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
        t for t in state.stored_transactions.values()
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
            state.stored_transactions.pop(tid, None)
        state._transactions_store.save()

        return {
            "message": f"Successfully sent {count} transactions to Google Sheet",
            "count": count,
            "sheet_name": effective_sheet,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=_detail(
                "Failed to send to Google Sheet.",
                f"Failed to send to Google Sheet: {str(e)}",
            ),
        )


@router.get("/gsheet/verify")
async def verify_gsheet_connection():
    """Verify Google Sheet connection and show headers."""
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


@router.get("/config/person-names")
async def get_person_names():
    """Get configured person names for the frontend."""
    return {"person_1": PERSON_1_NAME, "person_2": PERSON_2_NAME}
