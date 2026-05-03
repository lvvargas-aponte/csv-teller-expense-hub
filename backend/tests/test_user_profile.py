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
