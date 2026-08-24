"""Upcoming bills — everything actually due, and what it adds up to.

Transaction-derived bills were restricted to {utilities, mortgage, rent}, so
insurance, phone, internet, loans and childcare were deferred to a dashboard
card and the Bills page opened near-empty. No screen answered "what is due in
the next 30 days, in total".
"""
from datetime import date, timedelta

import state


def _seed_recurring(merchant: str, category: str, amount: float, day: int = 12):
    """Three monthly charges — enough for detect_recurring_charges to bite."""
    anchor = date.today().replace(day=1)
    for i in range(1, 4):
        month_start = anchor
        for _ in range(i):
            month_start = (month_start - timedelta(days=1)).replace(day=1)
        charge_date = month_start.replace(day=day)
        state.stored_transactions[f"{merchant}-{i}"] = {
            "id": f"{merchant}-{i}",
            "date": charge_date.isoformat(),
            "description": merchant,
            "amount": amount,
            "category": category,
            "transaction_type": "debit",
            "direction": "outflow",
            "source": "simplefin",
        }


def _seed_card(account_id: str, ledger: float, due_day: int, minimum: float):
    state._manual_accounts[account_id] = {
        "id": account_id, "institution": "Bank", "name": "Everyday Card",
        "type": "credit", "subtype": "", "available": 0.0, "ledger": ledger,
        "manual": True,
    }
    state.account_details[account_id] = {
        "due_day": due_day, "minimum_payment": minimum,
    }


def _bills(client, window_days=30):
    return client.get(f"/api/bills/upcoming?window_days={window_days}").json()


class TestBillCoverage:
    def test_insurance_and_phone_are_bills(self, client):
        _seed_recurring("STATE FARM", "Insurance", 140.0)
        _seed_recurring("VERIZON WIRELESS", "Phone", 85.0)

        names = [b["name"] for b in _bills(client)["bills"]]

        assert any("STATE FARM" in n for n in names), names
        assert any("VERIZON" in n for n in names), names

    def test_groceries_are_not_bills(self, client):
        """The Recurring Charges card owns everything that merely repeats."""
        _seed_recurring("TRADER JOES", "Groceries", 90.0)

        assert _bills(client)["bills"] == []


class TestTotalDue:
    def test_total_due_sums_the_window(self, client):
        _seed_recurring("STATE FARM", "Insurance", 140.0)
        _seed_recurring("VERIZON WIRELESS", "Phone", 85.0)
        _seed_card("c1", ledger=2000.0, due_day=15, minimum=45.0)

        body = _bills(client)

        assert body["total_due"] == 270.0          # 140 + 85 + 45
        assert body["total_due_by_kind"]["recurring"] == 225.0
        assert body["total_due_by_kind"]["credit"] == 45.0

    def test_a_card_is_due_for_its_minimum_not_its_balance(self, client):
        _seed_card("c1", ledger=2000.0, due_day=15, minimum=45.0)

        bill = _bills(client)["bills"][0]

        assert bill["amount_due"] == 45.0
        assert bill["balance"] == 2000.0           # kept as context
        assert _bills(client)["total_due"] == 45.0

    def test_a_card_with_no_minimum_set_contributes_nothing_to_the_total(self, client):
        _seed_card("c1", ledger=2000.0, due_day=15, minimum=None)

        body = _bills(client)

        assert body["bills"][0]["amount_due"] is None
        assert body["total_due"] == 0.0

    def test_empty_state_totals_zero(self, client):
        body = _bills(client)

        assert body["bills"] == []
        assert body["total_due"] == 0.0
        assert body["total_due_by_kind"] == {"credit": 0.0, "recurring": 0.0}
