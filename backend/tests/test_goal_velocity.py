"""Goal contribution velocity — PR5 of the data-gap initiative.

Turns the previously-passive ``monthly_required`` figure into an active
``pace_status`` by reading the goal's linked account from the
``balance_snapshots`` timeseries.

Tests use the live Postgres test DB so the SQL ``get_snapshots_since``
window logic is exercised end-to-end.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

import state
from db.base import sync_engine


def _insert_account(account_id: str, type_: str = "depository") -> None:
    """Add the account everywhere ``compute_goal_statuses`` will look for it.

    Two stores are involved: the structured ``accounts`` table (for
    balance-snapshot FK and ``get_snapshots_since``) and the in-memory
    manual-accounts dict (for ``_account_balance_by_id`` to surface the
    live balance). Real router code keeps these in sync; tests must do
    the same.
    """
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO accounts (id, source, name, type, manual) "
                "VALUES (:id, 'manual', :id, :type, true) "
                "ON CONFLICT (id) DO UPDATE SET type = EXCLUDED.type"
            ),
            {"id": account_id, "type": type_},
        )
    state._manual_accounts[account_id] = {
        "id": account_id,
        "institution": "Test",
        "name": account_id,
        "type": type_,
        "subtype": "",
        "available": 0.0,
        "ledger": 0.0,
    }


def _set_manual_balance(account_id: str, available: float) -> None:
    """Update the in-memory manual account's live balance — what
    ``_account_balance_by_id`` returns to ``compute_goal_statuses``."""
    acct = state._manual_accounts.get(account_id)
    if acct is None:
        return
    acct["available"] = float(available)
    state._manual_accounts[account_id] = acct


def _insert_snapshot(
    account_id: str,
    available: float,
    days_ago: float,
) -> None:
    captured = datetime.now(timezone.utc) - timedelta(days=days_ago)
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO balance_snapshots "
                "  (account_id, captured_at, available, source) "
                "VALUES (:aid, :ts, :avail, 'manual')"
            ),
            {"aid": account_id, "ts": captured, "avail": available},
        )


def _seed_goal(
    goal_id: str,
    name: str,
    target_amount: float,
    linked_account_id: str | None,
    target_date: str | None,
    kind: str = "savings",
) -> None:
    state.goals[goal_id] = {
        "id": goal_id,
        "name": name,
        "target_amount": target_amount,
        "current_balance": 0.0,
        "linked_account_id": linked_account_id,
        "target_date": target_date,
        "kind": kind,
        "notes": "",
    }


@pytest.fixture(autouse=True)
def _clear_goals():
    state.goals.clear()
    state._manual_accounts.clear()
    yield
    state.goals.clear()
    state._manual_accounts.clear()


class TestClassifyPace:
    def test_returns_none_when_inputs_missing(self):
        from analytics import _classify_pace
        assert _classify_pace(None, 100.0) is None
        assert _classify_pace(100.0, None) is None

    def test_returns_none_when_required_zero_or_negative(self):
        from analytics import _classify_pace
        assert _classify_pace(50.0, 0.0) is None
        assert _classify_pace(50.0, -10.0) is None

    def test_stalled_when_actual_zero_or_negative(self):
        from analytics import _classify_pace
        assert _classify_pace(0.0, 100.0) == "stalled"
        assert _classify_pace(-50.0, 100.0) == "stalled"

    def test_on_track_within_ten_percent_band(self):
        from analytics import _classify_pace
        assert _classify_pace(95.0, 100.0) == "on_track"
        assert _classify_pace(100.0, 100.0) == "on_track"
        assert _classify_pace(109.0, 100.0) == "on_track"

    def test_ahead_at_or_above_one_ten_ratio(self):
        from analytics import _classify_pace
        assert _classify_pace(120.0, 100.0) == "ahead"
        assert _classify_pace(200.0, 100.0) == "ahead"

    def test_behind_when_positive_but_below_ninety_percent(self):
        from analytics import _classify_pace
        assert _classify_pace(50.0, 100.0) == "behind"
        assert _classify_pace(89.0, 100.0) == "behind"


class TestGoalVelocityIntegration:
    def test_no_linked_account_keeps_velocity_fields_none(self):
        _seed_goal(
            "g1", "Vacation", 5000.0,
            linked_account_id=None,
            target_date="2027-01-01",
        )
        from analytics import compute_goal_statuses
        out = compute_goal_statuses()
        assert len(out) == 1
        g = out[0]
        assert g["actual_monthly_contribution"] is None
        assert g["pace_status"] is None
        # Existing fields still produced.
        assert g["monthly_required"] is not None

    def test_on_track_when_savings_match_required_pace(self):
        _insert_account("save1", "depository")
        # Started at $1000 thirty days ago, now $1500 → ~$500/mo contribution.
        _insert_snapshot("save1", 1000.0, days_ago=29)
        _insert_snapshot("save1", 1500.0, days_ago=0.1)
        _set_manual_balance("save1", 1500.0)

        # Goal needs $500/mo for 10 months ($5000 target, no current balance,
        # 10 months remaining).
        future = (datetime.now(timezone.utc).date() + timedelta(days=305)).isoformat()
        _seed_goal(
            "g1", "Emergency Fund", 6500.0,
            linked_account_id="save1",
            target_date=future,
            kind="emergency_fund",
        )
        # The goal's current_balance is read live from the linked account
        # (1500), so monthly_required ≈ (6500-1500)/10 = 500.

        from analytics import compute_goal_statuses
        out = compute_goal_statuses()
        g = out[0]
        # Sanity: the live balance flowed through.
        assert g["current_balance"] == 1500.0
        # Span isn't exactly 30 days, so monthly extrapolation drifts a bit;
        # the pace classification is the load-bearing assertion.
        assert g["actual_monthly_contribution"] == pytest.approx(500.0, abs=60.0)
        assert g["pace_status"] == "on_track"

    def test_stalled_when_balance_flat(self):
        _insert_account("save1", "depository")
        _insert_snapshot("save1", 1000.0, days_ago=29)
        _insert_snapshot("save1", 1000.0, days_ago=0.1)
        _set_manual_balance("save1", 1000.0)

        future = (datetime.now(timezone.utc).date() + timedelta(days=305)).isoformat()
        _seed_goal(
            "g1", "House Down Payment", 11000.0,
            linked_account_id="save1",
            target_date=future,
        )

        from analytics import compute_goal_statuses
        g = compute_goal_statuses()[0]
        assert g["actual_monthly_contribution"] == 0.0
        assert g["pace_status"] == "stalled"

    def test_behind_when_contributions_below_pace(self):
        _insert_account("save1", "depository")
        # Only $100/mo into a goal that needs ~$500/mo.
        _insert_snapshot("save1", 1000.0, days_ago=29)
        _insert_snapshot("save1", 1100.0, days_ago=0.1)
        _set_manual_balance("save1", 1100.0)

        future = (datetime.now(timezone.utc).date() + timedelta(days=305)).isoformat()
        _seed_goal(
            "g1", "Emergency Fund", 6100.0,
            linked_account_id="save1",
            target_date=future,
            kind="emergency_fund",
        )

        from analytics import compute_goal_statuses
        g = compute_goal_statuses()[0]
        assert g["actual_monthly_contribution"] == pytest.approx(100.0, abs=20.0)
        assert g["pace_status"] == "behind"

    def test_ahead_when_contributions_exceed_pace(self):
        _insert_account("save1", "depository")
        # $2000/mo into a goal that needs ~$500/mo.
        _insert_snapshot("save1", 1000.0, days_ago=29)
        _insert_snapshot("save1", 3000.0, days_ago=0.1)
        _set_manual_balance("save1", 3000.0)

        future = (datetime.now(timezone.utc).date() + timedelta(days=305)).isoformat()
        _seed_goal(
            "g1", "Vacation", 8000.0,
            linked_account_id="save1",
            target_date=future,
        )

        from analytics import compute_goal_statuses
        g = compute_goal_statuses()[0]
        assert g["pace_status"] == "ahead"

    def test_velocity_none_with_only_one_snapshot(self):
        _insert_account("save1", "depository")
        _insert_snapshot("save1", 1000.0, days_ago=2)
        _set_manual_balance("save1", 1000.0)

        future = (datetime.now(timezone.utc).date() + timedelta(days=305)).isoformat()
        _seed_goal(
            "g1", "Vacation", 6000.0,
            linked_account_id="save1",
            target_date=future,
        )

        from analytics import compute_goal_statuses
        g = compute_goal_statuses()[0]
        assert g["actual_monthly_contribution"] is None
        assert g["pace_status"] is None
