"""The proactive coach.

One test per rule with a seeded store, plus the ranking, the dismissal
lifecycle, and the narration guard — which is the highest-risk surface in
the module, because a fabricated dollar figure is one the user might act on.
"""
from datetime import date, timedelta

import pytest

import coach
import state
from db import properties_repo_memory


@pytest.fixture(autouse=True)
def _properties():
    return properties_repo_memory.install_for_tests()


AUG_15 = date(2026, 8, 15)


def _seed_income():
    """Six months of biweekly pay — enough for the income detector."""
    for i, month in enumerate(range(3, 9)):
        for j, day in enumerate((1, 15)):
            tid = f"pay{i}{j}"
            state.stored_transactions[tid] = {
                "id": tid, "transaction_id": tid,
                "date": f"2026-{month:02d}-{day:02d}",
                "description": "ACME CORP DIRECT DEP", "amount": 4000.0,
                "transaction_type": "credit", "source": "simplefin",
                "category": "Income",
            }


def _spend(tid, day, amount, category="Dining"):
    state.stored_transactions[tid] = {
        "id": tid, "transaction_id": tid, "date": day,
        "description": "RESTAURANT", "amount": amount,
        "transaction_type": "debit", "source": "simplefin", "category": category,
    }


def _ids(payload):
    return [a["id"] for a in payload["actions"]]


def _kinds(payload):
    return [a["kind"] for a in payload["actions"]]


class TestDailyAllowance:
    def test_over_budget_says_spend_nothing(self):
        _seed_income()
        _spend("huge", "2026-08-02", 99999)
        actions = coach.build_actions(today=AUG_15)["actions"]
        first = actions[0]
        assert first["kind"] == "spend_less"
        assert first["urgency"] == "now"
        assert first["amount"] == 0.0

    def test_ahead_of_pace_names_a_daily_number(self):
        _seed_income()
        _spend("s1", "2026-08-02", 6000)
        actions = coach.build_actions(today=AUG_15)["actions"]
        allowance = [a for a in actions if a["source"] == "rule:daily_allowance"]
        assert allowance
        assert allowance[0]["amount"] > 0

    def test_on_pace_produces_no_nag(self):
        _seed_income()
        actions = coach.build_actions(today=AUG_15)["actions"]
        assert not [a for a in actions if a["source"] == "rule:daily_allowance"]

    def test_no_income_produces_no_allowance_action(self):
        _spend("s1", "2026-08-02", 100)
        actions = coach.build_actions(today=AUG_15)["actions"]
        assert not [a for a in actions if a["source"] == "rule:daily_allowance"]


class TestBudgetOverspend:
    def test_over_cap_is_flagged_with_the_amount(self):
        _seed_income()
        state.budgets["Dining"] = {"category": "Dining", "monthly_limit": 400}
        _spend("s1", "2026-08-02", 580)

        actions = coach.build_actions(today=AUG_15)["actions"]
        over = [a for a in actions if a["source"] == "rule:budget_overspend"]
        assert over
        assert over[0]["amount"] == pytest.approx(180.0)
        assert "Dining" in over[0]["title"]

    def test_near_the_cap_is_a_softer_nudge(self):
        _seed_income()
        state.budgets["Dining"] = {"category": "Dining", "monthly_limit": 400}
        _spend("s1", "2026-08-02", 380)

        actions = coach.build_actions(today=AUG_15)["actions"]
        near = [a for a in actions if a["id"].startswith("budget_near")]
        assert near
        assert near[0]["urgency"] == "this_month"

    def test_trivial_overruns_are_not_worth_an_action(self):
        _seed_income()
        state.budgets["Dining"] = {"category": "Dining", "monthly_limit": 400}
        _spend("s1", "2026-08-02", 405)
        actions = coach.build_actions(today=AUG_15)["actions"]
        assert not [a for a in actions if a["id"].startswith("over_budget")]


class TestGoalBehind:
    """Pace needs a real contribution signal.

    ``_classify_pace`` returns None without one, deliberately refusing to
    label a goal "behind" when it simply has no evidence either way. So the
    rule only fires for goals linked to an account whose balance history
    shows how fast it is actually growing.
    """

    def _link_account_growing_slowly(self):
        from datetime import datetime, timedelta as td, timezone
        from db import accounts_repo_memory

        state._manual_accounts["sav_1"] = {
            "id": "sav_1", "name": "Savings", "type": "depository",
            "available": 600, "ledger": 600,
        }
        repo = accounts_repo_memory.active()
        now = datetime.now(timezone.utc)
        # $50/month of growth against a goal that needs far more.
        repo.insert_balance_snapshot(
            account_id="sav_1", source="manual", available=550, ledger=550,
            captured_at=(now - td(days=30)).isoformat(),
        )
        repo.insert_balance_snapshot(
            account_id="sav_1", source="manual", available=600, ledger=600,
            captured_at=now.isoformat(),
        )

    def test_behind_goal_names_the_monthly_gap(self):
        _seed_income()
        self._link_account_growing_slowly()
        state.goals["goal_1"] = {
            "id": "goal_1", "name": "Emergency fund", "kind": "emergency_fund",
            "target_amount": 12000, "current_balance": 600,
            "linked_account_id": "sav_1",
            "target_date": "2027-02-01",
        }
        actions = coach.build_actions(today=AUG_15)["actions"]
        behind = [a for a in actions if a["source"] == "rule:goal_behind"]
        assert behind
        assert behind[0]["amount"] > 0
        assert "Emergency fund" in behind[0]["title"]

    def test_a_goal_with_no_contribution_signal_is_left_alone(self):
        """No linked account means no evidence — and no accusation."""
        _seed_income()
        state.goals["goal_1"] = {
            "id": "goal_1", "name": "Vacation", "kind": "travel",
            "target_amount": 12000, "current_balance": 0,
            "target_date": "2027-02-01",
        }
        actions = coach.build_actions(today=AUG_15)["actions"]
        assert not [a for a in actions if a["source"] == "rule:goal_behind"]


class TestPromoApr:
    """The WIP stored promo_expires and nothing consumed it until now."""

    def test_expiring_promo_with_a_balance_is_flagged(self):
        _seed_income()
        state.account_details["card_1"] = {
            "apr": 26.99,
            "promo_apr": 0.0,
            "promo_expires": (AUG_15 + timedelta(days=20)).isoformat(),
        }
        state._manual_accounts["card_1"] = {
            "id": "card_1", "name": "Store Card", "type": "credit", "ledger": -4000,
        }
        actions = coach.build_actions(today=AUG_15)["actions"]
        promo = [a for a in actions if a["source"] == "rule:promo_apr_expiring"]
        assert promo
        assert promo[0]["amount"] == pytest.approx(4000.0)
        assert promo[0]["impact"]["value"] == pytest.approx(1079.6, abs=1)

    def test_a_paid_off_promo_card_is_not_flagged(self):
        _seed_income()
        state.account_details["card_1"] = {
            "apr": 26.99, "promo_apr": 0.0,
            "promo_expires": (AUG_15 + timedelta(days=20)).isoformat(),
        }
        state._manual_accounts["card_1"] = {
            "id": "card_1", "name": "Store Card", "type": "credit", "ledger": 0,
        }
        actions = coach.build_actions(today=AUG_15)["actions"]
        assert not [a for a in actions if a["source"] == "rule:promo_apr_expiring"]

    def test_a_distant_promo_is_not_yet_urgent(self):
        _seed_income()
        state.account_details["card_1"] = {
            "apr": 26.99, "promo_apr": 0.0,
            "promo_expires": (AUG_15 + timedelta(days=200)).isoformat(),
        }
        state._manual_accounts["card_1"] = {
            "id": "card_1", "name": "Store Card", "type": "credit", "ledger": -4000,
        }
        actions = coach.build_actions(today=AUG_15)["actions"]
        assert not [a for a in actions if a["source"] == "rule:promo_apr_expiring"]


class TestPropertyReview:
    def test_underperforming_property_surfaces_with_its_reason(self):
        _seed_income()
        repo = properties_repo_memory.active()
        repo.upsert_property({
            "id": "prop_1", "name": "Money Pit", "status": "rental",
            "monthly_rent": 500, "property_tax_annual": 12000,
        })
        actions = coach.build_actions(today=AUG_15)["actions"]
        review = [a for a in actions if a["source"] == "rule:property_underperforming"]
        assert review
        assert "Money Pit" in review[0]["title"]
        assert review[0]["detail"]


class TestEmergencyFund:
    def test_thin_cash_buffer_is_flagged(self):
        _seed_income()
        state.account_details["card_1"] = {"minimum_payment": 500}
        state._manual_accounts["chk"] = {
            "id": "chk", "name": "Checking", "type": "depository",
            "available": 300, "ledger": 300,
        }
        actions = coach.build_actions(today=AUG_15)["actions"]
        fund = [a for a in actions if a["source"] == "rule:emergency_fund_floor"]
        assert fund
        assert fund[0]["amount"] > 0

    def test_healthy_buffer_is_silent(self):
        _seed_income()
        state.account_details["card_1"] = {"minimum_payment": 100}
        state._manual_accounts["chk"] = {
            "id": "chk", "name": "Checking", "type": "depository",
            "available": 50000, "ledger": 50000,
        }
        actions = coach.build_actions(today=AUG_15)["actions"]
        assert not [a for a in actions if a["source"] == "rule:emergency_fund_floor"]


class TestRanking:
    def test_today_outranks_a_much_larger_long_horizon_number(self):
        """A $38k lifetime saving is a bigger figure than a $200 overspend,
        but only one of them is about today."""
        _seed_income()
        _spend("huge", "2026-08-02", 99999)
        repo = properties_repo_memory.active()
        repo.upsert_loan({
            "id": "loan_1", "name": "Mortgage",
            "original_principal": 400000, "interest_rate_pct": 7.0,
            "term_months": 360, "origination_date": date(2020, 1, 1),
            "first_payment_date": date(2020, 2, 1),
        })
        payload = coach.build_actions(today=AUG_15)
        assert payload["actions"][0]["urgency"] == "now"
        assert payload["actions"][0]["kind"] == "spend_less"

    def test_actions_carry_a_rank(self):
        _seed_income()
        _spend("huge", "2026-08-02", 99999)
        actions = coach.build_actions(today=AUG_15)["actions"]
        assert [a["rank"] for a in actions] == list(range(1, len(actions) + 1))

    def test_the_list_is_capped(self):
        _seed_income()
        _spend("huge", "2026-08-02", 99999)
        for i in range(12):
            state.budgets[f"Cat{i}"] = {"category": f"Cat{i}", "monthly_limit": 10}
            _spend(f"c{i}", "2026-08-03", 500, category=f"Cat{i}")

        payload = coach.build_actions(today=AUG_15, limit=5)
        assert len(payload["actions"]) == 5
        assert payload["total"] > 5

    def test_counts_are_reported_by_urgency(self):
        _seed_income()
        _spend("huge", "2026-08-02", 99999)
        payload = coach.build_actions(today=AUG_15)
        assert sum(payload["counts"].values()) == payload["total"]


class TestResilience:
    def test_empty_data_yields_an_empty_feed_not_an_error(self):
        payload = coach.build_actions(today=AUG_15)
        assert payload["actions"] == []
        assert payload["total"] == 0

    def test_one_broken_rule_does_not_blank_the_feed(self, monkeypatch):
        _seed_income()
        _spend("huge", "2026-08-02", 99999)

        def exploding(ctx):
            raise RuntimeError("boom")

        monkeypatch.setattr(coach, "RULES", (exploding, coach.rule_daily_allowance))
        payload = coach.build_actions(today=AUG_15)
        assert payload["total"] == 1


class TestDismissal:
    def test_dismissed_actions_disappear(self, client):
        _seed_income()
        _spend("huge", "2026-08-02", 99999)
        first = coach.build_actions(today=AUG_15)["actions"][0]["id"]

        assert client.post(
            f"/api/coach/actions/{first}/dismiss"
        ).status_code == 204
        assert first not in _ids(coach.build_actions(today=AUG_15))

    def test_undismissing_restores_it(self, client):
        _seed_income()
        _spend("huge", "2026-08-02", 99999)
        first = coach.build_actions(today=AUG_15)["actions"][0]["id"]

        client.post(f"/api/coach/actions/{first}/dismiss")
        client.delete(f"/api/coach/actions/{first}/dismiss")
        assert first in _ids(coach.build_actions(today=AUG_15))

    def test_ids_embed_the_period_so_dismissals_expire(self):
        """Dismissing August's Dining warning must not silence September's."""
        _seed_income()
        state.budgets["Dining"] = {"category": "Dining", "monthly_limit": 400}
        _spend("aug", "2026-08-02", 580)
        aug = [a for a in coach.build_actions(today=AUG_15)["actions"]
               if a["id"].startswith("over_budget")][0]["id"]
        assert aug.endswith("2026-08")


class TestNarrationGuard:
    """The highest-risk surface here: a fabricated figure the user acts on."""

    ACTIONS = [{
        "title": "Dining is $180 over",
        "detail": "$580 spent against a $400 cap.",
        "amount": 180.0,
        "impact": {"label": "over cap", "value": 180.0},
        "why": ["145% of the monthly cap used"],
    }]

    def test_accepts_narration_using_only_supplied_figures(self):
        assert coach.verify_narration(
            "You're $180 over on Dining — $580 against a $400 cap.", self.ACTIONS
        )

    def test_rejects_an_invented_figure(self):
        assert not coach.verify_narration(
            "You're $180 over on Dining, and you'll save $4,200 next year.",
            self.ACTIONS,
        )

    def test_rejects_a_subtly_wrong_restatement(self):
        """$185 is close enough to look right and is still fabricated."""
        assert not coach.verify_narration(
            "You're $185 over on Dining.", self.ACTIONS
        )

    def test_allows_small_integers_as_prose(self):
        assert coach.verify_narration(
            "There are 3 things to look at; Dining is $180 over.", self.ACTIONS
        )

    def test_tolerates_thousands_separators(self):
        actions = [{"title": "x", "detail": "y", "amount": 1840.0, "impact": None,
                    "why": []}]
        assert coach.verify_narration("That saves $1,840.", actions)

    def test_empty_narration_is_rejected(self):
        assert not coach.verify_narration("", self.ACTIONS)

    def test_prose_without_numbers_is_fine(self):
        assert coach.verify_narration(
            "Dining is running hot this month — ease off.", self.ACTIONS
        )


class TestEndpoint:
    def test_returns_the_feed(self, client):
        _seed_income()
        _spend("huge", "2026-08-02", 99999)
        response = client.get("/api/coach/actions")
        assert response.status_code == 200
        assert response.json()["actions"]

    def test_respects_the_limit(self, client):
        _seed_income()
        _spend("huge", "2026-08-02", 99999)
        assert len(client.get(
            "/api/coach/actions", params={"limit": 1}
        ).json()["actions"]) <= 1

    def test_accepts_an_as_of_date(self, client):
        _seed_income()
        assert client.get(
            "/api/coach/actions", params={"as_of": "2026-08-15"}
        ).json()["generated_at"] == "2026-08-15"

    def test_rejects_a_bad_date(self, client):
        assert client.get(
            "/api/coach/actions", params={"as_of": "08/15/2026"}
        ).status_code == 422

    def test_alerts_endpoint_is_untouched(self, client):
        """The AlertsCard still depends on it."""
        assert client.get("/api/alerts").status_code == 200
