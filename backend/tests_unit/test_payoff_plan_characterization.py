"""Characterization tests for ``POST /api/tools/payoff-plan``.

These pin the **exact current output** of the payoff simulation so the
upcoming refactor — moving the ~100-line simulation body out of
``routers/tools.py`` into ``amortization.simulate_payoff_plan()`` — can be
proven behavior-preserving. Unlike ``test_new_endpoints.TestPayoffPlan``,
which asserts relative properties (avalanche <= snowball, extra reduces
interest), every number here is an exact pinned value.

**These are not assertions that the current behavior is correct.** Two
known defects are deliberately pinned below so the refactor diff stays
legible; each is marked ``PINNED BUG`` and lists the file to update when
the fix lands in its own commit:

1. **No minimum-payment rollover.** When an account reaches zero its
   freed-up minimum is never redirected to the next debt — each account
   pays only its own ``min_payment`` forever, and ``extra`` only ever
   goes to the first non-zero balance. That cascade is the defining
   mechanic of both snowball and avalanche, so current payoff dates are
   later and total interest higher than reality.

2. **Unbounded negative amortization.** A minimum payment below the
   monthly interest charge runs the full ``PAYOFF_MAX_MONTHS`` (600) cap
   and reports a nonsense total (see
   ``test_min_payment_below_interest_runs_to_cap`` — $21.6 *billion*).
   There is no guard and nothing tells the user the debt never amortizes.

Date handling: ``payoff_months`` and every dollar figure are independent
of the current date and are pinned exactly. ``payoff_date`` is derived
from ``date.today()`` by the router, so it is asserted against the same
derivation rather than a frozen string. Promo fixtures express
``promo_expires`` relative to today for the same reason.
"""
from datetime import date

import pytest

ENDPOINT = "/api/tools/payoff-plan"


def _month_offset(months: int) -> date:
    """First of the month ``months`` out from today.

    Mirrors the arithmetic in ``routers/tools.py`` so the expected
    ``payoff_date`` tracks whenever the suite happens to run.
    """
    today = date.today()
    return date(
        today.year + (today.month - 1 + months) // 12,
        (today.month - 1 + months) % 12 + 1,
        1,
    )


def _expected_payoff_date(months: int) -> str:
    return _month_offset(months).strftime("%Y-%m")


def _by_name(payload: dict) -> dict:
    return {a["name"]: a for a in payload["accounts"]}


def _post(client, body):
    response = client.post(ENDPOINT, json=body)
    assert response.status_code == 200
    return response.json()


class TestSingleAccount:
    def test_single_card_no_extra(self, client):
        data = _post(client, {
            "accounts": [{"name": "Card A", "balance": 1000.0, "apr": 24.0, "min_payment": 50.0}],
            "strategy": "avalanche",
            "extra_monthly": 0.0,
        })

        assert data["strategy"] == "avalanche"
        assert data["grand_total_interest"] == pytest.approx(289.87)
        assert data["grand_total_months"] == 26
        assert data["interest_saved_vs_minimums"] == pytest.approx(0.0)

        acct = data["accounts"][0]
        assert acct["name"] == "Card A"
        assert acct["payoff_months"] == 26
        assert acct["total_interest"] == pytest.approx(289.87)
        assert acct["promo_expired_before_payoff"] is False
        assert acct["payoff_date"] == _expected_payoff_date(26)

    def test_zero_apr_accrues_no_interest(self, client):
        data = _post(client, {
            "accounts": [{"name": "ZeroAPR", "balance": 1200.0, "apr": 0.0, "min_payment": 100.0}],
            "strategy": "avalanche",
            "extra_monthly": 0.0,
        })

        assert data["grand_total_interest"] == pytest.approx(0.0)
        assert data["grand_total_months"] == 12
        assert data["accounts"][0]["payoff_months"] == 12
        assert data["accounts"][0]["total_interest"] == pytest.approx(0.0)

    def test_min_payment_below_interest_runs_to_cap(self, client):
        """PINNED BUG #2 — negative amortization is unbounded and unflagged.

        $10,000 at 29.99% accrues ~$250/mo interest against a $50 minimum,
        so the balance grows without limit until the 600-month cap. The
        reported total is ~$21.6 billion and the payload carries no signal
        that this debt never amortizes.

        When the guard lands (``amortization.build_schedule`` setting
        ``negative_amortization=True`` and bailing on period 1), update
        this test to assert the flag instead of the cap value.
        """
        data = _post(client, {
            "accounts": [
                {"name": "Underwater", "balance": 10000.0, "apr": 29.99, "min_payment": 50.0}
            ],
            "strategy": "avalanche",
            "extra_monthly": 0.0,
        })

        assert data["grand_total_months"] == 600      # state.PAYOFF_MAX_MONTHS
        assert data["accounts"][0]["payoff_months"] == 600
        assert data["accounts"][0]["total_interest"] == pytest.approx(21639884603.44)


class TestMultipleAccounts:
    _TWO_CARDS = [
        {"name": "High", "balance": 3000.0, "apr": 24.99, "min_payment": 75.0},
        {"name": "Low", "balance": 1500.0, "apr": 9.99, "min_payment": 40.0},
    ]

    def test_two_card_avalanche(self, client):
        data = _post(client, {
            "accounts": self._TWO_CARDS, "strategy": "avalanche", "extra_monthly": 0.0,
        })

        assert data["grand_total_interest"] == pytest.approx(3818.35)
        assert data["grand_total_months"] == 87

        accounts = _by_name(data)
        assert accounts["High"]["payoff_months"] == 87
        assert accounts["High"]["total_interest"] == pytest.approx(3512.71)
        assert accounts["Low"]["payoff_months"] == 46
        assert accounts["Low"]["total_interest"] == pytest.approx(305.64)

    def test_avalanche_orders_highest_apr_first(self, client):
        """Result ordering is the sort order, not the payoff order."""
        data = _post(client, {
            "accounts": self._TWO_CARDS, "strategy": "avalanche", "extra_monthly": 0.0,
        })
        assert [a["name"] for a in data["accounts"]] == ["High", "Low"]

    def test_snowball_orders_lowest_balance_first(self, client):
        data = _post(client, {
            "accounts": self._TWO_CARDS, "strategy": "snowball", "extra_monthly": 0.0,
        })
        assert [a["name"] for a in data["accounts"]] == ["Low", "High"]

    def test_strategy_is_inert_without_extra_payment(self, client):
        """PINNED BUG #1 — avalanche and snowball are indistinguishable here.

        With no extra payment, strategy currently changes only the result
        ordering, never the money: each account pays its own minimum in
        isolation and no freed-up minimum ever cascades. Identical totals
        across both strategies is the symptom.

        After the rollover fix these totals must both DROP (Low frees
        $40/mo into High at month 46). They may still equal each other in
        this two-account case — whichever debt finishes first frees its
        minimum into the survivor either way — so extend
        ``test_three_card_snowball_extra100`` to prove ordering matters.
        """
        avalanche = _post(client, {
            "accounts": self._TWO_CARDS, "strategy": "avalanche", "extra_monthly": 0.0,
        })
        snowball = _post(client, {
            "accounts": self._TWO_CARDS, "strategy": "snowball", "extra_monthly": 0.0,
        })

        assert avalanche["grand_total_interest"] == snowball["grand_total_interest"]
        assert avalanche["grand_total_months"] == snowball["grand_total_months"]

    def test_two_card_avalanche_with_extra(self, client):
        data = _post(client, {
            "accounts": self._TWO_CARDS, "strategy": "avalanche", "extra_monthly": 200.0,
        })

        assert data["grand_total_interest"] == pytest.approx(610.51)
        assert data["grand_total_months"] == 18
        assert data["interest_saved_vs_minimums"] == pytest.approx(3207.84)

        accounts = _by_name(data)
        assert accounts["High"]["payoff_months"] == 13
        assert accounts["High"]["total_interest"] == pytest.approx(439.17)
        assert accounts["Low"]["payoff_months"] == 18
        assert accounts["Low"]["total_interest"] == pytest.approx(171.34)

    def test_three_card_snowball_with_extra(self, client):
        data = _post(client, {
            "accounts": [
                {"name": "A", "balance": 800.0, "apr": 19.99, "min_payment": 25.0},
                {"name": "B", "balance": 2400.0, "apr": 22.99, "min_payment": 60.0},
                {"name": "C", "balance": 5000.0, "apr": 14.5, "min_payment": 100.0},
            ],
            "strategy": "snowball",
            "extra_monthly": 100.0,
        })

        assert data["grand_total_interest"] == pytest.approx(2665.45)
        assert data["grand_total_months"] == 47
        assert data["interest_saved_vs_minimums"] == pytest.approx(2599.88)

        accounts = _by_name(data)
        assert accounts["A"]["payoff_months"] == 7
        assert accounts["A"]["total_interest"] == pytest.approx(53.12)
        assert accounts["B"]["payoff_months"] == 24
        assert accounts["B"]["total_interest"] == pytest.approx(730.57)
        assert accounts["C"]["payoff_months"] == 47
        assert accounts["C"]["total_interest"] == pytest.approx(1881.76)


class TestPromoApr:
    """Deferred-interest windows — the in-flight ``christy-wip`` behavior.

    ``promo_months`` is derived as a whole-month delta from today and
    applied as ``month <= promo_months``, so a promo expiring exactly N
    months out charges the promo rate for N periods. That off-by-one is
    pinned here as-is; correcting it is a separate commit.
    """

    def _promo_body(self, months_until_expiry: int) -> dict:
        return {
            "accounts": [{
                "name": "Promo",
                "balance": 4000.0,
                "apr": 26.99,
                "min_payment": 100.0,
                "promo_apr": 0.0,
                "promo_expires": _month_offset(months_until_expiry).isoformat(),
            }],
            "strategy": "avalanche",
            "extra_monthly": 0.0,
        }

    def test_promo_active_twelve_months(self, client):
        data = _post(client, self._promo_body(12))

        acct = data["accounts"][0]
        assert acct["payoff_months"] == 57
        assert acct["total_interest"] == pytest.approx(1667.47)
        assert acct["promo_expired_before_payoff"] is True

    def test_promo_expiring_sooner_costs_more_interest(self, client):
        data = _post(client, self._promo_body(3))

        acct = data["accounts"][0]
        assert acct["payoff_months"] == 84
        assert acct["total_interest"] == pytest.approx(4325.10)
        assert acct["promo_expired_before_payoff"] is True

    def test_shorter_promo_is_strictly_worse(self, client):
        """The whole point of the promo model — pinned as a relation."""
        long_promo = _post(client, self._promo_body(12))["grand_total_interest"]
        short_promo = _post(client, self._promo_body(3))["grand_total_interest"]
        assert short_promo > long_promo
