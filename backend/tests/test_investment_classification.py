"""Investment / retirement bucket — PR3 of the data-gap initiative.

Pins ``analytics._classify_account_bucket`` and the ``total_investments``
field that ``_balances_snapshot`` and ``/balances/summary`` now expose.
"""
import pytest

import state


@pytest.fixture(autouse=True)
def _clear_state():
    state._manual_accounts.clear()
    state._balances_cache.clear()
    yield
    state._manual_accounts.clear()
    state._balances_cache.clear()


def _add_manual(acct_id, type_, subtype="", available=0.0, ledger=0.0):
    state._manual_accounts[acct_id] = {
        "id": acct_id,
        "institution": "Test Bank",
        "name": acct_id,
        "type": type_,
        "subtype": subtype,
        "available": available,
        "ledger": ledger,
    }


class TestClassifyAccountBucket:
    @pytest.mark.parametrize("acct_type,subtype,expected", [
        ("depository", "checking", "cash"),
        ("depository", "savings", "cash"),
        ("credit", "credit_card", "credit"),
        ("investment", "", "investment"),
        ("investment", "brokerage", "investment"),
        # subtype-driven classification (depository wrapper used by manual entry)
        ("depository", "401k", "investment"),
        ("depository", "IRA", "investment"),
        ("depository", "Roth IRA", "investment"),
        ("depository", "HSA", "investment"),
        ("depository", "529", "investment"),
        # unknown type/subtype falls through
        ("loan", "", "other"),
        ("", "", "other"),
    ])
    def test_classification(self, acct_type, subtype, expected):
        from analytics import _classify_account_bucket
        assert _classify_account_bucket(acct_type, subtype) == expected

    def test_classification_is_case_insensitive(self):
        from analytics import _classify_account_bucket
        assert _classify_account_bucket("DEPOSITORY", "401K") == "investment"


class TestBalancesSnapshot:
    def test_total_investments_zero_when_no_investment_accounts(self):
        _add_manual("a1", "depository", available=1000.0)
        from analytics import _balances_snapshot
        snap = _balances_snapshot()
        assert snap["total_investments"] == 0.0
        assert snap["total_cash"] == 1000.0

    def test_investment_account_lifts_total_investments_only(self):
        _add_manual("cash", "depository", available=1000.0)
        _add_manual("brk1", "investment", subtype="brokerage", available=25000.0)
        _add_manual("ira1", "depository", subtype="IRA", available=15000.0)

        from analytics import _balances_snapshot
        snap = _balances_snapshot()
        assert snap["total_cash"] == 1000.0
        assert snap["total_investments"] == 40000.0
        # Net worth includes investments in PR3.
        assert snap["net_worth"] == 41000.0

    def test_investment_value_falls_back_to_ledger_when_available_empty(self):
        # Some institutions report position value via ledger.
        _add_manual("brk1", "investment", available=0.0, ledger=12500.0)
        from analytics import _balances_snapshot
        snap = _balances_snapshot()
        assert snap["total_investments"] == 12500.0


class TestBalancesSummaryEndpoint:
    def test_summary_returns_total_investments(self, client):
        # Manual investment account → /balances/summary surfaces it.
        _add_manual("brk1", "investment", subtype="brokerage", available=10000.0)
        _add_manual("cash1", "depository", available=2000.0)

        r = client.get("/api/balances/summary")
        assert r.status_code == 200
        body = r.json()
        assert body["total_investments"] == 10000.0
        assert body["total_cash"] == 2000.0
        # Net worth includes investments.
        assert body["net_worth"] == 12000.0

    def test_summary_total_investments_zero_when_no_investment_accounts(self, client):
        _add_manual("cash1", "depository", available=2000.0)
        r = client.get("/api/balances/summary")
        assert r.status_code == 200
        assert r.json()["total_investments"] == 0.0


class TestSnapshotIntegration:
    def test_full_snapshot_includes_total_investments(self):
        _add_manual("brk1", "investment", available=5000.0)
        from analytics import build_financial_snapshot
        snap = build_financial_snapshot()
        assert snap["balances"]["total_investments"] == 5000.0
