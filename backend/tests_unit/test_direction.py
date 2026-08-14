"""Tests for the canonical transaction ``direction`` field."""
from csv_parser import DiscoverParser
from helpers import derive_direction, txn_direction


class TestDeriveDirection:
    def test_credit_is_inflow(self):
        assert derive_direction("credit") == "inflow"

    def test_debit_is_outflow(self):
        assert derive_direction("debit") == "outflow"


class TestTxnDirection:
    def test_stamped_direction_wins(self):
        txn = {"direction": "inflow", "transaction_type": "debit", "source": "teller"}
        assert txn_direction(txn) == "inflow"

    def test_modern_debit_is_outflow(self):
        assert txn_direction({"transaction_type": "debit", "source": "teller"}) == "outflow"

    def test_modern_credit_is_inflow(self):
        assert txn_direction({"transaction_type": "credit", "source": "teller"}) == "inflow"

    def test_legacy_discover_credit_purchase_is_outflow(self):
        txn = {"transaction_type": "credit", "source": "discover", "category": "Dining"}
        assert txn_direction(txn) == "outflow"

    def test_legacy_discover_payments_and_credits_is_inflow(self):
        txn = {
            "transaction_type": "credit",
            "source": "discover",
            "category": "Payments and Credits",
        }
        assert txn_direction(txn) == "inflow"

    def test_untyped_positive_amount_is_outflow(self):
        assert txn_direction({"amount": 12.5}) == "outflow"

    def test_untyped_negative_amount_is_inflow(self):
        assert txn_direction({"amount": -12.5}) == "inflow"


class TestIngestionStamping:
    def test_to_dict_stamps_direction(self):
        csv = (
            "Trans. Date,Post Date,Description,Amount,Category\n"
            "01/15/2024,01/16/2024,STARBUCKS,-4.50,Restaurants\n"
            "01/17/2024,01/18/2024,REFUND,4.50,Payments and Credits\n"
        )
        charge, refund = [t.to_dict() for t in DiscoverParser().parse(csv)]
        assert charge["transaction_type"] == "debit"
        assert charge["direction"] == "outflow"
        assert refund["transaction_type"] == "credit"
        assert refund["direction"] == "inflow"