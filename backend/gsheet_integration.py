"""
Google Sheets Integration Module
"""
import gspread
from google.oauth2.service_account import Credentials
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

from config import CREDENTIALS_FILE

logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]


# ---------------------------------------------------------------------------
# Custom exceptions — allow callers to distinguish error categories
# ---------------------------------------------------------------------------

class GoogleSheetsError(Exception):
    """Base class for Google Sheets errors"""


class AuthenticationError(GoogleSheetsError):
    """Raised when credentials are invalid or missing"""


class SheetNotFoundError(GoogleSheetsError):
    """Raised when the spreadsheet or worksheet cannot be found"""


@dataclass
class SheetConfig:
    """Configuration for Google Sheet access"""
    spreadsheet_id: str
    sheet_name: Optional[str] = None

    @classmethod
    def from_env(cls):
        """Create config from environment variables"""
        from config import SPREADSHEET_ID, SHEET_NAME
        if not SPREADSHEET_ID:
            raise ValueError("SPREADSHEET_ID environment variable not set")
        return cls(spreadsheet_id=SPREADSHEET_ID, sheet_name=SHEET_NAME)


class GoogleSheetsClient:
    """Handle Google Sheets authentication and client creation."""

    def __init__(self, credentials_file=None):
        # Default to the absolute path from config so this works from any cwd
        self.credentials_file = str(credentials_file or CREDENTIALS_FILE)
        self._client = None

    def get_client(self) -> gspread.Client:
        """Get or create authenticated Google Sheets client."""
        if self._client is None:
            self._client = self._authenticate()
        return self._client

    def _authenticate(self) -> gspread.Client:
        """Authenticate with Google Sheets API."""
        if not os.path.exists(self.credentials_file):
            raise AuthenticationError(
                f"Google credentials file not found: {self.credentials_file}\n"
                "Please download your service account JSON from Google Cloud Console\n"
                f"and save it as 'credentials.json' in the backend folder."
            )

        try:
            creds = Credentials.from_service_account_file(
                self.credentials_file,
                scopes=SCOPES,
            )
            return gspread.authorize(creds)
        except Exception as e:
            logger.error(f"Failed to authenticate with Google: {str(e)}")
            raise AuthenticationError(f"Failed to authenticate with Google: {str(e)}") from e


class SheetRepository:
    """Handle worksheet read/write operations."""

    def __init__(self, client: GoogleSheetsClient):
        self.client = client

    def get_worksheet(self, config: SheetConfig):
        """Get worksheet from spreadsheet."""
        try:
            gc = self.client.get_client()
            spreadsheet = gc.open_by_key(config.spreadsheet_id)
            if config.sheet_name:
                return spreadsheet.worksheet(config.sheet_name)
            return spreadsheet.sheet1
        except (AuthenticationError, GoogleSheetsError):
            raise
        except Exception as e:
            logger.error(f"Failed to access worksheet: {str(e)}")
            raise SheetNotFoundError(f"Failed to access worksheet: {str(e)}") from e

    def get_headers(self, config: SheetConfig) -> List[str]:
        """Get headers from the sheet."""
        try:
            worksheet = self.get_worksheet(config)
            return worksheet.row_values(1)
        except (AuthenticationError, SheetNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to read sheet headers: {str(e)}")
            raise SheetNotFoundError(f"Failed to read sheet headers: {str(e)}") from e


class GoogleSheetsService:
    """Facade — simplified interface for Google Sheets operations."""

    def __init__(self, config: SheetConfig):
        self.config = config
        self.client = GoogleSheetsClient()
        self.repository = SheetRepository(self.client)

    def verify_headers(self) -> Dict[str, Any]:
        """Compare the worksheet's headers against the sync contract."""
        from config import PERSON_1_NAME, PERSON_2_NAME
        from sheet_sync.contract import build_headers

        headers = self.repository.get_headers(self.config)
        expected = build_headers(PERSON_1_NAME, PERSON_2_NAME)
        return {
            "connected": True,
            "sheet_id": self.config.spreadsheet_id,
            "sheet_name": self.config.sheet_name or "Default",
            "headers": headers,
            "headers_match": headers == expected,
            "expected_headers": expected,
        }


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def get_sheet_headers(
        spreadsheet_id: str,
        sheet_name: Optional[str] = None,
) -> List[str]:
    """Get headers from Google Sheet."""
    config = SheetConfig(spreadsheet_id=spreadsheet_id, sheet_name=sheet_name)
    service = GoogleSheetsService(config)
    return service.repository.get_headers(config)
