"""User profile — PR6 of the data-gap initiative.

Pins the GET/PUT contract for the household profile and its inclusion
in the advisor's financial snapshot. Profile data lets the advisor
tailor risk-appropriate / dependents-aware recommendations.
"""
from sqlalchemy import text

from db.base import sync_engine


def _read_row():
    with sync_engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT risk_tolerance, time_horizon_years, dependents, "
                "       debt_strategy, notes FROM user_profile "
                "WHERE id = 'household'"
            )
        ).fetchone()


class TestGetProfile:
    def test_get_when_unset_returns_empty_shell(self, client):
        r = client.get("/api/profile")
        assert r.status_code == 200
        body = r.json()
        assert body["risk_tolerance"] is None
        assert body["time_horizon_years"] is None
        assert body["dependents"] is None
        assert body["debt_strategy"] is None
        assert body["monthly_income"] is None
        assert body["emergency_fund_months"] is None
        assert body["notes"] == ""


class TestPutProfile:
    def test_put_then_get_round_trips(self, client):
        r = client.put("/api/profile", json={
            "risk_tolerance": "balanced",
            "time_horizon_years": 25,
            "dependents": 2,
            "debt_strategy": "avalanche",
            "notes": "HCOL area, dual income",
        })
        assert r.status_code == 200
        assert r.json()["risk_tolerance"] == "balanced"

        r2 = client.get("/api/profile")
        assert r2.status_code == 200
        body = r2.json()
        assert body["risk_tolerance"] == "balanced"
        assert body["time_horizon_years"] == 25
        assert body["dependents"] == 2
        assert body["debt_strategy"] == "avalanche"
        assert body["notes"] == "HCOL area, dual income"

    def test_partial_put_preserves_unspecified_fields(self, client):
        client.put("/api/profile", json={
            "risk_tolerance": "balanced",
            "time_horizon_years": 25,
            "debt_strategy": "avalanche",
        })
        # Update only debt_strategy; others should remain.
        r = client.put("/api/profile", json={"debt_strategy": "snowball"})
        assert r.status_code == 200
        body = r.json()
        assert body["debt_strategy"] == "snowball"
        assert body["risk_tolerance"] == "balanced"      # untouched
        assert body["time_horizon_years"] == 25          # untouched

    def test_income_and_emergency_fund_round_trip(self, client):
        r = client.put("/api/profile", json={
            "monthly_income": 6250.50,
            "emergency_fund_months": 6,
        })
        assert r.status_code == 200
        body = client.get("/api/profile").json()
        assert body["monthly_income"] == 6250.50
        assert body["emergency_fund_months"] == 6

    def test_explicit_null_clears_a_field(self, client):
        """The settings page's "Not set" option sends null. Presence — not
        nullness — decides what changes, so this must actually unset."""
        client.put("/api/profile", json={
            "debt_strategy": "avalanche",
            "emergency_fund_months": 6,
            "risk_tolerance": "balanced",
        })

        r = client.put("/api/profile", json={
            "debt_strategy": None,
            "emergency_fund_months": None,
        })

        assert r.status_code == 200
        body = r.json()
        assert body["debt_strategy"] is None
        assert body["emergency_fund_months"] is None
        assert body["risk_tolerance"] == "balanced"   # omitted key untouched

    def test_null_notes_stores_empty_string(self, client):
        """notes is NOT NULL — clearing it means "", never NULL."""
        client.put("/api/profile", json={"notes": "something"})
        r = client.put("/api/profile", json={"notes": None})
        assert r.status_code == 200
        assert r.json()["notes"] == ""

    def test_put_with_invalid_enum_value_rejected(self, client):
        r = client.put("/api/profile", json={"risk_tolerance": "yolo"})
        # Pydantic Literal validation kicks in before any DB write.
        assert r.status_code == 422

    def test_empty_put_is_a_noop(self, client):
        # Empty body — nothing should be written.
        r = client.put("/api/profile", json={})
        assert r.status_code == 200
        # No row was created.
        assert _read_row() is None


class TestSnapshotIntegration:
    def test_user_profile_omitted_when_unset(self, client):
        from analytics import build_financial_snapshot
        snap = build_financial_snapshot()
        assert "user_profile" not in snap

    def test_user_profile_included_when_set(self, client):
        client.put("/api/profile", json={
            "risk_tolerance": "aggressive",
            "time_horizon_years": 30,
            "dependents": 0,
        })
        from analytics import build_financial_snapshot
        snap = build_financial_snapshot()
        assert "user_profile" in snap
        prof = snap["user_profile"]
        assert prof["risk_tolerance"] == "aggressive"
        assert prof["time_horizon_years"] == 30
        assert prof["dependents"] == 0
        # Unset enum fields not echoed back.
        assert "debt_strategy" not in prof

    def test_income_and_reserves_reach_the_advisor(self, client):
        client.put("/api/profile", json={
            "monthly_income": 6250.0,
            "emergency_fund_months": 6,
        })
        from analytics import build_financial_snapshot
        prof = build_financial_snapshot()["user_profile"]
        assert prof["monthly_income"] == 6250.0
        assert prof["emergency_fund_months"] == 6


class TestRetirementFields:
    """B1 — birth year, target age, target spend and expected return.

    The merge semantics are the load-bearing part: adding columns is where
    exclude_unset gets quietly broken, so the round-trip is asserted
    alongside both "omitted preserves" and "null clears".
    """

    def test_retirement_fields_round_trip(self, client):
        r = client.put("/api/profile", json={
            "birth_year": 1990,
            "target_retirement_age": 60,
            "annual_retirement_spend": 60000.0,
            "expected_return_pct": 5.5,
        })
        assert r.status_code == 200

        body = client.get("/api/profile").json()
        assert body["birth_year"] == 1990
        assert body["target_retirement_age"] == 60
        assert body["annual_retirement_spend"] == 60000.0
        assert body["expected_return_pct"] == 5.5

    def test_omitted_retirement_fields_are_preserved(self, client):
        client.put("/api/profile", json={
            "birth_year": 1985,
            "target_retirement_age": 65,
            "annual_retirement_spend": 48000.0,
        })
        r = client.put("/api/profile", json={"target_retirement_age": 62})
        assert r.status_code == 200
        body = r.json()
        assert body["target_retirement_age"] == 62
        assert body["birth_year"] == 1985                  # untouched
        assert body["annual_retirement_spend"] == 48000.0  # untouched

    def test_explicit_null_clears_a_retirement_field(self, client):
        client.put("/api/profile", json={
            "birth_year": 1985,
            "expected_return_pct": 7.0,
        })
        r = client.put("/api/profile", json={"expected_return_pct": None})
        assert r.status_code == 200
        body = r.json()
        assert body["expected_return_pct"] is None
        assert body["birth_year"] == 1985

    def test_unset_retirement_fields_read_as_none(self, client):
        body = client.get("/api/profile").json()
        assert body["birth_year"] is None
        assert body["target_retirement_age"] is None
        assert body["annual_retirement_spend"] is None
        assert body["expected_return_pct"] is None
