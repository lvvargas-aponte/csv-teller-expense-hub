"""Allocation waterfall — ordering, refusals, and the deferred-interest trap.

The tier order is the whole product here, so most of these assert *sequence*
rather than arithmetic: a correct total split the wrong way round is still
wrong advice.
"""
from datetime import date, timedelta

import pytest

import allocation
from allocation import (
    AllocationContext,
    DebtSlot,
    EmployerMatch,
    MortgageSlot,
    PropertyFund,
    allocate,
    effective_apr,
)


TODAY = date(2026, 8, 15)


def _debt(name="Card", balance=5000.0, apr=24.0, **kw) -> DebtSlot:
    rate = kw.pop("effective_apr", apr)
    return DebtSlot(
        id=kw.pop("id", name.lower()),
        name=name,
        balance=balance,
        apr=apr,
        effective_apr=rate,
        rate_basis=kw.pop("rate_basis", f"{rate:.2f}% — stated APR"),
        **kw,
    )


def _ctx(**kw) -> AllocationContext:
    base = dict(
        monthly_essential_spend=2000.0,
        cash_on_hand=6000.0,          # funded: 3 x 2000
        emergency_fund_months=3,
        investment_return_pct=7.0,
        tax_rate_on_withdrawals_pct=15.0,
        employer_match_known=False,
        contribution_limits={"ira": 7500.0},
        contribution_limits_year=2026,
    )
    base.update(kw)
    return AllocationContext(**base)


def _keys(result):
    return [a["key"] for a in result["allocations"]]


# ---------------------------------------------------------------------------
# Effective APR
# ---------------------------------------------------------------------------

def test_effective_apr_plain_card_is_its_stated_rate():
    rate, basis = effective_apr(apr=22.99, today=TODAY)
    assert rate == 22.99
    assert basis == "stated APR"


def test_deferred_interest_promo_is_priced_at_the_full_regular_rate():
    """The trap: a 0% deferred-interest promo is a full-rate debt today.

    Interest accrues from day one and is only waived on full payoff, so
    ranking it at its nominal 0% is how a $6k balance turns into a
    four-figure surprise.
    """
    rate, basis = effective_apr(
        apr=26.99,
        promo_apr=0.0,
        promo_expires=(TODAY + timedelta(days=120)).isoformat(),
        deferred_interest=True,
        today=TODAY,
    )
    assert rate == 26.99
    assert "deferred interest" in basis
    assert "waived" in basis


def test_true_promo_rate_blends_over_the_next_twelve_months():
    """Six months at 0%, six at 24% -> ~12% for a one-year comparison."""
    rate, basis = effective_apr(
        apr=24.0,
        promo_apr=0.0,
        promo_expires=(TODAY + timedelta(days=183)).isoformat(),
        deferred_interest=False,
        today=TODAY,
    )
    assert 11.0 < rate < 13.0
    assert "blended" in basis


def test_true_promo_further_out_than_a_year_stays_near_the_promo_rate():
    rate, _ = effective_apr(
        apr=24.0,
        promo_apr=0.0,
        promo_expires=(TODAY + timedelta(days=800)).isoformat(),
        today=TODAY,
    )
    assert rate == 0.0


def test_expired_promo_falls_back_to_the_regular_rate():
    rate, basis = effective_apr(
        apr=24.0,
        promo_apr=0.0,
        promo_expires=(TODAY - timedelta(days=5)).isoformat(),
        today=TODAY,
    )
    assert rate == 24.0
    assert "expired" in basis


# ---------------------------------------------------------------------------
# Tier 1 — employer match
# ---------------------------------------------------------------------------

def test_unknown_employer_match_asks_rather_than_assuming_zero():
    result = allocate(500.0, _ctx(employer_match_known=None))
    assert [q["key"] for q in result["questions"]] == ["employer_match"]
    # And it must not block the rest of the waterfall.
    assert result["allocations"]


def test_employer_match_outranks_a_twenty_six_percent_card():
    ctx = _ctx(
        employer_match_known=True,
        employer_match=EmployerMatch(
            match_pct=50.0, limit_pct_of_pay=6.0, annual_gross_income=120_000.0
        ),
        debts=[_debt(apr=26.0, effective_apr=26.0)],
    )
    result = allocate(1000.0, ctx)
    assert _keys(result)[0] == "employer_match"
    # 120k x 6% / 12 = $600/mo matched.
    assert result["allocations"][0]["amount"] == 600.0
    assert result["allocations"][0]["quantified_benefit"]["value"] == 300.0


def test_a_lump_sum_cannot_capture_a_payroll_match():
    ctx = _ctx(
        employer_match_known=True,
        employer_match=EmployerMatch(
            match_pct=100.0, limit_pct_of_pay=4.0, annual_gross_income=90_000.0
        ),
    )
    result = allocate(5000.0, ctx, cadence="one_time")
    assert "employer_match" not in _keys(result)
    skipped = {s["key"]: s for s in result["skipped"]}
    assert "paycheck" in skipped["employer_match"]["reason"]


# ---------------------------------------------------------------------------
# Tier 2 — emergency floor
# ---------------------------------------------------------------------------

def test_emergency_floor_halts_every_lower_tier():
    ctx = _ctx(cash_on_hand=500.0, debts=[_debt(apr=29.0, effective_apr=29.0)])
    result = allocate(1000.0, ctx)

    assert _keys(result) == ["emergency_fund"]
    assert result["allocations"][0]["amount"] == 1000.0
    assert any(s["key"] == "below_emergency_floor" for s in result["skipped"])


def test_a_partly_filled_floor_releases_the_remainder_downstream():
    """$300 short of the target, $1,000 to place: $300 up, $700 onward."""
    ctx = _ctx(cash_on_hand=5700.0, debts=[_debt(apr=29.0, effective_apr=29.0)])
    result = allocate(1000.0, ctx)

    assert _keys(result)[:2] == ["emergency_fund", "high_interest_debt"]
    assert result["allocations"][0]["amount"] == 300.0
    assert result["allocations"][1]["amount"] == 700.0


def test_a_funded_buffer_is_reported_as_skipped_not_silently_omitted():
    result = allocate(500.0, _ctx())
    skipped = {s["key"] for s in result["skipped"]}
    assert "emergency_fund" in skipped


def test_holding_the_buffer_ahead_of_expensive_debt_is_priced_in_the_caveats():
    """The one contested call in the waterfall must not be silent."""
    ctx = _ctx(cash_on_hand=1000.0, debts=[_debt(balance=8000.0, apr=27.0, effective_apr=27.0)])
    result = allocate(400.0, ctx)

    priced = [c for c in result["caveats"] if "2,160" in c]
    assert priced, result["caveats"]
    assert "starter buffer" in priced[0]


# ---------------------------------------------------------------------------
# Tier 3 — high-interest debt
# ---------------------------------------------------------------------------

def test_only_debt_above_the_expected_return_is_paid_down_early():
    ctx = _ctx(debts=[
        _debt(name="Visa", apr=24.0, effective_apr=24.0),
        _debt(name="Car loan", apr=4.5, effective_apr=4.5, id="car"),
    ])
    result = allocate(1000.0, ctx)

    debt_rows = [a for a in result["allocations"] if a["key"] == "high_interest_debt"]
    assert [a["label"] for a in debt_rows] == ["Pay down Visa"]


def test_avalanche_orders_by_rate_and_snowball_by_balance():
    # The rate and the balance point opposite ways, which is the only
    # arrangement where the two strategies are distinguishable.
    debts = [
        _debt(name="Big", balance=9000.0, apr=25.0, effective_apr=25.0, id="big"),
        _debt(name="Small", balance=800.0, apr=19.0, effective_apr=19.0, id="small"),
    ]
    avalanche = allocate(400.0, _ctx(debts=debts, debt_strategy="avalanche"))
    snowball = allocate(400.0, _ctx(debts=debts, debt_strategy="snowball"))

    assert avalanche["allocations"][0]["label"] == "Pay down Big"     # 25% first
    assert snowball["allocations"][0]["label"] == "Pay down Small"    # $800 first
    assert "avalanche" in avalanche["allocations"][0]["rationale"]
    assert "snowball" in snowball["allocations"][0]["rationale"]


def test_an_allocation_never_exceeds_the_balance_it_targets():
    ctx = _ctx(debts=[_debt(name="Nearly clear", balance=150.0, apr=26.0, effective_apr=26.0)])
    result = allocate(1000.0, ctx)

    debt_row = next(a for a in result["allocations"] if a["key"] == "high_interest_debt")
    assert debt_row["amount"] == 150.0


def test_debt_payoff_is_labelled_a_guaranteed_return():
    ctx = _ctx(debts=[_debt(apr=24.0, effective_apr=24.0)])
    result = allocate(1200.0, ctx, cadence="one_time")
    row = next(a for a in result["allocations"] if a["key"] == "high_interest_debt")
    assert row["quantified_benefit"]["guaranteed"] is True
    # A one-time $1,200 at 24% avoids a full year of interest on it.
    assert row["quantified_benefit"]["value"] == pytest.approx(288.0)


# ---------------------------------------------------------------------------
# Tier 4 — tax-advantaged room
# ---------------------------------------------------------------------------

def test_missing_contribution_room_asks_rather_than_assuming():
    result = allocate(500.0, _ctx(contribution_limits={}))
    assert any(q["key"] == "contribution_room" for q in result["questions"])


def test_exhausted_room_is_skipped_with_its_reason():
    ctx = _ctx(contribution_limits={"ira": 7500.0}, contributed_ytd={"ira": 7500.0})
    result = allocate(500.0, ctx)
    skipped = {s["key"]: s for s in result["skipped"]}
    assert "already used" in skipped["tax_advantaged"]["reason"]


def test_the_limits_year_is_always_stated():
    result = allocate(500.0, _ctx())
    assert any("2026" in c for c in result["caveats"])
    assert result["assumptions"]["contribution_limits_year"] == 2026


# ---------------------------------------------------------------------------
# Honesty about the inputs
# ---------------------------------------------------------------------------

def test_an_essentials_figure_missing_its_bills_is_flagged():
    """The buffer gates every lower tier, so an undersized target quietly
    waves money past a stop it should have hit."""
    result = allocate(500.0, _ctx(essentials_include_bills=False))
    thin = [c for c in result["caveats"] if "No recurring bills" in c]
    assert thin
    assert "very likely higher" in thin[0]


def test_a_complete_essentials_figure_carries_no_such_warning():
    result = allocate(500.0, _ctx())
    assert not any("No recurring bills" in c for c in result["caveats"])


# ---------------------------------------------------------------------------
# Tier 5 — property fund
# ---------------------------------------------------------------------------

def test_property_fund_takes_its_monthly_requirement():
    ctx = _ctx(
        contribution_limits={},
        property_fund=PropertyFund(
            goal_id="goal_1", name="Duplex down payment",
            monthly_required=800.0, remaining=40_000.0,
        ),
    )
    result = allocate(1000.0, ctx)
    row = next(a for a in result["allocations"] if a["key"] == "property_fund")
    assert row["amount"] == 800.0
    assert row["target_id"] == "goal_1"


def test_property_goal_detection_needs_both_kind_and_a_property_word():
    goals = [
        {"id": "g1", "kind": "savings", "name": "House down payment",
         "target_amount": 50000, "current_balance": 0},
        {"id": "g2", "kind": "big_purchase", "name": "New kitchen",
         "target_amount": 20000, "current_balance": 0},
        {"id": "g3", "kind": "big_purchase", "name": "Duplex down payment",
         "target_amount": 60000, "current_balance": 10000, "monthly_required": 900},
    ]
    fund = allocation._property_fund_from_goals(goals)
    assert fund is not None
    assert fund.goal_id == "g3"
    assert fund.remaining == 50_000.0


def test_a_fully_funded_property_goal_is_not_offered():
    goals = [{"id": "g1", "kind": "big_purchase", "name": "Rental down payment",
              "target_amount": 30000, "current_balance": 30000}]
    assert allocation._property_fund_from_goals(goals) is None


# ---------------------------------------------------------------------------
# Tier 6 — brokerage vs. extra principal
# ---------------------------------------------------------------------------

def _mortgage(rate=6.5) -> MortgageSlot:
    return MortgageSlot(
        id="loan_1", name="123 Oak St", balance=250_000.0, rate_pct=rate,
        payment=1580.17, term_months=360, months_elapsed=24,
        first_payment_date="2024-08-01",
    )


def test_a_cheap_mortgage_loses_to_the_market_and_says_why():
    """5.95% after-tax return beats a 3.25% mortgage."""
    ctx = _ctx(contribution_limits={}, mortgages=[_mortgage(rate=3.25)])
    result = allocate(1000.0, ctx)

    assert _keys(result)[-1] == "taxable_investing"
    skipped = {s["key"]: s for s in result["skipped"]}
    assert "extra_mortgage_principal" in skipped
    assert "3.25%" in skipped["extra_mortgage_principal"]["reason"]
    assert "5.95%" in skipped["extra_mortgage_principal"]["reason"]


def test_an_expensive_mortgage_beats_the_market():
    ctx = _ctx(contribution_limits={}, mortgages=[_mortgage(rate=7.75)])
    result = allocate(1000.0, ctx)

    assert _keys(result)[-1] == "extra_mortgage_principal"
    row = result["allocations"][-1]
    assert row["target_id"] == "loan_1"
    assert row["quantified_benefit"]["guaranteed"] is True


def test_deductibility_is_a_caveat_never_a_calculation():
    ctx = _ctx(mortgages=[_mortgage()])
    result = allocate(1000.0, ctx)
    cpa = [c for c in result["caveats"] if "CPA" in c]
    assert cpa
    assert "deductible" in cpa[0]


# ---------------------------------------------------------------------------
# The waterfall as a whole
# ---------------------------------------------------------------------------

def test_tiers_run_in_order_and_the_full_amount_is_accounted_for():
    ctx = _ctx(
        cash_on_hand=5000.0,                       # $1,000 short of the floor
        employer_match_known=True,
        employer_match=EmployerMatch(
            match_pct=50.0, limit_pct_of_pay=3.0, annual_gross_income=96_000.0
        ),                                          # $240/mo
        debts=[_debt(name="Visa", balance=1500.0, apr=24.0, effective_apr=24.0)],
        contribution_limits={"ira": 7500.0},        # $625/mo
        property_fund=PropertyFund("g1", "Duplex fund", 500.0, 40_000.0),
        mortgages=[_mortgage(rate=3.0)],
    )
    result = allocate(4000.0, ctx)

    assert _keys(result) == [
        "employer_match",
        "emergency_fund",
        "high_interest_debt",
        "tax_advantaged",
        "property_fund",
        "taxable_investing",
    ]
    assert [a["tier"] for a in result["allocations"]] == [1, 2, 3, 4, 5, 6]
    assert result["allocated"] == 4000.0
    assert result["unallocated"] == 0.0


def test_every_allocation_carries_a_rationale():
    ctx = _ctx(debts=[_debt()], mortgages=[_mortgage()])
    result = allocate(3000.0, ctx)
    assert all(a["rationale"] for a in result["allocations"])
    assert all(a["quantified_benefit"] for a in result["allocations"])


def test_zero_declines_rather_than_returning_an_empty_plan():
    result = allocate(0.0, _ctx())
    assert result["available"] is False
    assert result["reason"] == "no_amount"


def test_a_bare_context_still_produces_a_usable_answer():
    """No debts, no properties, no goals — the money still has to go somewhere."""
    result = allocate(300.0, AllocationContext())
    assert result["available"] is True
    assert _keys(result)[-1] == "taxable_investing"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

class TestEndpoints:
    def test_allocate_returns_a_plan(self, client):
        response = client.post("/api/tools/allocate", json={"amount": 500})
        assert response.status_code == 200
        body = response.json()
        assert body["available"] is True
        assert body["allocated"] + body["unallocated"] == 500.0

    def test_a_non_positive_amount_is_rejected_by_validation(self, client):
        assert client.post("/api/tools/allocate", json={"amount": 0}).status_code == 422

    def test_cadence_is_echoed_back(self, client):
        body = client.post(
            "/api/tools/allocate", json={"amount": 5000, "cadence": "one_time"},
        ).json()
        assert body["cadence"] == "one_time"

    def test_settings_default_to_an_unanswered_employer_match(self, client):
        body = client.get("/api/tools/allocation-settings").json()
        assert body["employer_match_known"] is None
        assert body["emergency_fund_months"] == 3
        assert body["contribution_limits_as_of_year"] == 2026

    def test_settings_merge_rather_than_replace(self, client):
        client.put("/api/tools/allocation-settings", json={"emergency_fund_months": 6})
        client.put("/api/tools/allocation-settings", json={"annual_gross_income": 90000})
        body = client.get("/api/tools/allocation-settings").json()
        assert body["emergency_fund_months"] == 6
        assert body["annual_gross_income"] == 90000

    def test_answering_the_match_question_removes_it(self, client):
        before = client.post("/api/tools/allocate", json={"amount": 500}).json()
        assert any(q["key"] == "employer_match" for q in before["questions"])

        client.put("/api/tools/allocation-settings", json={
            "employer_match_known": True,
            "employer_match_pct": 50,
            "employer_match_limit_pct_of_pay": 6,
            "annual_gross_income": 120000,
        })
        after = client.post("/api/tools/allocate", json={"amount": 500}).json()
        assert not any(q["key"] == "employer_match" for q in after["questions"])
        assert after["allocations"][0]["key"] == "employer_match"
