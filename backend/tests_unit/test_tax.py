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
