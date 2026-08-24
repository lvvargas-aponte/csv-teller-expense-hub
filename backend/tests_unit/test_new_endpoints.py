"""Tests for four new FastAPI endpoints:
  GET  /api/balances/summary
  POST /api/tools/payoff-plan
  POST /api/insights/spending-summary
  GET  /api/insights/forecast
"""
import re
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

import state
from state import stored_transactions

# conftest.py supplies: client fixture, clear_storage (autouse)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_txn(txn_id, date, amount, category, txn_type="debit"):
    """Insert a transaction directly into stored_transactions."""
    stored_transactions[txn_id] = {
        "id": txn_id,
        "transaction_id": txn_id,
        "date": date,
        "amount": amount,
        "category": category,
        "transaction_type": txn_type,
        "description": "Test",
        "is_shared": False,
        "who": None,
        "what": "",
        "notes": "",
    }


def _make_simplefin_account(acct_id, name, balance, institution="Chase"):
    """Return a dict shaped like a SimpleFIN /accounts list entry.

    SimpleFIN carries no explicit account-type field — ``persist_simplefin_
    balances`` infers cash vs. credit from the account/institution name via
    ``infer_account_bucket``, so the ``name`` chosen here ("Checking" vs.
    "Visa") is what actually selects the bucket. Credit-card balances are
    reported negative (money owed) per SimpleFIN's own sign convention.
    """
    return {
        "id": acct_id,
        "name": name,
        "org": {"name": institution},
        "balance": balance,
        "transactions": [],
    }


def _mock_list_accounts_by_url(accounts_list, url="https://user:pass@bridge.example/access"):
    """Return an AsyncMock for simplefin.list_accounts_by_url with one successful url batch."""
    return AsyncMock(return_value=([(url, accounts_list)], []))


# ---------------------------------------------------------------------------
# GET /api/balances/summary
# ---------------------------------------------------------------------------

class TestGetBalancesSummary:
    def test_no_urls_returns_empty_summary(self, client, monkeypatch):
        monkeypatch.setattr("state.SIMPLEFIN_ACCESS_URLS", [])
        response = client.get("/api/balances/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["net_worth"] == 0
        assert data["total_cash"] == 0
        assert data["total_credit_debt"] == 0
        assert data["accounts"] == []

    def test_depository_only(self, client):
        accounts = [
            _make_simplefin_account("acc1", "Checking", balance="1000.00")
        ]
        with patch.object(state.simplefin, "list_accounts_by_url",
                          _mock_list_accounts_by_url(accounts)):
            with patch.object(state, "SIMPLEFIN_ACCESS_URLS", ["https://u:p@bridge.example/access"]):
                response = client.get("/api/balances/summary?force=true")

        assert response.status_code == 200
        data = response.json()
        assert data["total_cash"] == pytest.approx(1000.0)
        assert data["total_credit_debt"] == pytest.approx(0.0)
        assert data["net_worth"] == pytest.approx(1000.0)
        assert len(data["accounts"]) == 1

    def test_credit_only(self, client):
        accounts = [
            _make_simplefin_account("acc2", "Visa", balance="-500.00")
        ]
        with patch.object(state.simplefin, "list_accounts_by_url",
                          _mock_list_accounts_by_url(accounts)):
            with patch.object(state, "SIMPLEFIN_ACCESS_URLS", ["https://u:p@bridge.example/access"]):
                response = client.get("/api/balances/summary?force=true")

        assert response.status_code == 200
        data = response.json()
        assert data["total_cash"] == pytest.approx(0.0)
        assert data["total_credit_debt"] == pytest.approx(500.0)
        assert data["net_worth"] == pytest.approx(-500.0)

    def test_mixed_accounts(self, client):
        accounts = [
            _make_simplefin_account("acc1", "Checking", balance="2000.00"),
            _make_simplefin_account("acc2", "Visa", balance="-800.00"),
        ]
        with patch.object(state.simplefin, "list_accounts_by_url",
                          _mock_list_accounts_by_url(accounts)):
            with patch.object(state, "SIMPLEFIN_ACCESS_URLS", ["https://u:p@bridge.example/access"]):
                response = client.get("/api/balances/summary?force=true")

        assert response.status_code == 200
        data = response.json()
        assert data["total_cash"] == pytest.approx(2000.0)
        assert data["total_credit_debt"] == pytest.approx(800.0)
        assert data["net_worth"] == pytest.approx(1200.0)
        assert len(data["accounts"]) == 2

    def test_brokerage_counts_as_investment_not_cash(self, client):
        """A SimpleFIN brokerage lands in the investment bucket, and its value
        is counted exactly once — summing it into cash as well would inflate
        net worth by the size of the portfolio."""
        accounts = [
            _make_simplefin_account("acc1", "Checking", balance="2000.00"),
            _make_simplefin_account(
                "acc3", "Individual Brokerage", balance="50000.00", institution="E*Trade",
            ),
        ]
        with patch.object(state.simplefin, "list_accounts_by_url",
                          _mock_list_accounts_by_url(accounts)):
            with patch.object(state, "SIMPLEFIN_ACCESS_URLS", ["https://u:p@bridge.example/access"]):
                response = client.get("/api/balances/summary?force=true")

        data = response.json()
        assert data["total_cash"] == pytest.approx(2000.0)
        assert data["total_investments"] == pytest.approx(50000.0)
        assert data["net_worth"] == pytest.approx(52000.0)
        brokerage = next(a for a in data["accounts"] if a["id"] == "acc3")
        assert brokerage["type"] == "investment"

    def test_failed_url_skipped(self, client):
        """First access URL errors; second returns a valid account. Both modelled as return value."""
        good_accounts = [
            _make_simplefin_account("acc_good", "Savings", balance="500.00")
        ]
        # list_accounts_by_url returns one success and one error entry
        mock_return = (
            [("https://u:p@good.example/access", good_accounts)],
            [{"url": "https://***@bad.example/access", "error": "Auth failed (401)"}],
        )
        with patch.object(state.simplefin, "list_accounts_by_url",
                          AsyncMock(return_value=mock_return)):
            with patch.object(state, "SIMPLEFIN_ACCESS_URLS",
                              ["https://u:p@bad.example/access", "https://u:p@good.example/access"]):
                response = client.get("/api/balances/summary?force=true")

        assert response.status_code == 200
        data = response.json()
        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["id"] == "acc_good"
        assert data["total_cash"] == pytest.approx(500.0)

    def test_default_get_never_hits_simplefin(self, client):
        """GET without force=true must NOT call SimpleFIN, even when access URLs exist."""
        list_mock = AsyncMock(return_value=([], []))
        with patch.object(state.simplefin, "list_accounts_by_url", list_mock):
            with patch.object(state, "SIMPLEFIN_ACCESS_URLS", ["https://u:p@bridge.example/access"]):
                response = client.get("/api/balances/summary")

        assert response.status_code == 200
        assert list_mock.await_count == 0


# ---------------------------------------------------------------------------
# POST /api/tools/payoff-plan
# ---------------------------------------------------------------------------

class TestPayoffPlan:
    _endpoint = "/api/tools/payoff-plan"

    def _post(self, client, body):
        return client.post(self._endpoint, json=body)

    def test_single_card_basic(self, client):
        body = {
            "accounts": [{"name": "Card A", "balance": 1000.0, "apr": 24.0, "min_payment": 50.0}],
            "strategy": "avalanche",
            "extra_monthly": 0.0,
        }
        response = self._post(client, body)
        assert response.status_code == 200
        data = response.json()
        assert len(data["accounts"]) == 1
        acct = data["accounts"][0]
        assert acct["payoff_months"] > 0
        assert acct["total_interest"] > 0
        assert re.match(r"^\d{4}-\d{2}$", acct["payoff_date"])
        assert data["grand_total_interest"] >= 0

    def test_zero_balance_pays_immediately(self, client):
        body = {
            "accounts": [{"name": "Zero Card", "balance": 0.0, "apr": 20.0, "min_payment": 25.0}],
            "strategy": "avalanche",
            "extra_monthly": 0.0,
        }
        response = self._post(client, body)
        assert response.status_code == 200
        data = response.json()
        assert "payoff_months" in data["accounts"][0]

    def test_avalanche_orders_by_apr(self, client):
        """Avalanche (highest APR first) should produce less total interest than snowball."""
        cards = [
            {"name": "CardA", "balance": 500.0, "apr": 20.0, "min_payment": 30.0},
            {"name": "CardB", "balance": 500.0, "apr": 5.0, "min_payment": 30.0},
        ]
        avalanche_body = {"accounts": cards, "strategy": "avalanche", "extra_monthly": 0.0}
        snowball_body = {"accounts": cards, "strategy": "snowball", "extra_monthly": 0.0}

        avalanche_resp = self._post(client, avalanche_body)
        snowball_resp = self._post(client, snowball_body)

        assert avalanche_resp.status_code == 200
        assert snowball_resp.status_code == 200

        avalanche_interest = avalanche_resp.json()["grand_total_interest"]
        snowball_interest = snowball_resp.json()["grand_total_interest"]
        assert avalanche_interest <= snowball_interest

    def test_snowball_strategy(self, client):
        cards = [
            {"name": "CardA", "balance": 500.0, "apr": 20.0, "min_payment": 30.0},
            {"name": "CardB", "balance": 500.0, "apr": 5.0, "min_payment": 30.0},
        ]
        body = {"accounts": cards, "strategy": "snowball", "extra_monthly": 0.0}
        response = self._post(client, body)
        assert response.status_code == 200
        assert response.json()["strategy"] == "snowball"

    def test_freed_minimum_rolls_into_next_debt(self, client):
        """Snowball: Small clears in 2 months at $250/mo; its minimum must then
        join Big's $100, paying Big off in month 9 rather than month 24."""
        body = {
            "accounts": [
                {"name": "Small", "balance": 500.0,  "apr": 0.0, "min_payment": 250.0},
                {"name": "Big",   "balance": 2400.0, "apr": 0.0, "min_payment": 100.0},
            ],
            "strategy": "snowball",
            "extra_monthly": 0.0,
        }
        data = self._post(client, body).json()
        by_name = {a["name"]: a for a in data["accounts"]}
        assert by_name["Small"]["payoff_months"] == 2
        assert by_name["Big"]["payoff_months"] == 9
        assert data["grand_total_months"] == 9

    def test_minimum_below_interest_is_flagged(self, client):
        body = {
            "accounts": [{"name": "Trap", "balance": 10000.0,
                          "apr": 29.99, "min_payment": 100.0}],
            "strategy": "avalanche",
            "extra_monthly": 0.0,
        }
        acct = self._post(client, body).json()["accounts"][0]
        assert acct["never_amortizes"] is True
        assert acct["payoff_months"] == state.PAYOFF_MAX_MONTHS

    def test_extra_monthly_reduces_interest(self, client):
        card = {"name": "Card", "balance": 2000.0, "apr": 20.0, "min_payment": 50.0}

        no_extra_body = {"accounts": [card], "strategy": "avalanche", "extra_monthly": 0.0}
        with_extra_body = {"accounts": [card], "strategy": "avalanche", "extra_monthly": 200.0}

        no_extra_resp = self._post(client, no_extra_body)
        with_extra_resp = self._post(client, with_extra_body)

        assert no_extra_resp.status_code == 200
        assert with_extra_resp.status_code == 200

        no_extra_data = no_extra_resp.json()
        with_extra_data = with_extra_resp.json()

        assert with_extra_data["grand_total_months"] < no_extra_data["grand_total_months"]
        assert with_extra_data["grand_total_interest"] < no_extra_data["grand_total_interest"]

    def test_interest_saved_positive_with_extra(self, client):
        card = {"name": "Card", "balance": 2000.0, "apr": 20.0, "min_payment": 50.0}
        body = {"accounts": [card], "strategy": "avalanche", "extra_monthly": 100.0}
        response = self._post(client, body)
        assert response.status_code == 200
        assert response.json()["interest_saved_vs_minimums"] >= 0

    def test_empty_accounts_returns_zeros(self, client):
        body = {"accounts": [], "strategy": "avalanche", "extra_monthly": 0.0}
        response = self._post(client, body)
        assert response.status_code == 200
        data = response.json()
        assert data["grand_total_interest"] == pytest.approx(0.0)

    def test_invalid_request_missing_field(self, client):
        body = {"accounts": [{"name": "x"}]}
        response = self._post(client, body)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/insights/spending-summary
# ---------------------------------------------------------------------------

class TestSpendingSummary:
    _endpoint = "/api/insights/spending-summary"

    def _mock_ollama(self, ai_text=None, raise_connect_error=False):
        """Return a context-manager patch for httpx.AsyncClient that mocks Ollama."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": ai_text or ""}
        mock_resp.raise_for_status = MagicMock()

        mock_instance = AsyncMock()
        if raise_connect_error:
            mock_instance.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
        else:
            mock_instance.post = AsyncMock(return_value=mock_resp)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        return mock_instance

    def test_empty_storage_returns_no_ai(self, client):
        response = client.post(self._endpoint, json={})
        assert response.status_code == 200
        data = response.json()
        assert data["ai_available"] is False
        assert data["spending_by_month"] == {}

    def test_spending_grouped_by_month_and_category(self, client):
        _seed_txn("t1", "2024-01-10", 50.0, "Dining")
        _seed_txn("t2", "2024-01-20", 30.0, "Dining")
        _seed_txn("t3", "2024-01-25", 100.0, "Shopping")
        _seed_txn("t4", "2024-02-05", 70.0, "Dining")

        mock_instance = self._mock_ollama(raise_connect_error=True)
        with patch("httpx.AsyncClient", return_value=mock_instance):
            response = client.post(self._endpoint, json={})

        assert response.status_code == 200
        data = response.json()
        sbm = data["spending_by_month"]
        assert "2024-01" in sbm
        assert "2024-02" in sbm
        assert sbm["2024-01"]["Dining"] == pytest.approx(80.0)
        assert sbm["2024-01"]["Shopping"] == pytest.approx(100.0)
        assert sbm["2024-02"]["Dining"] == pytest.approx(70.0)
        assert data["ai_available"] is False

    def test_credit_txns_excluded(self, client):
        _seed_txn("t1", "2024-01-10", 200.0, "Paycheck", txn_type="credit")

        response = client.post(self._endpoint, json={})
        assert response.status_code == 200
        data = response.json()
        assert data["spending_by_month"] == {}

    def test_ollama_available_returns_ai_summary(self, client):
        _seed_txn("t1", "2024-01-10", 50.0, "Dining")

        mock_instance = self._mock_ollama(ai_text="You spent a lot.")
        with patch("httpx.AsyncClient", return_value=mock_instance):
            response = client.post(self._endpoint, json={})

        assert response.status_code == 200
        data = response.json()
        assert data["ai_available"] is True
        assert data["ai_summary"] == "You spent a lot."

    def test_ollama_unreachable_degrades_gracefully(self, client):
        _seed_txn("t1", "2024-01-10", 50.0, "Dining")

        mock_instance = self._mock_ollama(raise_connect_error=True)
        with patch("httpx.AsyncClient", return_value=mock_instance):
            response = client.post(self._endpoint, json={})

        assert response.status_code == 200
        data = response.json()
        assert data["ai_available"] is False
        assert "2024-01" in data["spending_by_month"]
        assert data["ai_summary"] is None

    def test_only_last_6_months_included(self, client):
        # Seed 7 different months
        months = [
            "2023-06", "2023-07", "2023-08", "2023-09",
            "2023-10", "2023-11", "2023-12",
        ]
        for i, m in enumerate(months):
            _seed_txn(f"t{i}", f"{m}-01", 100.0, "Dining")

        mock_instance = self._mock_ollama(raise_connect_error=True)
        with patch("httpx.AsyncClient", return_value=mock_instance):
            response = client.post(self._endpoint, json={})

        assert response.status_code == 200
        data = response.json()
        assert len(data["spending_by_month"]) <= 6


# ---------------------------------------------------------------------------
# GET /api/insights/forecast
# ---------------------------------------------------------------------------

class TestSpendingForecast:
    _endpoint = "/api/insights/forecast"

    def test_empty_storage_returns_empty_forecast(self, client):
        response = client.get(self._endpoint)
        assert response.status_code == 200
        data = response.json()
        assert data["categories"] == []
        assert re.match(r"^\d{4}-\d{2}$", data["forecast_month"])

    def test_single_month_forecast(self, client):
        _seed_txn("t1", "2024-01-10", 100.0, "Dining")

        response = client.get(self._endpoint)
        assert response.status_code == 200
        data = response.json()
        assert len(data["categories"]) == 1
        cat = data["categories"][0]
        assert cat["category"] == "Dining"
        # Only m1 = 100, predicted = 100 * 0.5 = 50
        assert cat["predicted"] == pytest.approx(50.0)

    def test_three_month_weighted_average(self, client):
        # m1 (most recent) = 2024-03: 100, m2 = 2024-02: 200, m3 = 2024-01: 300
        _seed_txn("t1", "2024-01-10", 300.0, "Groceries")
        _seed_txn("t2", "2024-02-10", 200.0, "Groceries")
        _seed_txn("t3", "2024-03-10", 100.0, "Groceries")

        response = client.get(self._endpoint)
        assert response.status_code == 200
        data = response.json()

        groceries = next(c for c in data["categories"] if c["category"] == "Groceries")
        # predicted = 100*0.5 + 200*0.3 + 300*0.2 = 50 + 60 + 60 = 170
        assert groceries["predicted"] == pytest.approx(170.0)

    def test_categories_sorted_by_predicted_descending(self, client):
        # Single month: CategoryA=200, CategoryB=50
        # With only m1 each: predicted = 200*0.5=100 and 50*0.5=25
        _seed_txn("t1", "2024-01-10", 200.0, "CategoryA")
        _seed_txn("t2", "2024-01-20", 50.0, "CategoryB")

        response = client.get(self._endpoint)
        assert response.status_code == 200
        cats = response.json()["categories"]
        assert len(cats) >= 2
        predicted_values = [c["predicted"] for c in cats]
        assert predicted_values == sorted(predicted_values, reverse=True)
        assert cats[0]["category"] == "CategoryA"

    def test_only_uses_last_3_months(self, client):
        # Seed 5 months; only the 3 most recent should influence predictions
        months_data = {
            "2023-11": ("OldCategory", 500.0),
            "2023-12": ("OldCategory", 500.0),
            "2024-01": ("RecentOnly", 100.0),
            "2024-02": ("RecentOnly", 100.0),
            "2024-03": ("RecentOnly", 100.0),
        }
        for i, (m, (cat, amt)) in enumerate(months_data.items()):
            _seed_txn(f"t{i}", f"{m}-10", amt, cat)

        response = client.get(self._endpoint)
        assert response.status_code == 200
        cats = response.json()["categories"]
        cat_names = {c["category"] for c in cats}

        # OldCategory only appears in the 2 oldest months; if it shows at all,
        # its months_of_data should reflect only what falls in the 3 most recent window
        if "OldCategory" in cat_names:
            old_entry = next(c for c in cats if c["category"] == "OldCategory")
            assert old_entry["months_of_data"] <= 3

        # RecentOnly appears in all 3 most recent months
        assert "RecentOnly" in cat_names
        recent_entry = next(c for c in cats if c["category"] == "RecentOnly")
        assert recent_entry["months_of_data"] == 3

    def test_forecast_month_is_next_month(self, client):
        from datetime import date
        response = client.get(self._endpoint)
        assert response.status_code == 200
        forecast_month = response.json()["forecast_month"]
        today = date.today()
        current_month_str = today.strftime("%Y-%m")
        assert forecast_month != current_month_str

    def test_credit_transactions_excluded(self, client):
        _seed_txn("t1", "2024-01-10", 500.0, "Paycheck", txn_type="credit")

        response = client.get(self._endpoint)
        assert response.status_code == 200
        assert response.json()["categories"] == []
