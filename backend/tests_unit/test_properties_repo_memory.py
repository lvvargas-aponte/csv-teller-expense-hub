"""Semantics of the in-memory PropertiesRepo twin.

The twin exists so tests_unit can run without Postgres, which only works if
it behaves like the SQL it stands in for. These cover the behaviours the
rest of the code depends on; ``tests/test_properties_repo.py`` asserts the
same things against a real database, where FK cascades and constraints are
actually enforced rather than emulated.
"""
from datetime import date

import pytest

from db import properties_repo, properties_repo_memory


@pytest.fixture
def repo():
    return properties_repo_memory.install_for_tests()


def _property(pid="prop_1", **overrides):
    row = {
        "id": pid,
        "name": "Maple St Duplex",
        "address": "12 Maple St",
        "property_type": "multi_family",
        "status": "rental",
        "units": 2,
        "purchase_date": date(2021, 6, 1),
        "purchase_price": 320000,
        "monthly_rent": 3200,
    }
    row.update(overrides)
    return row


def _loan(lid="loan_1", **overrides):
    row = {
        "id": lid,
        "name": "Maple St Mortgage",
        "loan_type": "mortgage",
        "property_id": "prop_1",
        "original_principal": 256000,
        "interest_rate_pct": 3.75,
        "term_months": 360,
        "origination_date": date(2021, 6, 1),
        "lien_position": 1,
    }
    row.update(overrides)
    return row


class TestProperties:
    def test_upsert_then_get_round_trips(self, repo):
        repo.upsert_property(_property())
        found = repo.get_property("prop_1")
        assert found["name"] == "Maple St Duplex"
        assert found["units"] == 2

    def test_dates_come_back_as_iso_strings(self, repo):
        """Matches PgPropertiesRepo, which converts at the boundary."""
        repo.upsert_property(_property())
        assert repo.get_property("prop_1")["purchase_date"] == "2021-06-01"

    def test_get_missing_returns_none(self, repo):
        assert repo.get_property("nope") is None

    def test_upsert_overwrites_the_same_id(self, repo):
        repo.upsert_property(_property())
        repo.upsert_property(_property(name="Renamed"))
        assert len(repo.list_properties()) == 1
        assert repo.get_property("prop_1")["name"] == "Renamed"

    def test_list_is_sorted_by_name(self, repo):
        repo.upsert_property(_property("prop_1", name="Zeta"))
        repo.upsert_property(_property("prop_2", name="Alpha"))
        assert [p["name"] for p in repo.list_properties()] == ["Alpha", "Zeta"]

    def test_returned_rows_are_copies(self, repo):
        """Mutating a result must not corrupt the store."""
        repo.upsert_property(_property())
        repo.get_property("prop_1")["name"] = "Mutated"
        assert repo.get_property("prop_1")["name"] == "Maple St Duplex"

    def test_delete_reports_rows_removed(self, repo):
        repo.upsert_property(_property())
        assert repo.delete_property("prop_1") == 1
        assert repo.delete_property("prop_1") == 0


class TestValuations:
    def test_first_valuation_sets_current_value(self, repo):
        repo.upsert_property(_property())
        repo.add_valuation(property_id="prop_1", as_of=date(2026, 1, 1), value=410000)
        assert repo.get_property("prop_1")["current_value"] == 410000

    def test_same_day_revaluation_overwrites(self, repo):
        repo.upsert_property(_property())
        repo.add_valuation(property_id="prop_1", as_of=date(2026, 1, 1), value=400000)
        repo.add_valuation(property_id="prop_1", as_of=date(2026, 1, 1), value=415000)
        assert len(repo.list_valuations("prop_1")) == 1
        assert repo.get_property("prop_1")["current_value"] == 415000

    def test_newer_valuation_moves_current_value(self, repo):
        repo.upsert_property(_property())
        repo.add_valuation(property_id="prop_1", as_of=date(2025, 1, 1), value=380000)
        repo.add_valuation(property_id="prop_1", as_of=date(2026, 1, 1), value=410000)
        assert repo.get_property("prop_1")["current_value"] == 410000

    def test_backfilling_an_older_valuation_does_not_clobber_current(self, repo):
        """Adding a 2019 appraisal must not overwrite a 2026 value."""
        repo.upsert_property(_property())
        repo.add_valuation(property_id="prop_1", as_of=date(2026, 1, 1), value=410000)
        repo.add_valuation(property_id="prop_1", as_of=date(2019, 1, 1), value=250000)
        assert repo.get_property("prop_1")["current_value"] == 410000

    def test_list_is_newest_first(self, repo):
        repo.upsert_property(_property())
        for year, value in ((2024, 350000), (2026, 410000), (2025, 380000)):
            repo.add_valuation(
                property_id="prop_1", as_of=date(year, 1, 1), value=value
            )
        assert [v["as_of"] for v in repo.list_valuations("prop_1")] == [
            "2026-01-01", "2025-01-01", "2024-01-01"
        ]

    def test_upsert_property_preserves_current_value(self, repo):
        """Editing a property must not wipe the denormalized valuation."""
        repo.upsert_property(_property())
        repo.add_valuation(property_id="prop_1", as_of=date(2026, 1, 1), value=410000)
        repo.upsert_property(_property(name="Edited"))
        assert repo.get_property("prop_1")["current_value"] == 410000


class TestLoans:
    def test_upsert_then_get_round_trips(self, repo):
        repo.upsert_loan(_loan())
        found = repo.get_loan("loan_1")
        assert found["original_principal"] == 256000
        assert found["interest_rate_pct"] == 3.75
        assert found["origination_date"] == "2021-06-01"

    def test_filter_by_property(self, repo):
        repo.upsert_loan(_loan("loan_1", property_id="prop_1"))
        repo.upsert_loan(_loan("loan_2", property_id="prop_2"))
        repo.upsert_loan(_loan("loan_3", property_id=None, loan_type="auto"))

        assert [l["id"] for l in repo.list_loans("prop_1")] == ["loan_1"]
        assert len(repo.list_loans()) == 3

    def test_sorted_by_lien_position(self, repo):
        repo.upsert_loan(_loan("loan_2", name="HELOC", lien_position=2))
        repo.upsert_loan(_loan("loan_1", name="First", lien_position=1))
        assert [l["name"] for l in repo.list_loans()] == ["First", "HELOC"]

    def test_delete_reports_rows_removed(self, repo):
        repo.upsert_loan(_loan())
        assert repo.delete_loan("loan_1") == 1
        assert repo.delete_loan("loan_1") == 0


class TestCascades:
    def test_deleting_a_property_removes_its_valuations(self, repo):
        repo.upsert_property(_property())
        repo.add_valuation(property_id="prop_1", as_of=date(2026, 1, 1), value=410000)
        repo.delete_property("prop_1")
        assert repo.list_valuations("prop_1") == []

    def test_deleting_a_property_removes_its_rental_terms(self, repo):
        repo.upsert_property(_property())
        repo.replace_rental_terms("prop_1", [{"unit_label": "A", "monthly_rent": 1600}])
        repo.delete_property("prop_1")
        assert repo.list_rental_terms("prop_1") == []

    def test_deleting_a_property_orphans_but_keeps_its_loans(self, repo):
        """ON DELETE SET NULL, not CASCADE — selling the asset must never
        silently delete the debt record."""
        repo.upsert_property(_property())
        repo.upsert_loan(_loan())
        repo.delete_property("prop_1")

        survivor = repo.get_loan("loan_1")
        assert survivor is not None
        assert survivor["property_id"] is None


class TestRentalTerms:
    def test_replace_is_wholesale_not_merge(self, repo):
        repo.replace_rental_terms("prop_1", [
            {"unit_label": "A", "monthly_rent": 1600},
            {"unit_label": "B", "monthly_rent": 1600},
        ])
        repo.replace_rental_terms("prop_1", [{"unit_label": "A", "monthly_rent": 1700}])

        terms = repo.list_rental_terms("prop_1")
        assert len(terms) == 1
        assert terms[0]["monthly_rent"] == 1700

    def test_sorted_by_unit_label(self, repo):
        repo.replace_rental_terms("prop_1", [
            {"unit_label": "B", "monthly_rent": 1600},
            {"unit_label": "A", "monthly_rent": 1500},
        ])
        assert [t["unit_label"] for t in repo.list_rental_terms("prop_1")] == ["A", "B"]

    def test_empty_for_unknown_property(self, repo):
        assert repo.list_rental_terms("nope") == []


class TestRepoSwap:
    def test_install_for_tests_replaces_the_active_repo(self, repo):
        assert properties_repo.get_repo() is repo

    def test_reset_clears_state_without_reinstalling(self, repo):
        repo.upsert_property(_property())
        properties_repo_memory.reset()
        assert properties_repo.get_repo() is repo
        assert repo.list_properties() == []

    def test_twin_implements_the_whole_protocol(self, repo):
        """Guards against the twin drifting behind PropertiesRepo."""
        required = [
            name for name in dir(properties_repo.PropertiesRepo)
            if not name.startswith("_")
        ]
        missing = [name for name in required if not hasattr(repo, name)]
        assert missing == []
