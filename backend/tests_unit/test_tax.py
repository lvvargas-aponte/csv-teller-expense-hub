"""Tax treatment labelling — inference, and the user override that beats it."""
from datetime import date
import pytest

import state
import tax


def _acct(account_id="a1", subtype="401k", acct_type="investment"):
    return {"id": account_id, "type": acct_type, "subtype": subtype}


def _set_details(acct, **fields):
    state.account_details[acct["id"]] = {"account_id": acct["id"], **fields}


class TestInferTreatment:
    @pytest.mark.parametrize("subtype,expected", [
        ("roth_ira", "roth"),
        ("roth ira", "roth"),
        ("roth", "roth"),
        ("401k", "traditional"),
        ("401(k)", "traditional"),
        ("403b", "traditional"),
        ("403(b)", "traditional"),
        ("ira", "traditional"),
        ("sep_ira", "traditional"),
        ("simple_ira", "traditional"),
        ("hsa", "hsa"),
        ("529", "education"),
        ("brokerage", "taxable"),
    ])
    def test_known_subtypes(self, subtype, expected):
        assert tax.infer_treatment(subtype) == expected

    def test_rollover_ira_infers_traditional(self):
        assert tax.infer_treatment("rollover_ira") == "traditional"

    @pytest.mark.parametrize("subtype", ["investment", "retirement", "checking", "", None])
    def test_ambiguous_subtypes_are_not_guessed(self, subtype):
        assert tax.infer_treatment(subtype) is None


class TestEffectiveTreatment:
    def test_falls_back_to_inference_when_the_user_has_said_nothing(self):
        assert tax.effective_treatment(_acct(subtype="401k")) == "traditional"

    def test_user_choice_overrides_inference(self):
        acct = _acct(subtype="401k")          # would infer 'traditional'
        _set_details(acct, tax_treatment="roth")   # a Roth 401(k)
        assert tax.effective_treatment(acct) == "roth"

    def test_user_choice_supplies_a_treatment_inference_has_none_for(self):
        acct = _acct(subtype="retirement")
        assert tax.effective_treatment(acct) is None
        _set_details(acct, tax_treatment="traditional")
        assert tax.effective_treatment(acct) == "traditional"


class TestDescribe:
    def test_inference_is_reported_as_an_assumption_not_a_commitment(self):
        out = tax.describe(_acct(subtype="401k"))
        assert out == {
            "treatment": "traditional",
            "inferred": "traditional",
            "set_by_user": False,
        }

    def test_a_user_value_is_marked_as_set_and_still_reports_the_inference(self):
        acct = _acct(subtype="401k")
        _set_details(acct, tax_treatment="roth")
        out = tax.describe(acct)
        assert out["treatment"] == "roth"
        assert out["inferred"] == "traditional"
        assert out["set_by_user"] is True


class TestRetirementProjectionUsesTreatment:
    """B3's follow-through: the projection prefers retirement-labelled money."""

    @pytest.mark.asyncio
    async def test_taxable_brokerage_is_split_out_of_the_retirement_pot(self):
        import retirement
        from db import accounts_repo_memory

        def seed(account_id, name, value, subtype):
            state._manual_accounts[account_id] = {
                "id": account_id, "institution": "Fidelity", "name": name,
                "type": "investment", "subtype": subtype,
                "available": value, "ledger": value, "manual": True,
            }
            accounts_repo_memory.active().upsert_manual_account(
                account_id=account_id, institution="Fidelity", name=name,
                type_="investment", subtype=subtype,
            )

        seed("k401", "Employer 401(k)", 100000.0, "401k")
        seed("brk", "Taxable brokerage", 40000.0, "brokerage")
        state.user_profile_cache = {}

        from db import profile_repo
        original = profile_repo.load
        profile_repo.load = lambda: {
            "birth_year": 1990, "target_retirement_age": 65,
            "annual_retirement_spend": 60000.0, "expected_return_pct": 6.0,
            "risk_tolerance": "balanced",
        }
        try:
            out = await retirement.project(today=date(2026, 1, 1))
        finally:
            profile_repo.load = original

        assert out["available"] is True
        assert out["current_balance"] == 100000.0
        assert out["balance_split"] == {
            "retirement": 100000.0, "other": 40000.0, "basis": "tax_treatment",
        }


class TestSummaryCarriesTreatment:
    @pytest.mark.asyncio
    async def test_investment_rows_carry_the_label_and_its_provenance(self):
        import balances_service
        from db import accounts_repo_memory

        state._manual_accounts["k401"] = {
            "id": "k401", "institution": "Fidelity", "name": "Employer 401(k)",
            "type": "investment", "subtype": "401k",
            "available": 100000.0, "ledger": 100000.0, "manual": True,
        }
        accounts_repo_memory.active().upsert_manual_account(
            account_id="k401", institution="Fidelity", name="Employer 401(k)",
            type_="investment", subtype="401k",
        )
        state.account_details["k401"] = {
            "account_id": "k401", "tax_treatment": "roth",
        }

        summary = await balances_service.build_summary()
        row = next(a for a in summary.accounts if a.id == "k401")

        assert row.tax_treatment == "roth"
        assert row.tax_treatment_inferred == "traditional"
        assert row.tax_treatment_set_by_user is True


def _seed_investment(account_id, name, value, subtype):
    from db import accounts_repo_memory

    state._manual_accounts[account_id] = {
        "id": account_id, "institution": "Fidelity", "name": name,
        "type": "investment", "subtype": subtype,
        "available": value, "ledger": value, "manual": True,
    }
    accounts_repo_memory.active().upsert_manual_account(
        account_id=account_id, institution="Fidelity", name=name,
        type_="investment", subtype=subtype,
    )


@pytest.fixture
def profile(monkeypatch):
    """Stand in for the household profile row without a database."""
    row = {}
    from db import profile_repo

    monkeypatch.setattr(profile_repo, "load_quietly", lambda: dict(row))
    return row


class TestAfterTaxNetWorth:
    @pytest.mark.asyncio
    async def test_traditional_balance_is_discounted_at_the_stated_rate(self, profile):
        profile.update(marginal_tax_rate_pct=22.0, show_after_tax_net_worth=True)
        _seed_investment("k401", "Employer 401(k)", 200000.0, "401k")

        out = await tax.after_tax_net_worth()

        assert out["available"] is True
        assert out["pre_tax_balance"] == 200000.0
        assert out["deferred_tax_estimate"] == 44000.0
        assert out["rate_pct"] == 22.0
        assert out["rate_source"] == "profile"
        assert out["headline_net_worth"] == 200000.0
        assert out["after_tax_net_worth"] == 156000.0
        assert "estimate" in out["note"].lower()

    @pytest.mark.asyncio
    async def test_roth_hsa_and_taxable_balances_are_left_alone(self, profile):
        profile.update(marginal_tax_rate_pct=22.0, show_after_tax_net_worth=True)
        _seed_investment("roth1", "Roth IRA", 50000.0, "roth_ira")
        _seed_investment("hsa1", "HSA", 10000.0, "hsa")
        # Taxing a brokerage needs per-lot basis and holding periods; a flat
        # rate on the whole balance would be wrong in the user's disfavour.
        _seed_investment("brk", "Brokerage", 40000.0, "brokerage")

        out = await tax.after_tax_net_worth()

        assert out["pre_tax_balance"] == 0.0
        assert out["deferred_tax_estimate"] == 0.0
        assert out["after_tax_net_worth"] == out["headline_net_worth"] == 100000.0

    @pytest.mark.asyncio
    async def test_a_blank_rate_is_unavailable_rather_than_inferred(self, profile):
        profile.update(show_after_tax_net_worth=True)
        _seed_investment("k401", "Employer 401(k)", 200000.0, "401k")

        out = await tax.after_tax_net_worth()

        assert out["available"] is False
        assert "marginal" in out["reason"].lower()
        assert out.get("after_tax_net_worth") is None

    @pytest.mark.asyncio
    async def test_the_setting_is_opt_in_so_off_produces_nothing(self, profile):
        profile.update(marginal_tax_rate_pct=22.0)
        _seed_investment("k401", "Employer 401(k)", 200000.0, "401k")

        out = await tax.after_tax_net_worth()

        assert out["available"] is False
        assert out.get("after_tax_net_worth") is None

    @pytest.mark.asyncio
    async def test_a_user_set_roth_401k_is_not_discounted(self, profile):
        profile.update(marginal_tax_rate_pct=22.0, show_after_tax_net_worth=True)
        _seed_investment("k401", "Employer 401(k)", 200000.0, "401k")
        state.account_details["k401"] = {
            "account_id": "k401", "tax_treatment": "roth",
        }

        out = await tax.after_tax_net_worth()

        assert out["pre_tax_balance"] == 0.0
        assert out["after_tax_net_worth"] == 200000.0


@pytest.fixture
def contributions(monkeypatch):
    """Stand in for B2's detection — D3's job starts once the rows exist."""
    import retirement

    rows = []

    async def fake():
        return {
            "monthly_total": round(sum(r["monthly"] for r in rows), 2),
            "by_account": rows,
            "confidence": "high",
            "caveat": None,
        }

    monkeypatch.setattr(retirement, "estimate_contributions", fake)
    return rows


def _contributing(rows, account_id, name, monthly, method="recurring_transfer"):
    rows.append({
        "account_id": account_id, "name": name, "monthly": monthly,
        "method": method, "confidence": "high" if method == "recurring_transfer" else "low",
    })


def _group(out, key):
    return next(g for g in out["groups"] if g["key"] == key)


class TestContributionHeadroom:
    @pytest.mark.asyncio
    async def test_ytd_against_the_limit_produces_headroom(self, profile, contributions):
        profile.update(birth_year=1990)
        _seed_investment("roth1", "Fidelity Roth IRA", 42000.0, "roth_ira")
        _contributing(contributions, "roth1", "Fidelity Roth IRA", 525.0)

        out = await tax.contribution_headroom(today=date(2026, 9, 1))

        assert out["available"] is True
        assert out["year"] == 2026
        assert out["catch_up_eligible"] is False
        ira = _group(out, "ira")
        assert ira["ytd"] == 4200.0
        assert ira["limit"] == 7500.0
        assert ira["headroom"] == 3300.0
        assert ira["months_remaining"] == 4.0
        assert ira["monthly_to_use_remaining"] == 825.0
        assert ira["approximate"] is False

    @pytest.mark.asyncio
    async def test_missing_year_returns_unavailable_not_a_stale_limit(
        self, profile, contributions
    ):
        out = await tax.contribution_headroom(today=date(2099, 3, 1))
        assert out["available"] is False
        assert "2099" in out["reason"]

    @pytest.mark.asyncio
    async def test_catch_up_applies_from_the_year_the_user_turns_fifty(
        self, profile, contributions
    ):
        profile.update(birth_year=1976)   # turns 50 in 2026
        _seed_investment("ira1", "Vanguard IRA", 80000.0, "ira")
        _contributing(contributions, "ira1", "Vanguard IRA", 100.0)

        out = await tax.contribution_headroom(today=date(2026, 9, 1))

        assert out["catch_up_eligible"] is True
        assert _group(out, "ira")["limit"] == 8600.0

    @pytest.mark.asyncio
    async def test_iras_pool_together_and_the_workplace_plan_stands_apart(
        self, profile, contributions
    ):
        profile.update(birth_year=1990)
        _seed_investment("roth1", "Roth IRA", 42000.0, "roth_ira")
        _seed_investment("ira1", "Traditional IRA", 30000.0, "ira")
        _seed_investment("k401", "Employer 401(k)", 200000.0, "401k")
        _contributing(contributions, "roth1", "Roth IRA", 300.0)
        _contributing(contributions, "ira1", "Traditional IRA", 200.0)
        _contributing(contributions, "k401", "Employer 401(k)", 1000.0)

        out = await tax.contribution_headroom(today=date(2026, 9, 1))

        assert _group(out, "ira")["ytd"] == 4000.0
        assert _group(out, "ira")["limit"] == 7500.0
        assert _group(out, "workplace")["ytd"] == 8000.0
        assert _group(out, "workplace")["limit"] == 24500.0

    @pytest.mark.asyncio
    async def test_hsa_is_reported_without_a_limit_rather_than_a_guessed_one(
        self, profile, contributions
    ):
        profile.update(birth_year=1990)
        _seed_investment("hsa1", "Fidelity HSA", 9000.0, "hsa")
        _contributing(contributions, "hsa1", "Fidelity HSA", 300.0)

        out = await tax.contribution_headroom(today=date(2026, 9, 1))

        hsa = _group(out, "hsa")
        assert hsa["ytd"] == 2400.0
        assert hsa["limit"] is None
        assert hsa["headroom"] is None
        assert "coverage" in hsa["limit_note"].lower()

    @pytest.mark.asyncio
    async def test_velocity_derived_rows_mark_the_group_approximate(
        self, profile, contributions
    ):
        profile.update(birth_year=1990)
        _seed_investment("k401", "Employer 401(k)", 200000.0, "401k")
        _contributing(
            contributions, "k401", "Employer 401(k)", 1000.0, method="snapshot_velocity"
        )

        out = await tax.contribution_headroom(today=date(2026, 9, 1))

        workplace = _group(out, "workplace")
        assert workplace["approximate"] is True
        assert "growth" in workplace["approximate_reason"].lower()

    @pytest.mark.asyncio
    async def test_a_taxable_brokerage_has_no_limit_to_compare_against(
        self, profile, contributions
    ):
        profile.update(birth_year=1990)
        _seed_investment("brk", "Brokerage", 40000.0, "brokerage")
        _contributing(contributions, "brk", "Brokerage", 500.0)

        out = await tax.contribution_headroom(today=date(2026, 9, 1))

        assert out["groups"] == []
