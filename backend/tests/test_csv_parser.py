"""Tests for csv_parser.py"""
import pytest
from csv_parser import (
    BankType, BankDetector, DiscoverParser, BarclaysParser,
    GenericParser, parse_csv, _id_counter,
)


# ---------------------------------------------------------------------------
# BankDetector
# ---------------------------------------------------------------------------

class TestBankDetector:
    def test_detects_discover_by_header(self):
        headers = ["Trans. Date", "Post Date", "Description", "Amount", "Category"]
        assert BankDetector.detect(headers) == BankType.DISCOVER

    def test_detects_discover_by_filename(self):
        assert BankDetector.detect([], "Discover-Statement-2024.csv") == BankType.DISCOVER

    def test_detects_barclays_by_header(self):
        headers = ["Transaction Date", "Description", "Category", "Amount"]
        assert BankDetector.detect(headers) == BankType.BARCLAYS

    def test_detects_barclays_by_filename(self):
        assert BankDetector.detect([], "creditcard_transactions.csv") == BankType.BARCLAYS

    def test_unknown_returns_unknown(self):
        assert BankDetector.detect(["date", "desc", "amt"]) == BankType.UNKNOWN

    def test_filename_takes_priority_over_generic_headers(self):
        # Even with headers that could be generic, filename wins
        assert BankDetector.detect(["date", "description", "amount"], "Discover-2024.csv") == BankType.DISCOVER


# ---------------------------------------------------------------------------
# DiscoverParser
# ---------------------------------------------------------------------------

DISCOVER_TWO_ROWS = (
    "Trans. Date,Post Date,Description,Amount,Category\n"
    "01/15/2024,01/16/2024,STARBUCKS,-4.50,Restaurants\n"
    "01/16/2024,01/17/2024,AMAZON,-29.99,Shopping\n"
)

DISCOVER_ONE_ROW_ONE_BAD = (
    "Trans. Date,Post Date,Description,Amount,Category\n"
    "01/15/2024,01/16/2024,STARBUCKS,-4.50,Restaurants\n"
    "01/16/2024,01/17/2024,AMAZON,not-a-number,Shopping\n"
)


class TestDiscoverParser:
    def test_parses_two_rows(self):
        transactions = DiscoverParser().parse(DISCOVER_TWO_ROWS)
        assert len(transactions) == 2
        assert transactions[0].description == "STARBUCKS"
        assert transactions[0].amount == -4.50
        assert transactions[1].description == "AMAZON"
        assert transactions[1].amount == -29.99

    def test_skips_malformed_row(self):
        transactions = DiscoverParser().parse(DISCOVER_ONE_ROW_ONE_BAD)
        assert len(transactions) == 1
        assert transactions[0].description == "STARBUCKS"

    def test_empty_csv_returns_empty_list(self):
        assert DiscoverParser().parse("") == []

    def test_header_only_returns_empty_list(self):
        assert DiscoverParser().parse("Trans. Date,Post Date,Description,Amount,Category\n") == []

    def test_transaction_id_is_generated(self):
        transactions = DiscoverParser().parse(DISCOVER_TWO_ROWS)
        assert transactions[0].transaction_id is not None
        assert len(transactions[0].transaction_id) > 0

    def test_source_is_discover(self):
        transactions = DiscoverParser().parse(DISCOVER_TWO_ROWS)
        assert transactions[0].source == BankType.DISCOVER

    def test_category_is_captured(self):
        transactions = DiscoverParser().parse(DISCOVER_TWO_ROWS)
        assert transactions[0].category == "Restaurants"


# ---------------------------------------------------------------------------
# BarclaysParser
# ---------------------------------------------------------------------------

BARCLAYS_VALID = (
    "Barclays Bank Delaware\n"
    "Account Number: 1234567890123456\n"
    "Account Balance as of 01/31/2024: $1234.56\n"
    "\n"
    "Transaction Date,Description,Category,Amount\n"
    "01/15/2024,WHOLE FOODS,DEBIT,-67.23\n"
    "01/16/2024,NETFLIX,DEBIT,-15.99\n"
)

BARCLAYS_DOLLAR_SIGN = (
    "Transaction Date,Description,Category,Amount\n"
    "01/15/2024,WHOLE FOODS,DEBIT,$67.23\n"
)

BARCLAYS_NO_HEADER = (
    "Some random content\n"
    "1,2,3,4\n"
)


class TestBarclaysParser:
    def test_parses_past_metadata_preamble(self):
        transactions = BarclaysParser().parse(BARCLAYS_VALID)
        assert len(transactions) == 2
        assert transactions[0].description == "WHOLE FOODS"
        assert transactions[0].amount == -67.23

    def test_raises_when_header_not_found(self):
        with pytest.raises(ValueError, match="Barclays CSV"):
            BarclaysParser().parse(BARCLAYS_NO_HEADER)

    def test_strips_dollar_sign_from_amount(self):
        transactions = BarclaysParser().parse(BARCLAYS_DOLLAR_SIGN)
        assert len(transactions) == 1
        assert transactions[0].amount == 67.23

    def test_source_is_barclays(self):
        transactions = BarclaysParser().parse(BARCLAYS_VALID)
        assert transactions[0].source == BankType.BARCLAYS

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="Barclays CSV"):
            BarclaysParser().parse("")


# ---------------------------------------------------------------------------
# GenericParser
# ---------------------------------------------------------------------------

GENERIC_VALID = (
    "date,description,amount\n"
    "2024-01-15,COFFEE SHOP,-3.50\n"
    "2024-01-16,GAS STATION,-45.00\n"
)

GENERIC_MISSING_AMOUNT = (
    "date,description,amount\n"
    "2024-01-15,COFFEE SHOP,-3.50\n"
    "2024-01-16,GAS STATION,\n"       # empty amount — row should be skipped
)


class TestGenericParser:
    def test_parses_generic_format(self):
        transactions = GenericParser().parse(GENERIC_VALID)
        assert len(transactions) == 2
        assert transactions[0].description == "COFFEE SHOP"

    def test_skips_rows_missing_amount(self):
        transactions = GenericParser().parse(GENERIC_MISSING_AMOUNT)
        assert len(transactions) == 1

    def test_source_is_unknown(self):
        transactions = GenericParser().parse(GENERIC_VALID)
        assert transactions[0].source == BankType.UNKNOWN


# ---------------------------------------------------------------------------
# parse_csv end-to-end
# ---------------------------------------------------------------------------

class TestParseCSV:
    def test_discover_end_to_end(self):
        result = parse_csv(DISCOVER_TWO_ROWS, "Discover-Statement.csv")
        assert len(result) == 2

    def test_barclays_end_to_end(self):
        result = parse_csv(BARCLAYS_VALID, "creditcard.csv")
        assert len(result) == 2

    def test_empty_content_returns_empty_list(self):
        assert parse_csv("", "anything.csv") == []

    def test_unknown_bank_falls_back_to_generic(self):
        result = parse_csv(GENERIC_VALID, "mybank.csv")
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Transaction ID collision handling
# ---------------------------------------------------------------------------

DISCOVER_DUPLICATE_ROWS = (
    "Trans. Date,Post Date,Description,Amount,Category\n"
    "01/15/2024,01/16/2024,STARBUCKS,-4.50,Restaurants\n"
    "01/15/2024,01/16/2024,STARBUCKS,-4.50,Restaurants\n"  # identical row
)


class TestTransactionIdCollision:
    def test_duplicate_transactions_get_different_ids(self):
        # Reset counter so this test is independent of run order
        _id_counter.clear()
        transactions = DiscoverParser().parse(DISCOVER_DUPLICATE_ROWS)
        assert len(transactions) == 2
        ids = {t.transaction_id for t in transactions}
        assert len(ids) == 2, "Duplicate transactions must receive distinct IDs"
