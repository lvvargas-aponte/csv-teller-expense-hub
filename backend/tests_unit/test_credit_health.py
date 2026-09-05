"""Credit utilization — one composition, read from live balances.

A manual account's stored ``ledger`` is its *starting* balance; the live one
is starting plus the signed delta of linked transactions. Utilization built on
the stored figure disagreed with the Accounts page, and the same wrong number
reached the alert feed and the health score.
"""
import state


def _seed_manual_card(account_id="c1", starting_ledger=1000.0, limit=5000.0, subtype=""):
    state._manual_accounts[account_id] = {
        "id": account_id,
        "institution": "Bank",
        "name": "Everyday Card",
        "type": "credit",
        "subtype": subtype,
        "available": 0.0,
        "ledger": starting_ledger,
        "manual": True,
    }
    if limit is not None:
        state.account_details[account_id] = {"credit_limit": limit}


def _seed_outflow(tid, account_id, amount):
    """A purchase posted to the manual card — raises what is owed."""
    state.stored_transactions[tid] = {
        "id": tid,
        "date": "2026-08-05",
        "description": "MERCHANT",
        "amount": amount,
        "category": "Shopping",
        "transaction_type": "debit",
        "direction": "outflow",
        "account_id": account_id,
        "source": "manual",
    }


class TestCreditHealthLiveBalances:
    def test_manual_card_utilization_uses_live_balance(self, client):
        # starting ledger 1000 + 500 outflow -> live balance 1500 -> 30% of 5000
        _seed_manual_card(starting_ledger=1000.0, limit=5000.0)
        _seed_outflow("t1", "c1", 500.0)

        data = client.get("/api/accounts/credit-health").json()

        assert data["accounts"][0]["balance"] == 1500.0
        assert data["accounts"][0]["utilization_pct"] == 30.0
        assert data["overall_utilization_pct"] == 30.0   # not 20.0
        assert data["total_balance"] == 1500.0

    def test_installment_loan_is_left_out_of_the_composition(self, client):
        """Revolving utilization is meaningless for an auto loan or mortgage.

        The loan was once returned with a null percentage so /debt could show
        every debt in one place. /debt builds its own Cards and Loans sections
        from the balances summary instead, so all that row did here was render
        a name with an empty bar beside it.
        """
        _seed_manual_card("card", starting_ledger=1000.0, limit=5000.0)
        _seed_manual_card("auto", starting_ledger=18000.0, limit=20000.0, subtype="loan")

        data = client.get("/api/accounts/credit-health").json()

        assert [a["account_id"] for a in data["accounts"]] == ["card"]
        # The loan is out of the ratio entirely — 1000 / 5000, not 19000 / 25000.
        assert data["overall_utilization_pct"] == 20.0
        assert data["total_limit"] == 5000.0


class TestCreditAlertsLiveBalances:
    def test_alert_reports_the_live_utilization(self, client):
        # 1000 starting + 500 outflow = 1500 of a 2000 limit -> 75%, not 50%.
        _seed_manual_card(starting_ledger=1000.0, limit=2000.0)
        _seed_outflow("t1", "c1", 500.0)

        feed = client.get("/api/alerts").json()["alerts"]
        credit = [a for a in feed if a["category"] == "credit"]

        assert len(credit) == 1
        assert "75%" in credit[0]["message"]
        assert credit[0]["severity"] == "warn"

    def test_installment_loan_raises_no_utilization_alert(self, client):
        _seed_manual_card("auto", starting_ledger=19000.0, limit=20000.0, subtype="loan")

        feed = client.get("/api/alerts").json()["alerts"]

        assert [a for a in feed if a["category"] == "credit"] == []
