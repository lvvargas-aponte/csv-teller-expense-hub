"""Trajectory integration tests for the Fin agent harness.

Scripts ``chat_ollama`` to emit specific tool-call sequences against a
seeded ``expense_hub_test`` DB and asserts on the trajectory shape — which
tools were called, with what arguments, in what order — not just the final
string. Real DB, real tool handlers; only the LLM is mocked.
"""
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

import state
from db.base import sync_engine


def _resp(text: str = "", tool_calls=None) -> Dict[str, Any]:
    return {
        "ai_available": True,
        "text": text,
        "tool_calls": tool_calls or [],
        "raw": None,
    }


def _tc(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    return {"function": {"name": name, "arguments": args}}


def _read_trajectory(turn_id: int) -> List[Dict[str, Any]]:
    with sync_engine.connect() as conn:
        row = conn.execute(
            text("SELECT trajectory FROM conversation_turns WHERE id = :id"),
            {"id": turn_id},
        ).fetchone()
    if not row or row[0] is None:
        return []
    return list(row[0])


@pytest.fixture
def agent_mode_on():
    # Agent mode is always on now; fixture kept so tests keep their signature.
    yield


def _seed_credit_account(account_id: str, name: str, balance: float, apr: float) -> None:
    """Drop a credit account into the balances cache + account_details side-car."""
    state._balances_cache["teller_accounts"] = [
        {
            "id": account_id,
            "institution": "Chase",
            "name": name,
            "type": "credit",
            "subtype": "credit_card",
            "available": 0.0,
            "ledger": balance,
        }
    ]
    state._balances_cache["fetched_at"] = "2026-05-01T00:00:00"
    state.account_details[account_id] = {
        "apr": apr,
        "minimum_payment": 35.0,
        "credit_limit": 5000.0,
        "due_day": 15,
    }


def _seed_budget(category: str, limit: float, spent: float) -> None:
    state.budgets[category] = {
        "category": category,
        "monthly_limit": limit,
        "rollover": False,
    }
    # Drop a transaction in the current month so compute_budget_statuses sees spend.
    from datetime import date
    today = date.today().isoformat()
    txn_id = f"seed_{category}"
    state.stored_transactions[txn_id] = {
        "id": txn_id,
        "date": today,
        "description": f"{category} test charge",
        "amount": spent,
        "category": category,
        "type": "debit",
        "is_shared": False,
    }


class TestAgentTrajectories:
    _endpoint = "/api/advisor/chat"

    def test_debt_question_invokes_get_debt(self, client, agent_mode_on):
        _seed_credit_account("acc_chase", "Chase Sapphire", 1234.56, apr=24.99)

        llm = AsyncMock(side_effect=[
            _resp(tool_calls=[_tc("get_debt", {"account_name": "chase"})]),
            _resp(text="You owe $1,234.56 on Chase Sapphire at 24.99% APR."),
        ])
        with patch("agent.harness.chat_ollama", new=llm):
            r = client.post(
                self._endpoint,
                json={"message": "how much do I owe on Chase?"},
            )

        assert r.status_code == 200
        body = r.json()
        assert body["reply"] is not None
        assert body["turn_id"] is not None

        trajectory = _read_trajectory(body["turn_id"])
        assert trajectory, "trajectory must be persisted to conversation_turns"
        tool_calls = [e for e in trajectory if e.get("kind") == "tool_call"]
        assert len(tool_calls) == 1
        assert tool_calls[0]["tool_name"] == "get_debt"
        assert tool_calls[0]["arguments"]["account_name"] == "chase"
        # The handler actually ran against the seeded data.
        assert any(e.get("kind") == "tool_result" for e in trajectory)

    def test_budget_question_invokes_get_budget_status(self, client, agent_mode_on):
        _seed_budget("Dining", limit=300.0, spent=420.0)

        llm = AsyncMock(side_effect=[
            _resp(tool_calls=[_tc("get_budget_status", {"category": "Dining"})]),
            _resp(text="Yep — you're $120 over on dining this month."),
        ])
        with patch("agent.harness.chat_ollama", new=llm):
            r = client.post(
                self._endpoint,
                json={"message": "am I over on dining?"},
            )

        body = r.json()
        trajectory = _read_trajectory(body["turn_id"])
        tools_called = [e["tool_name"] for e in trajectory if e.get("kind") == "tool_call"]
        assert tools_called == ["get_budget_status"]

    def test_cashflow_question_invokes_project_cashflow(self, client, agent_mode_on):
        llm = AsyncMock(side_effect=[
            _resp(tool_calls=[_tc("project_cashflow", {"horizon_days": 30})]),
            _resp(text="Looking at the next 30 days, you're net positive."),
        ])
        with patch("agent.harness.chat_ollama", new=llm):
            r = client.post(
                self._endpoint,
                json={"message": "what's my cashflow look like in 30 days?"},
            )

        body = r.json()
        trajectory = _read_trajectory(body["turn_id"])
        tools_called = [e["tool_name"] for e in trajectory if e.get("kind") == "tool_call"]
        assert tools_called == ["project_cashflow"]
        # Tool result was fed back; final reply terminated the loop.
        kinds = [e.get("kind") for e in trajectory]
        assert "tool_result" in kinds and "final" in kinds
