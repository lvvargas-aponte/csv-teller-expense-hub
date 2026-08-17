"""Credit utilization is card-only.

``infer_account_bucket`` types mortgages and installment loans as
``credit`` because they're liabilities, so anything card-specific has to
screen out the ``loan`` subtype or a 30-year mortgage lands on the
utilization card next to a Citi Double Cash.
"""
import pytest

import state
from simplefin import is_revolving_credit


def _acct(acct_id, name, subtype="credit_card", ledger=0.0):
    return {
        "id": acct_id,
        "institution": "Test Bank",
        "name": name,
        "type": "credit",
        "subtype": subtype,
        "available": ledger,
        "ledger": ledger,
    }


class TestIsRevolvingCredit:
    @pytest.mark.parametrize("subtype,expected", [
        ("credit_card", True),
        ("loan", False),
        ("mortgage", False),
        ("CREDIT_CARD", True),
        ("LOAN", False),
    ])
    def test_subtype_drives_the_decision(self, subtype, expected):
        assert is_revolving_credit(_acct("a1", "Some Card", subtype)) is expected

    def test_depository_is_never_revolving_credit(self):
        assert is_revolving_credit({"type": "depository", "subtype": ""}) is False

    @pytest.mark.parametrize("name,expected", [
        ("MORTGAGE LOAN (1474)", False),
        ("20 YEAR FIXED RATE LOAN (0002)", False),
        ("CARECREDIT / SYNCHRONY BANK (0742)", True),
        ("Blue Cash Everyday (5006)", True),
    ])
    def test_falls_back_to_name_when_subtype_is_blank(self, name, expected):
        # Manual accounts can be saved with no subtype at all.
        assert is_revolving_credit(_acct("a1", name, subtype="")) is expected

    def test_credit_union_in_the_name_is_not_a_loan_signal(self):
        acct = _acct("a1", "Navy Federal Credit Union Platinum", subtype="")
        assert is_revolving_credit(acct) is True


class TestCreditHealthEndpoint:
    def test_loans_are_excluded_from_utilization(self, client):
        state._manual_accounts["card"] = _acct("card", "Citi Double Cash", ledger=413.65)
        state._manual_accounts["mtg"] = _acct(
            "mtg", "MORTGAGE LOAN (1474)", subtype="loan", ledger=301840.07,
        )
        state._manual_accounts["fixed"] = _acct(
            "fixed", "20 YEAR FIXED RATE LOAN (0002)", subtype="loan", ledger=109231.05,
        )

        r = client.get("/api/accounts/credit-health")
        assert r.status_code == 200
        assert [a["account_id"] for a in r.json()["accounts"]] == ["card"]

    def test_card_utilization_still_computes(self, client):
        state._manual_accounts["card"] = _acct("card", "Citi Double Cash", ledger=500.0)
        state.account_details["card"] = {"credit_limit": 2000.0}

        body = client.get("/api/accounts/credit-health").json()
        assert body["accounts"][0]["utilization_pct"] == 25.0
        assert body["overall_utilization_pct"] == 25.0

    def test_a_loan_with_a_limit_set_does_not_skew_the_overall(self, client):
        # A stray credit_limit on a loan used to be folded into the ratio.
        state._manual_accounts["card"] = _acct("card", "Citi Double Cash", ledger=500.0)
        state.account_details["card"] = {"credit_limit": 2000.0}
        state._manual_accounts["mtg"] = _acct(
            "mtg", "MORTGAGE LOAN (1474)", subtype="loan", ledger=301840.07,
        )
        state.account_details["mtg"] = {"credit_limit": 400000.0}

        body = client.get("/api/accounts/credit-health").json()
        assert body["overall_utilization_pct"] == 25.0
        assert body["total_limit"] == 2000.0


class TestUtilizationAlerts:
    """The utilization rule now lives in ``coach``; ``/api/alerts`` is a
    projection of it. These assert the same guarantees through that seam."""

    def _utilization_alerts(self):
        import coach
        return [
            a for a in coach.build_alerts()["alerts"] if a["category"] == "credit"
        ]

    def test_no_alert_for_a_loan(self):
        state._manual_accounts["mtg"] = _acct(
            "mtg", "MORTGAGE LOAN (1474)", subtype="loan", ledger=301840.07,
        )
        state.account_details["mtg"] = {"credit_limit": 320000.0}  # ~94%
        assert self._utilization_alerts() == []

    def test_alert_still_fires_for_a_maxed_card(self):
        state._manual_accounts["card"] = _acct("card", "Citi Double Cash", ledger=1900.0)
        state.account_details["card"] = {"credit_limit": 2000.0}
        alerts = self._utilization_alerts()
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "error"

    def test_the_endpoint_returns_the_same_thing(self, client):
        state._manual_accounts["card"] = _acct("card", "Citi Double Cash", ledger=1900.0)
        state.account_details["card"] = {"credit_limit": 2000.0}

        body = client.get("/api/alerts").json()
        credit = [a for a in body["alerts"] if a["category"] == "credit"]
        assert len(credit) == 1
        assert body["counts"]["error"] >= 1

    def test_the_paydown_target_is_quantified(self):
        """The old feed said "consider paying down". This says how much."""
        state._manual_accounts["card"] = _acct("card", "Citi Double Cash", ledger=1900.0)
        state.account_details["card"] = {"credit_limit": 2000.0}

        import coach
        action = next(
            a for a in coach.build_actions(limit=coach.ALERT_LIMIT)["actions"]
            if a["kind"] == "reduce_utilization"
        )
        # 30% of a $2,000 limit is $600; $1,900 - $600 = $1,300.
        assert action["amount"] == 1300.0
