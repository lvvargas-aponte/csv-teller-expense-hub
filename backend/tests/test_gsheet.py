"""Tests for gsheet_integration.py"""
import pytest

from gsheet_integration import (
    TransactionFormatter, GoogleSheetsClient,
    AuthenticationError, get_expected_headers,
)


# ---------------------------------------------------------------------------
# TransactionFormatter
# ---------------------------------------------------------------------------

class TestTransactionFormatter:
    def test_format_for_sheet_maps_all_columns(self):
        fmt = TransactionFormatter()
        txn = {
            "date": "2024-01-15",
            "description": "STARBUCKS",
            "amount": -4.50,
            "who": "Alice",
            "what": "Coffee",
            "person_1_owes": 2.25,
            "person_2_owes": 2.25,
            "notes": "test note",
        }
        row = fmt.format_for_sheet(txn)
        assert row[0] == "2024-01-15"
        assert row[1] == "STARBUCKS"
        assert row[2] == -4.50
        assert row[3] == "Alice"
        assert row[4] == "Coffee"
        assert row[5] == 2.25
        assert row[6] == 2.25
        assert row[7] == "test note"

    def test_backward_compat_person1_owes_key(self):
        """Old key 'person1_owes' (no underscore) must still be read."""
        fmt = TransactionFormatter()
        txn = {"date": "", "description": "", "amount": 0, "who": "", "what": "",
               "person1_owes": 10.0, "person2_owes": 5.0, "notes": ""}
        row = fmt.format_for_sheet(txn)
        assert row[5] == 10.0
        assert row[6] == 5.0

    def test_format_batch_returns_list_of_lists(self):
        fmt = TransactionFormatter()
        txns = [
            {"date": "2024-01-15", "description": "A", "amount": -1, "who": "", "what": "",
             "person_1_owes": 0, "person_2_owes": 0, "notes": ""},
            {"date": "2024-01-16", "description": "B", "amount": -2, "who": "", "what": "",
             "person_1_owes": 0, "person_2_owes": 0, "notes": ""},
        ]
        rows = fmt.format_batch(txns)
        assert len(rows) == 2
        assert isinstance(rows[0], list)
        assert rows[0][1] == "A"
        assert rows[1][1] == "B"

    def test_missing_optional_fields_default_to_empty(self):
        fmt = TransactionFormatter()
        row = fmt.format_for_sheet({"date": "2024-01-15", "description": "X", "amount": -5})
        assert row[3] == ""   # who
        assert row[4] == ""   # what
        assert row[7] == ""   # notes


# ---------------------------------------------------------------------------
# get_expected_headers
# ---------------------------------------------------------------------------

class TestGetExpectedHeaders:
    def test_returns_eight_columns(self):
        headers = get_expected_headers()
        assert len(headers) == 8

    def test_first_column_is_transaction_date(self):
        assert get_expected_headers()[0] == "Transaction Date"

    def test_includes_notes_as_last_column(self):
        assert get_expected_headers()[-1] == "Notes"


# ---------------------------------------------------------------------------
# GoogleSheetsClient authentication
# ---------------------------------------------------------------------------

class TestGoogleSheetsClient:
    def test_raises_auth_error_when_credentials_missing(self, tmp_path):
        """Attempting to authenticate with a missing file must raise AuthenticationError."""
        client = GoogleSheetsClient(credentials_file=str(tmp_path / "does_not_exist.json"))
        with pytest.raises(AuthenticationError, match="credentials file not found"):
            client.get_client()

    def test_raises_auth_error_on_invalid_credentials(self, tmp_path):
        """A file that exists but contains invalid JSON must raise AuthenticationError."""
        bad_creds = tmp_path / "creds.json"
        bad_creds.write_text("{not valid json")
        client = GoogleSheetsClient(credentials_file=str(bad_creds))
        with pytest.raises(AuthenticationError):
            client.get_client()
