"""
Google Sheets Integration Module
"""
import gspread
from google.oauth2.service_account import Credentials
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

# Setup logging
logger = logging.getLogger(__name__)

# Constants
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
CREDENTIALS_FILE = 'credentials.json'


def get_expected_headers() -> List[str]:
    """Get expected headers with person names from environment"""
    person_1 = os.getenv('PERSON_1_NAME', 'Person 1')
    person_2 = os.getenv('PERSON_2_NAME', 'Person 2')

    return [
        "Transaction Date",
        "Description",
        "Amount",
        "Who",
        "What",
        f"{person_1} Owes",
        f"{person_2} Owes",
        "Notes"
    ]


@dataclass
class SheetConfig:
    """Configuration for Google Sheet access"""
    spreadsheet_id: str
    sheet_name: Optional[str] = None

    @classmethod
    def from_env(cls):
        """Create config from environment variables"""
        spreadsheet_id = os.getenv('SPREADSHEET_ID')
        sheet_name = os.getenv('SHEET_NAME')

        if not spreadsheet_id:
            raise ValueError("SPREADSHEET_ID environment variable not set")

        return cls(spreadsheet_id=spreadsheet_id, sheet_name=sheet_name)


class GoogleSheetsClient:
    """
    Single Responsibility: Handle Google Sheets authentication and client creation
    """

    def __init__(self, credentials_file: str = CREDENTIALS_FILE):
        self.credentials_file = credentials_file
        self._client = None

    def get_client(self) -> gspread.Client:
        """Get or create authenticated Google Sheets client"""
        if self._client is None:
            self._client = self._authenticate()
        return self._client

    def _authenticate(self) -> gspread.Client:
        """Authenticate with Google Sheets API"""
        if not os.path.exists(self.credentials_file):
            raise FileNotFoundError(
                f"Google credentials file not found: {self.credentials_file}\n"
                "Please download your service account JSON from Google Cloud Console\n"
                f"and save it as '{self.credentials_file}' in the backend folder."
            )

        try:
            creds = Credentials.from_service_account_file(
                self.credentials_file,
                scopes=SCOPES
            )
            return gspread.authorize(creds)
        except Exception as e:
            logger.error(f"Failed to authenticate with Google: {str(e)}")
            raise ValueError(f"Failed to authenticate with Google: {str(e)}")


class SheetRepository:
    """
    Single Responsibility: Handle worksheet operations
    Open/Closed Principle: Easy to extend with new sheet operations
    """

    def __init__(self, client: GoogleSheetsClient):
        self.client = client

    def get_worksheet(self, config: SheetConfig):
        """Get worksheet from spreadsheet"""
        try:
            gc = self.client.get_client()
            spreadsheet = gc.open_by_key(config.spreadsheet_id)

            if config.sheet_name:
                return spreadsheet.worksheet(config.sheet_name)
            return spreadsheet.sheet1
        except Exception as e:
            logger.error(f"Failed to access worksheet: {str(e)}")
            raise Exception(f"Failed to access worksheet: {str(e)}")

    def get_headers(self, config: SheetConfig) -> List[str]:
        """Get headers from the sheet"""
        try:
            worksheet = self.get_worksheet(config)
            return worksheet.row_values(1)
        except Exception as e:
            logger.error(f"Failed to read sheet headers: {str(e)}")
            raise Exception(f"Failed to read sheet headers: {str(e)}")

    def append_rows(self, config: SheetConfig, rows: List[List[Any]]) -> int:
        """Append rows to the sheet"""
        if not rows:
            return 0

        try:
            worksheet = self.get_worksheet(config)
            worksheet.append_rows(rows, value_input_option='USER_ENTERED')
            logger.info(f"Successfully appended {len(rows)} rows to sheet")
            return len(rows)
        except Exception as e:
            logger.error(f"Failed to append rows: {str(e)}")
            raise Exception(f"Failed to append rows: {str(e)}")


class TransactionFormatter:
    """
    Single Responsibility: Format transactions for Google Sheets
    Dependency Inversion: Depends on abstractions (Dict) not concrete implementations
    """

    def __init__(self):
        self.person_1 = os.getenv('PERSON_1_NAME', 'Person 1')
        self.person_2 = os.getenv('PERSON_2_NAME', 'Person 2')

    def format_for_sheet(self, transaction: Dict[str, Any]) -> List[Any]:
        """Format a single transaction for Google Sheets"""
        return [
            transaction.get('date', ''),
            transaction.get('description', ''),
            transaction.get('amount', 0),
            transaction.get('who', ''),
            transaction.get('what', ''),
            transaction.get('person_1_owes', transaction.get('person1_owes', 0)),  # Backward compat
            transaction.get('person_2_owes', transaction.get('person2_owes', 0)),  # Backward compat
            transaction.get('notes', '')
        ]

    def format_batch(self, transactions: List[Dict[str, Any]]) -> List[List[Any]]:
        """Format multiple transactions for Google Sheets"""
        return [
            self.format_for_sheet(t)
            for t in transactions
        ]


class GoogleSheetsService:
    """
    Facade: Provides simplified interface for Google Sheets operations
    Interface Segregation: Clients only depend on methods they use
    """

    def __init__(self, config: SheetConfig):
        self.config = config
        self.client = GoogleSheetsClient()
        self.repository = SheetRepository(self.client)
        self.formatter = TransactionFormatter()

    def append_transactions(self, transactions: List[Dict[str, Any]]) -> int:
        """
        Append transactions to Google Sheet

        Args:
            transactions: List of transaction dictionaries

        Returns:
            Number of rows appended
        """
        if not transactions:
            logger.warning("No transactions to append")
            return 0

        rows = self.formatter.format_batch(transactions)
        return self.repository.append_rows(self.config, rows)

    def verify_headers(self) -> Dict[str, Any]:
        """
        Verify sheet headers match expected format

        Returns:
            Dictionary with verification results
        """
        headers = self.repository.get_headers(self.config)
        expected_headers = get_expected_headers()
        headers_match = headers == expected_headers

        return {
            "connected": True,
            "sheet_id": self.config.spreadsheet_id,
            "sheet_name": self.config.sheet_name or "Default",
            "headers": headers,
            "headers_match": headers_match,
            "expected_headers": expected_headers
        }


# Convenience functions for backward compatibility
def append_to_sheet(
        spreadsheet_id: str,
        transactions: List[Dict[str, Any]],
        sheet_name: Optional[str] = None
) -> int:
    """Append transactions to Google Sheet"""
    config = SheetConfig(spreadsheet_id=spreadsheet_id, sheet_name=sheet_name)
    service = GoogleSheetsService(config)
    return service.append_transactions(transactions)


def get_sheet_headers(
        spreadsheet_id: str,
        sheet_name: Optional[str] = None
) -> List[str]:
    """Get headers from Google Sheet"""
    config = SheetConfig(spreadsheet_id=spreadsheet_id, sheet_name=sheet_name)
    service = GoogleSheetsService(config)
    return service.repository.get_headers(config)