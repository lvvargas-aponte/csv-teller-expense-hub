"""PgPropertiesRepo against a real database.

Deliberately narrower than ``tests_unit/test_properties_repo_memory.py``.
That suite covers CRUD semantics against the in-memory twin; this one
covers the things only Postgres can actually prove — foreign keys, ON
DELETE behaviour, the unique constraint, and Numeric -> float conversion at
the boundary. Together they keep the twin honest.
"""
from datetime import date

import pytest
from sqlalchemy import text

from db import properties_repo
from db.base import sync_engine
from db.properties_repo import PgPropertiesRepo


@pytest.fixture
def repo():
    """The real Postgres repo, regardless of any in-memory swap."""
    return PgPropertiesRepo()


@pytest.fixture
def account_id():
    """A real accounts row, so FK-bearing columns have a valid target."""
    aid = "acct_props_test"
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO accounts (id, source, institution, name, type, manual) "
                "VALUES (:id, 'manual', 'Test Bank', 'Operating', 'depository', true) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"id": aid},
        )
    return aid


def _property(pid="prop_pg_1", **overrides):
    row = {
        "id": pid,
        "name": "Maple St Duplex",
        "address": "12 Maple St",
        "property_type": "multi_family",
        "status": "rental",
        "units": 2,
        "purchase_date": date(2021, 6, 1),
        "purchase_price": 320000,
        "closing_costs": 7400,
        "monthly_rent": 3200,
        "vacancy_rate_pct": 5,
    }
    row.update(overrides)
    return row


def _loan(lid="loan_pg_1", **overrides):
    row = {
        "id": lid,
        "name": "Maple St Mortgage",
        "loan_type": "mortgage",
        "property_id": "prop_pg_1",
        "original_principal": 256000,
        "interest_rate_pct": 3.75,
        "term_months": 360,
        "origination_date": date(2021, 6, 1),
        "lien_position": 1,
        "escrow_monthly": 420,
    }
    row.update(overrides)
    return row


class TestTypeConversion:
    def test_numeric_columns_come_back_as_float_not_decimal(self, repo):
        """Decimal must not leak into analytics — it would infect every
        arithmetic site downstream."""
        repo.upsert_property(_property())
        found = repo.get_property("prop_pg_1")

        assert isinstance(found["purchase_price"], float)
        assert isinstance(found["vacancy_rate_pct"], float)
        assert found["purchase_price"] == 320000.0

    def test_dates_come_back_as_iso_strings(self, repo):
        repo.upsert_property(_property())
        assert repo.get_property("prop_pg_1")["purchase_date"] == "2021-06-01"

    def test_rate_precision_survives_the_round_trip(self, repo):
        """Numeric(6,3) matches account_details.apr, so a mortgage rate and a
        card APR round-trip identically."""
        repo.upsert_property(_property())
        repo.upsert_loan(_loan(interest_rate_pct=6.875))
        assert repo.get_loan("loan_pg_1")["interest_rate_pct"] == 6.875

    def test_jsonb_rules_default_to_an_empty_list(self, repo):
        repo.upsert_property(_property())
        assert repo.get_property("prop_pg_1")["rules"] == []


class TestUpsert:
    def test_second_upsert_updates_rather_than_duplicating(self, repo):
        repo.upsert_property(_property())
        repo.upsert_property(_property(name="Renamed", units=3))

        assert len(repo.list_properties()) == 1
        found = repo.get_property("prop_pg_1")
        assert found["name"] == "Renamed"
        assert found["units"] == 3

    def test_upsert_returns_the_stored_row(self, repo):
        returned = repo.upsert_property(_property())
        assert returned["id"] == "prop_pg_1"
        assert returned["name"] == "Maple St Duplex"

    def test_updated_at_advances_on_update(self, repo):
        first = repo.upsert_property(_property())
        second = repo.upsert_property(_property(name="Renamed"))
        assert second["updated_at"] >= first["updated_at"]


class TestValuationConstraint:
    def test_unique_per_property_per_day_upserts(self, repo):
        repo.upsert_property(_property())
        repo.add_valuation(
            property_id="prop_pg_1", as_of=date(2026, 1, 1), value=400000
        )
        repo.add_valuation(
            property_id="prop_pg_1", as_of=date(2026, 1, 1), value=415000
        )

        valuations = repo.list_valuations("prop_pg_1")
        assert len(valuations) == 1
        assert valuations[0]["value"] == 415000.0

    def test_current_value_denormalization_tracks_the_newest(self, repo):
        repo.upsert_property(_property())
        repo.add_valuation(
            property_id="prop_pg_1", as_of=date(2025, 1, 1), value=380000
        )
        repo.add_valuation(
            property_id="prop_pg_1", as_of=date(2026, 1, 1), value=410000
        )
        assert repo.get_property("prop_pg_1")["current_value"] == 410000.0

        # Backfilling an older appraisal must not clobber the current number.
        repo.add_valuation(
            property_id="prop_pg_1", as_of=date(2019, 1, 1), value=250000
        )
        assert repo.get_property("prop_pg_1")["current_value"] == 410000.0


class TestForeignKeys:
    def test_operating_account_link_resolves(self, repo, account_id):
        repo.upsert_property(_property(operating_account_id=account_id))
        assert repo.get_property("prop_pg_1")["operating_account_id"] == account_id

    def test_deleting_a_property_cascades_into_valuations(self, repo):
        repo.upsert_property(_property())
        repo.add_valuation(
            property_id="prop_pg_1", as_of=date(2026, 1, 1), value=410000
        )
        repo.delete_property("prop_pg_1")
        assert repo.list_valuations("prop_pg_1") == []

    def test_deleting_a_property_cascades_into_rental_terms(self, repo):
        repo.upsert_property(_property())
        repo.replace_rental_terms(
            "prop_pg_1", [{"unit_label": "A", "monthly_rent": 1600}]
        )
        repo.delete_property("prop_pg_1")
        assert repo.list_rental_terms("prop_pg_1") == []

    def test_deleting_a_property_orphans_but_keeps_its_loans(self, repo):
        """ON DELETE SET NULL. Selling the house must not delete the mortgage
        record — the debt history outlives the asset."""
        repo.upsert_property(_property())
        repo.upsert_loan(_loan())
        repo.delete_property("prop_pg_1")

        survivor = repo.get_loan("loan_pg_1")
        assert survivor is not None
        assert survivor["property_id"] is None

    def test_deleting_an_account_orphans_but_keeps_its_loan(self, repo, account_id):
        repo.upsert_property(_property())
        repo.upsert_loan(_loan(account_id=account_id))

        with sync_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM accounts WHERE id = :id"), {"id": account_id}
            )

        survivor = repo.get_loan("loan_pg_1")
        assert survivor is not None
        assert survivor["account_id"] is None


class TestOrdering:
    def test_properties_sorted_by_name(self, repo):
        repo.upsert_property(_property("prop_pg_1", name="Zeta"))
        repo.upsert_property(_property("prop_pg_2", name="Alpha"))
        assert [p["name"] for p in repo.list_properties()] == ["Alpha", "Zeta"]

    def test_loans_sorted_by_lien_position(self, repo):
        repo.upsert_property(_property())
        repo.upsert_loan(_loan("loan_pg_2", name="HELOC", lien_position=2))
        repo.upsert_loan(_loan("loan_pg_1", name="First", lien_position=1))
        assert [l["name"] for l in repo.list_loans()] == ["First", "HELOC"]

    def test_loans_filtered_by_property(self, repo):
        repo.upsert_property(_property("prop_pg_1"))
        repo.upsert_property(_property("prop_pg_2", name="Other"))
        repo.upsert_loan(_loan("loan_pg_1", property_id="prop_pg_1"))
        repo.upsert_loan(_loan("loan_pg_2", property_id="prop_pg_2"))
        repo.upsert_loan(_loan("loan_pg_3", property_id=None, loan_type="auto"))

        assert [l["id"] for l in repo.list_loans("prop_pg_1")] == ["loan_pg_1"]
        assert len(repo.list_loans()) == 3


class TestDefaultRepo:
    def test_production_default_is_the_postgres_repo(self):
        """The module-level default must be Pg — the in-memory twin is only
        ever installed by a conftest."""
        import importlib
        fresh = importlib.reload(properties_repo)
        assert isinstance(fresh.get_repo(), fresh.PgPropertiesRepo)
