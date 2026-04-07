"""
CSV Parser Module
"""
import csv
import io
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class BankType(str, Enum):
    """Enumeration of supported bank types"""
    DISCOVER = "discover"
    BARCLAYS = "barclays"
    TELLER = "teller"
    UNKNOWN = "unknown"


@dataclass
class Transaction:
    """
    Data class representing a transaction
    Single Responsibility: Just hold transaction data
    """
    date: str
    description: str
    amount: float
    source: BankType
    post_date: Optional[str] = None
    category: Optional[str] = None
    transaction_id: Optional[str] = None
    is_shared: bool = False
    who: Optional[str] = None
    what: Optional[str] = None
    person_1_owes: float = 0.0
    person_2_owes: float = 0.0
    notes: str = ""

    def __post_init__(self):
        """Generate transaction ID if not provided"""
        if not self.transaction_id:
            self.transaction_id = self._generate_id()

    def _generate_id(self) -> str:
        """Generate unique transaction ID"""
        desc_snippet = self.description[:20] if self.description else ""
        return f"{self.source}_{self.date}_{self.amount}_{desc_snippet}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


class BankDetector:
    """
    Single Responsibility: Detect bank type from CSV data
    """

    @staticmethod
    def detect(headers: List[str], filename: str = "") -> BankType:
        """
        Detect bank type from CSV headers or filename

        Args:
            headers: List of CSV column headers
            filename: Optional filename for detection

        Returns:
            Detected BankType
        """
        headers_lower = [h.lower().strip() for h in headers]
        filename_lower = filename.lower()

        # Check filename first
        if "discover" in filename_lower:
            return BankType.DISCOVER
        if "creditcard" in filename_lower or "barclays" in filename_lower:
            return BankType.BARCLAYS

        # Check headers
        if "trans. date" in headers_lower and "post date" in headers_lower:
            return BankType.DISCOVER

        return BankType.UNKNOWN


class CSVParser(ABC):
    """
    Abstract base class for CSV parsers
    Open/Closed Principle: Closed for modification, open for extension
    """

    @abstractmethod
    def parse(self, content: str) -> List[Transaction]:
        """Parse CSV content into transactions"""
        pass

    @abstractmethod
    def get_bank_type(self) -> BankType:
        """Return the bank type this parser handles"""
        pass


class DiscoverParser(CSVParser):
    """
    Single Responsibility: Parse Discover CSV format
    """

    def get_bank_type(self) -> BankType:
        return BankType.DISCOVER

    def parse(self, content: str) -> List[Transaction]:
        """Parse Discover CSV format"""
        transactions = []
        reader = csv.DictReader(io.StringIO(content))

        for row in reader:
            try:
                transaction = Transaction(
                    date=row.get('Trans. Date', '').strip(),
                    description=row.get('Description', '').strip(),
                    amount=float(row.get('Amount', 0)),
                    source=BankType.DISCOVER,
                    post_date=row.get('Post Date', '').strip(),
                    category=row.get('Category', '').strip()
                )
                transactions.append(transaction)
            except (ValueError, KeyError) as e:
                logger.warning(f"Error parsing Discover row: {e}")
                continue

        return transactions


class BarclaysParser(CSVParser):
    """
    Single Responsibility: Parse Barclays CSV format
    """

    def get_bank_type(self) -> BankType:
        return BankType.BARCLAYS

    def parse(self, content: str) -> List[Transaction]:
        """Parse Barclays CSV format.

        Barclays CSVs have metadata rows at the top before the real headers:
            Barclays Bank Delaware
            Account Number: XXXXXXXXXXXXXXXX
            Account Balance as of ...:  $X.XX
            (blank)
            Transaction Date,Description,Category,Amount   <- real header
        """
        transactions = []
        reader = csv.reader(io.StringIO(content))

        # Scan until we find the real header row
        for row in reader:
            if row and row[0].strip() == 'Transaction Date':
                break  # next rows are data
        else:
            logger.warning("Could not find Barclays header row")
            return transactions

        # Columns: 0=Transaction Date, 1=Description, 2=Category, 3=Amount
        for row in reader:
            try:
                if len(row) < 4:
                    continue

                amount_str = row[3].strip().replace('$', '').replace(',', '').replace('£', '')
                amount = float(amount_str) if amount_str else 0.0

                transaction = Transaction(
                    date=row[0].strip(),
                    description=row[1].strip(),
                    category=row[2].strip(),  # DEBIT / CREDIT
                    amount=amount,
                    source=BankType.BARCLAYS
                )
                transactions.append(transaction)
            except (ValueError, IndexError) as e:
                logger.warning(f"Error parsing Barclays row: {e}")
                continue

        return transactions


class GenericParser(CSVParser):
    """
    Single Responsibility: Parse unknown CSV formats
    Fallback parser for unrecognized formats
    """

    def get_bank_type(self) -> BankType:
        return BankType.UNKNOWN

    def parse(self, content: str) -> List[Transaction]:
        """Parse generic CSV format"""
        transactions = []
        reader = csv.DictReader(io.StringIO(content))

        for row in reader:
            # Try to find common column names
            date = None
            description = None
            amount = None

            for key in row.keys():
                key_lower = key.lower().strip()
                if 'date' in key_lower and not date:
                    date = row[key].strip()
                elif 'description' in key_lower or 'merchant' in key_lower:
                    description = row[key].strip()
                elif 'amount' in key_lower:
                    try:
                        amount = float(row[key].replace('$', '').replace(',', ''))
                    except ValueError:
                        pass

            if date and description and amount is not None:
                transaction = Transaction(
                    date=date,
                    description=description,
                    amount=amount,
                    source=BankType.UNKNOWN
                )
                transactions.append(transaction)

        return transactions


class ParserFactory:
    """
    Factory Pattern: Create appropriate parser based on bank type
    Single Responsibility: Parser creation logic
    """

    _parsers = {
        BankType.DISCOVER: DiscoverParser,
        BankType.BARCLAYS: BarclaysParser,
    }

    @classmethod
    def create_parser(cls, bank_type: BankType) -> CSVParser:
        """
        Create parser for given bank type

        Args:
            bank_type: Type of bank to create parser for

        Returns:
            Appropriate CSVParser instance
        """
        parser_class = cls._parsers.get(bank_type, GenericParser)
        return parser_class()

    @classmethod
    def register_parser(cls, bank_type: BankType, parser_class: type):
        """Register a new parser type (for extensibility)"""
        cls._parsers[bank_type] = parser_class


class CSVProcessorService:
    """
    Facade: Simplified interface for CSV processing
    Coordinates between detector, factory, and parsers
    """

    def __init__(self):
        self.detector = BankDetector()
        self.factory = ParserFactory()

    def process_csv(self, content: str, filename: str = "") -> List[Transaction]:
        """
        Process CSV content and return transactions

        Args:
            content: CSV file content as string
            filename: Optional filename for bank detection

        Returns:
            List of Transaction objects
        """
        if not content.strip():
            logger.warning("Empty CSV content provided")
            return []

        # Detect bank type
        lines = content.strip().split('\n')
        if not lines:
            return []

        headers = lines[0].split(',')
        bank_type = self.detector.detect(headers, filename)

        logger.info(f"Detected bank type: {bank_type} for file: {filename}")

        # Get appropriate parser and parse
        parser = self.factory.create_parser(bank_type)
        transactions = parser.parse(content)

        logger.info(f"Parsed {len(transactions)} transactions from {filename}")
        return transactions


# Convenience functions for backward compatibility
def parse_csv(content: str, filename: str = "") -> List[Transaction]:
    """Parse CSV content and return list of transactions"""
    processor = CSVProcessorService()
    return processor.process_csv(content, filename)


def transactions_to_google_sheet_format(transactions: List[Transaction]) -> List[Dict[str, Any]]:
    """Convert transactions to Google Sheet format"""
    person_1 = os.getenv('PERSON_1_NAME', 'Person 1')
    person_2 = os.getenv('PERSON_2_NAME', 'Person 2')
    rows = []
    for t in transactions:
        if t.is_shared:  # Only export shared expenses
            rows.append({
                "Transaction Date": t.date,
                "Description": t.description,
                "Amount": t.amount,
                "Who": t.who or "",
                "What": t.what or "",
                f"{person_1} Owes": t.person_1_owes,
                f"{person_2} Owes": t.person_2_owes,
                "Notes": t.notes
            })
    return rows