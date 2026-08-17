"""Real estate's contribution to net worth.

Before this existed, net worth was ``cash + investments - credit``: a
mortgage arrived from the bank as a credit account and was subtracted, while
the house securing it counted for nothing. A household with real equity read
as deeply negative.

The correction has one trap, and most of this file guards it. Property value
has to be added *without* the mortgage being subtracted twice — once as the
synced credit account, once as property debt. Which side owns the debt
depends on whether the loan is linked to an account the caller already
counted, so that's the axis these tests move along.
"""
from datetime import date

import pytest

import properties
from db import properties_repo_memory


@pytest.fixture
def repo():
    return properties_repo_memory.install_for_tests()


def _property(repo, pid="prop_1", value=400000, **overrides):
    row = {
        "id": pid,
        "name": "Maple St Duplex",
        "status": "rental",
        "current_value": value,
    }
    row.update(overrides)
    return repo.upsert_property(row)


def _loan(repo, lid="loan_1", **overrides):
    row = {
        "id": lid,
        "name": "Mortgage",
        "property_id": "prop_1",
        "original_principal": 240000,
        "current_principal": 200000,
        "interest_rate_pct": 6.0,
        "term_months": 360,
        "origination_date": date(2020, 1, 1),
        "first_payment_date": date(2020, 2, 1),
        "payment_amount": 1438.92,
        "lien_position": 1,
    }
    row.update(overrides)
    return repo.upsert_loan(row)


class TestDoubleCountingTrap:
    """A mortgage must be subtracted exactly once, whichever side owns it."""

    def test_linked_debt_is_not_re_subtracted(self, repo):
        """The account is already in the caller's credit total, so the loan
        reports as linked and the caller subtracts nothing further."""
        _property(repo)
        _loan(repo, account_id="acct_chase")

        pos = properties.compute_real_estate_position({"acct_chase"})

        assert pos["linked_debt"] == 200000
        assert pos["unlinked_debt"] == 0
        # What the caller adds to net worth: value only.
        assert pos["total_value"] - pos["unlinked_debt"] == 400000

    def test_unlinked_debt_must_be_subtracted(self, repo):
        """A hand-entered loan appears in no account total, so it is the
        caller's job to subtract it — the mirror of the case above."""
        _property(repo)
        _loan(repo, account_id=None)

        pos = properties.compute_real_estate_position({"acct_chase"})

        assert pos["linked_debt"] == 0
        assert pos["unlinked_debt"] == 200000
        assert pos["total_value"] - pos["unlinked_debt"] == 200000

    def test_equity_is_the_same_either_way(self, repo):
        """Where the debt is *counted* changes; what the household is *worth*
        does not. Equity is the invariant across both arrangements."""
        _property(repo)
        _loan(repo, account_id="acct_chase")
        linked = properties.compute_real_estate_position({"acct_chase"})

        repo.upsert_loan({**repo.get_loan("loan_1"), "account_id": None})
        unlinked = properties.compute_real_estate_position({"acct_chase"})

        assert linked["total_equity"] == unlinked["total_equity"] == 200000

    def test_account_linked_but_not_counted_is_unlinked(self, repo):
        """Carrying an ``account_id`` isn't enough — the account has to be one
        the caller actually summed. A loan pointing at a stale or removed
        account would otherwise vanish from net worth entirely."""
        _property(repo)
        _loan(repo, account_id="acct_closed")

        pos = properties.compute_real_estate_position({"acct_chase"})

        assert pos["unlinked_debt"] == 200000

    def test_no_counted_ids_treats_everything_as_unlinked(self, repo):
        """The conservative default: subtract the debt rather than assume
        somebody else did."""
        _property(repo)
        _loan(repo, account_id="acct_chase")

        assert properties.compute_real_estate_position()["unlinked_debt"] == 200000


class TestValuation:
    def test_unvalued_property_is_named_not_silently_dropped(self, repo):
        """A property with no valuation contributes nothing — that part is
        unavoidable. Naming it is what makes the hole fixable."""
        _property(repo, value=400000)
        _property(repo, pid="prop_2", name="Davie", value=None)

        pos = properties.compute_real_estate_position()

        assert pos["total_value"] == 400000
        assert pos["property_count"] == 2
        assert pos["valued_count"] == 1
        assert pos["unvalued_properties"] == ["Davie"]

    def test_non_property_loan_is_ignored(self, repo):
        """An auto loan is not a real-estate position, and its account is
        already counted as ordinary credit."""
        _property(repo)
        _loan(repo, lid="loan_car", property_id=None, loan_type="auto")

        pos = properties.compute_real_estate_position()

        assert pos["total_debt"] == 0


class TestHistorical:
    def test_valuation_as_of_uses_the_value_that_stood_then(self, repo):
        _property(repo, value=400000)
        repo.add_valuation(
            property_id="prop_1", as_of=date(2024, 1, 1), value=300000
        )
        repo.add_valuation(
            property_id="prop_1", as_of=date(2025, 1, 1), value=400000
        )

        assert properties.real_estate_at(date(2024, 6, 1))["total_value"] == 300000
        assert properties.real_estate_at(date(2025, 6, 1))["total_value"] == 400000

    def test_value_carries_backward_when_history_predates_valuations(self, repo):
        """Contributing zero would draw a cliff on the net-worth chart — a
        leap the size of a house on the day the first valuation was typed in,
        which reads as a real event and isn't one."""
        _property(repo, value=400000)
        repo.add_valuation(
            property_id="prop_1", as_of=date(2025, 1, 1), value=400000
        )

        assert properties.real_estate_at(date(2020, 1, 1))["total_value"] == 400000

    def test_historical_debt_ignores_the_live_account_balance(self, repo):
        """A linked account reports today's balance, not the one that stood on
        the target date, so history has to come off the schedule instead."""
        _property(repo)
        _loan(repo, account_id=None, current_principal=100000)

        early = properties.real_estate_at(date(2021, 1, 1))["unlinked_debt"]
        later = properties.real_estate_at(date(2024, 1, 1))["unlinked_debt"]

        # Amortized, not the stored 100000, and paying down over time.
        assert early > later
        # 11 payments in: principal moves slowly this early in the schedule.
        assert early == pytest.approx(237052.79, abs=1.0)

    def test_counted_history_skips_snapshotted_mortgage(self, repo):
        """The snapshot for that date already subtracted the mortgage."""
        _property(repo)
        _loan(repo, account_id="acct_chase")

        pos = properties.real_estate_at(date(2024, 1, 1), {"acct_chase"})

        assert pos["unlinked_debt"] == 0
        assert pos["net_contribution"] == 400000
