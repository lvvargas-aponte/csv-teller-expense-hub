"""SimpleFIN ingest: merchant enrichment and category precedence.

None of the connected institutions populate SimpleFIN's optional
``extra.category``, but every transaction carries ``payee`` and the card
accounts carry ``mcc``. These tests pin how those two land, and — the part
that's easy to regress — what happens to a category on the *second* sync of
a transaction that's already stored.

Precedence, highest first: a category rule, then whatever is already on the
stored row, then the incoming payload (bank-reported category, else MCC).
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

import state


def _ts(date_str):
    """YYYY-MM-DD → Unix seconds at UTC midnight, as SimpleFIN sends them."""
    return int(datetime.strptime(date_str, "%Y-%m-%d")
               .replace(tzinfo=timezone.utc).timestamp())


def _txn(txn_id, description, amount, date="2026-06-15", **extra_fields):
    """A SimpleFIN transaction as it actually arrives on the wire.

    Deliberately includes the keys the live payload has — ``payee``, ``mcc``,
    ``memo`` — and omits ``extra``, which is `{}` on every real transaction.
    """
    out = {
        "id": txn_id,
        "posted": _ts(date),
        "amount": amount,
        "description": description,
        "payee": "",
        "memo": "",
    }
    out.update(extra_fields)
    return out


def _account(transactions, acct_id="acc-citi", name="Citi Double Cash", org="Citibank"):
    return {
        "id": acct_id,
        "name": name,
        "org": {"name": org},
        "balance": "-100.00",
        "transactions": transactions,
    }


def _sync(client, accounts, from_date="2026-06-01", to_date="2026-06-30"):
    mock = AsyncMock(return_value=([("https://u:p@bridge.example/access", accounts)], []))
    with patch.object(state.simplefin, "list_accounts_by_url", mock):
        with patch.object(state, "SIMPLEFIN_ACCESS_URLS", ["https://u:p@bridge.example/access"]):
            response = client.post(
                "/api/simplefin/sync",
                json={"from_date": from_date, "to_date": to_date},
            )
    assert response.status_code == 200, response.text
    return response.json()


class TestEnrichmentPassthrough:
    def test_payee_and_mcc_are_stored(self, client):
        _sync(client, [_account([
            _txn("t1", "FOOD LION #1557 RALEIGH NC", "-84.12",
                 payee="Food Lion", mcc="5411"),
        ])])

        stored = state.stored_transactions["t1"]
        assert stored["payee"] == "Food Lion"
        assert stored["mcc"] == "5411"
        # The raw description is kept as-is — payee is an addition, not a
        # replacement; the store number and city still live in there.
        assert stored["description"] == "FOOD LION #1557 RALEIGH NC"

    def test_mcc_assigns_the_category(self, client):
        _sync(client, [_account([
            _txn("t1", "TST* ARCANA BAR AND LO DURHAM NC", "-31.00",
                 payee="Arcana Bar and Lo", mcc="5813"),
        ])])
        assert state.stored_transactions["t1"]["category"] == "Dining"

    def test_blank_payee_and_missing_mcc_store_as_none(self, client):
        # Most institutions send neither; nothing should be invented.
        _sync(client, [_account([_txn("t1", "ACH DEBIT", "-20.00")])])

        stored = state.stored_transactions["t1"]
        assert stored["payee"] is None
        assert stored["mcc"] is None
        assert stored["category"] is None

    def test_placeholder_mcc_leaves_category_unset(self, client):
        # Autopay rows arrive as 0000 — a real field with no real code in it.
        _sync(client, [_account([
            _txn("t1", "AUTOPAY XXXXXXXXXXX6815RAUTOPAY AUTO-PMT", "-450.00",
                 payee="Credit Card Payment", mcc="0000"),
        ])])

        stored = state.stored_transactions["t1"]
        assert stored["mcc"] == "0000"
        assert stored["category"] is None

    def test_bank_reported_category_still_wins_over_mcc(self, client):
        # No connected bank populates `extra` today, but the protocol allows
        # it — a real label from the institution beats our code lookup.
        _sync(client, [_account([
            _txn("t1", "SOME MERCHANT", "-10.00",
                 mcc="5411", extra={"category": "restaurants"}),
        ])])
        # ...and it goes through the normalizer on the way in.
        assert state.stored_transactions["t1"]["category"] == "Dining"


class TestResyncPrecedence:
    """The same transaction arriving a second time."""

    def test_hand_set_category_survives_resync(self, client):
        accounts = [_account([
            _txn("t1", "FOOD LION #1557 RALEIGH NC", "-84.12",
                 payee="Food Lion", mcc="5411"),
        ])]
        _sync(client, accounts)
        assert state.stored_transactions["t1"]["category"] == "Groceries"

        # The account holder reclassifies it — a warehouse run for the rental.
        stored = state.stored_transactions["t1"]
        stored["category"] = "Rental: Davie"
        state.stored_transactions["t1"] = stored

        _sync(client, accounts)
        assert state.stored_transactions["t1"]["category"] == "Rental: Davie"

    def test_resync_fills_a_blank_category(self, client):
        _sync(client, [_account([_txn("t1", "FOOD LION", "-84.12")])])
        assert state.stored_transactions["t1"]["category"] is None

        # Same transaction, but the bank has since attached its MCC.
        _sync(client, [_account([
            _txn("t1", "FOOD LION", "-84.12", payee="Food Lion", mcc="5411"),
        ])])
        assert state.stored_transactions["t1"]["category"] == "Groceries"

    def test_resync_refreshes_payee_and_mcc(self, client):
        _sync(client, [_account([_txn("t1", "FOOD LION", "-84.12")])])
        assert state.stored_transactions["t1"]["payee"] is None

        _sync(client, [_account([
            _txn("t1", "FOOD LION", "-84.12", payee="Food Lion", mcc="5411"),
        ])])
        stored = state.stored_transactions["t1"]
        assert stored["payee"] == "Food Lion"
        assert stored["mcc"] == "5411"

    def test_rule_outranks_mcc_on_first_sync_and_resync(self, client):
        state.category_rules["rule_test"] = {
            "id": "rule_test",
            "match": "description_contains",
            "value": "FOOD LION",
            "amount": None,
            "transaction_type": None,
            "category": "Tomatillo LLC",
            "enabled": True,
            "created": "2026-01-01T00:00:00",
        }
        accounts = [_account([
            _txn("t1", "FOOD LION #1557 RALEIGH NC", "-84.12",
                 payee="Food Lion", mcc="5411"),
        ])]

        _sync(client, accounts)
        assert state.stored_transactions["t1"]["category"] == "Tomatillo LLC"

        _sync(client, accounts)
        assert state.stored_transactions["t1"]["category"] == "Tomatillo LLC"
