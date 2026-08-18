"""Google Sheets routes: connection verify and person names.

Writing to the spreadsheet belongs to ``sheet_sync`` — see ``routers/sync.py``.
The previous positional writer here emitted a column layout the live sheet
never had, and two writers disagreeing about its shape is exactly what the
sync contract exists to prevent.
"""
import logging

from fastapi import APIRouter, HTTPException

from config import SPREADSHEET_ID, SHEET_NAME, PERSON_1_NAME, PERSON_2_NAME
from gsheet_integration import get_sheet_headers
from sheet_sync.contract import build_headers

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/gsheet/verify")
async def verify_gsheet_connection():
    """Verify the Google Sheet connection and compare headers to the contract."""
    if not SPREADSHEET_ID:
        raise HTTPException(status_code=500, detail="Google Sheet ID not configured")

    try:
        headers = get_sheet_headers(SPREADSHEET_ID, SHEET_NAME)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to verify Google Sheet: {str(e)}"
        )

    expected = build_headers(PERSON_1_NAME, PERSON_2_NAME)
    return {
        "connected": True,
        "sheet_id": SPREADSHEET_ID,
        "sheet_name": SHEET_NAME or "Default",
        "headers": headers,
        "headers_match": headers == expected,
        "expected_headers": expected,
    }


@router.get("/config/person-names")
async def get_person_names():
    """Get configured person names for the frontend."""
    return {"person_1": PERSON_1_NAME, "person_2": PERSON_2_NAME}
