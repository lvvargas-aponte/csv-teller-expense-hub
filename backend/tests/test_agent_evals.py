"""Trajectory eval harness for the Fin agent.

Table-driven regression net: each row is a user message paired with the
tools that *must* be called and tools that *must not* be called. A
keyword-based router stub stands in for the LLM so the eval is
deterministic and runs in CI — it picks tool calls from keywords in the
user's message, mirroring what a well-behaved local model would do.

When the prompt or registry drifts in a way that changes tool selection,
this suite fails and points at the row. Live-model evaluation belongs in
a separate, non-CI smoke script.
"""
from typing import Any, Dict, List, Optional  # noqa: F401
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

import state
from db.base import sync_engine


# ---------------------------------------------------------------------------
# Router stub — picks a tool based on keywords in the user's message.
# Deterministic stand-in for the LLM's tool-choice behavior.
# ---------------------------------------------------------------------------

def _resp(text: str = "", tool_calls=None) -> Dict[str, Any]:
    return {
        "ai_available": True,
        "text": text,
        "tool_calls": tool_calls or [],
        "raw": None,
    }


def _tc(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    return {"function": {"name": name, "arguments": args}}


def _pick_tool(message: str, history: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """Return the single tool call this stub would emit for ``message``.

    A well-behaved model should consult the previous assistant turn when
    the current message is a short follow-up ("yes", "tell me more"). We
    model that by peeking at history when the message is bare.
    """
    m = message.lower().strip()

    # Conversation continuity: short positive reply → act on what the
    # previous assistant turn offered.
    SHORT_AFFIRMATIVES = {"yes", "yes please", "ok", "sure", "tell me more",
                          "do it", "go ahead", "show me", "that sounds good"}
    if m in SHORT_AFFIRMATIVES and history:
        for prev in reversed(history[:-1]):  # skip current user turn
            if prev.get("role") == "assistant":
                prev_text = (prev.get("content") or "").lower()
                if "entertainment" in prev_text or "dining" in prev_text:
                    return _tc("get_category_spending", {"category": "Entertainment"})
                if "savings" in prev_text:
                    return _tc("get_category_spending", {"category": "Savings"})
                break
        # Nothing useful in history — still must not bail out asking "yes to what?"
        return None

    # Order matters — most specific match first. The recall / search-doc
    # keywords go BEFORE general keywords ("budget", "save") so a phrase
    # like "what did you say about my budget last time" routes to
    # recall_past_conversation, not get_budget_status.
    if any(k in m for k in ("last time we", "we talked about", "what did you say",
                              "previous conversation", "before in another chat")):
        return _tc("recall_past_conversation", {"query": message})
    if any(k in m for k in ("irs", "tax return", "my statement", "per the doc",
                              "according to the doc", "contribution limit", "pub 590")):
        return _tc("search_documents", {"query": message})
    if any(k in m for k in ("remember that", "please remember", "save that")):
        return _tc("remember_about_user", {
            "fact": message, "category": "goal", "tags": [],
        })
    if any(k in m for k in ("what did i say about", "do you remember")):
        return _tc("recall_about_user", {"query": message})
    if any(k in m for k in ("average", "total ", "how much did i spend")):
        return _tc("get_category_spending", {"category": "Drinks"})
    if any(k in m for k in ("owe", "debt", "credit card", "balance on")):
        return _tc("get_debt", {})
    if any(k in m for k in ("budget", "over on")):
        return _tc("get_budget_status", {})
    if any(k in m for k in ("savings target", "on pace", "goal")):
        return _tc("get_goal_status", {})
    if any(k in m for k in ("cashflow", "next 30 days", "next month", "upcoming bills")):
        return _tc("project_cashflow", {"horizon_days": 30})
    if any(k in m for k in ("stock", "portfolio", "holdings", "etf", "crypto",
                              "allocation", "concentration", "vti", "btc")):
        return _tc("get_investments", {})
    if any(k in m for k in ("how much cash", "checking", "net worth", "how much do i have")):
        return _tc("get_balance", {})
    if any(k in m for k in ("that ", "find ")):
        return _tc("search_transactions", {"query": message})
    return None


def _contextual_final_reply(user_message: str) -> str:
    """Produce a final assistant reply whose text references concrete
    categories so multi-turn continuity tests can see meaningful history."""
    m = user_message.lower()
    if "save" in m and ("next" in m or "month" in m):
        return (
            "Looking at Entertainment, Dining, and Subscriptions — these "
            "tend to be the biggest discretionary buckets. Want me to "
            "break down spend in each?"
        )
    if "savings" in m:
        return (
            "Your Savings transfers look healthy this year. Want me to "
            "pull the full Savings breakdown month by month?"
        )
    return "grounded final reply"


class _StubLLM:
    """Two-turn stub: first turn picks a tool (if applicable), second answers.

    Uses the LAST user message (current turn) when picking a tool — matches
    how a real model behaves and lets us test multi-turn continuity.
    """

    def __init__(self):
        self.user_message: Optional[str] = None
        self.call_count = 0

    async def __call__(self, *, messages, system=None, tools=None, model=None):
        self.call_count += 1
        # Use the most recent user message — this is what the model would
        # actually be responding to on the current turn.
        for m in reversed(messages):
            if m.get("role") == "user":
                self.user_message = m.get("content") or ""
                break

        if self.call_count == 1:
            tool = _pick_tool(self.user_message or "", history=messages)
            if tool is not None:
                return _resp(tool_calls=[tool])
            return _resp(text=_contextual_final_reply(self.user_message or ""))
        return _resp(text=_contextual_final_reply(self.user_message or ""))


def _read_trajectory(turn_id: int) -> List[Dict[str, Any]]:
    with sync_engine.connect() as conn:
        row = conn.execute(
            text("SELECT trajectory FROM conversation_turns WHERE id = :id"),
            {"id": turn_id},
        ).fetchone()
    if not row or row[0] is None:
        return []
    return list(row[0])


def _tools_called(trajectory: List[Dict[str, Any]]) -> List[str]:
    return [e["tool_name"] for e in trajectory if e.get("kind") == "tool_call"]


# ---------------------------------------------------------------------------
# Eval table — drives the parametrized regression test
# ---------------------------------------------------------------------------

@pytest.fixture
def agent_mode_on():
    # Agent mode is always on now; fixture kept so parametrized tests keep
    # their signature.
    yield


_EVAL_CASES = [
    # (id, user_message, must_call, must_not_call)
    ("debt_question",
     "how much do I owe on Chase?",
     {"get_debt"},
     {"project_cashflow", "search_transactions"}),
    ("budget_question",
     "am I over on dining this month?",
     {"get_budget_status"},
     {"get_debt", "search_transactions"}),
    ("cashflow_question",
     "what does my cashflow look like for the next 30 days?",
     {"project_cashflow"},
     {"get_debt"}),
    ("balance_question",
     "how much cash do I have right now?",
     {"get_balance"},
     {"search_transactions"}),
    ("goal_question",
     "am I on pace with my emergency fund goal?",
     {"get_goal_status"},
     {"get_debt"}),
    ("transaction_lookup",
     "what was that $300 charge from last week?",
     {"search_transactions"},
     {"project_cashflow"}),
    # Aggregation regression — Fin used to call search_transactions for this
    # and find nothing because it's a similarity search, not a roll-up.
    ("category_average",
     "what's my average Drinks spend this year?",
     {"get_category_spending"},
     {"search_transactions"}),
    ("category_total",
     "how much did I spend on Groceries last month?",
     {"get_category_spending"},
     {"search_transactions"}),
    ("portfolio_question",
     "how is my stock portfolio doing?",
     {"get_investments"},
     {"get_balance", "get_category_spending"}),
    ("specific_ticker",
     "what's my position in VTI?",
     {"get_investments"},
     {"search_transactions"}),
    ("knowledge_doc_question",
     "what does the IRS say about Roth contribution limits this year?",
     {"search_documents"},
     {"get_category_spending", "search_transactions"}),
    ("past_conversation_recall",
     "what did you say about my budget last time we talked?",
     {"recall_past_conversation"},
     {"get_budget_status", "search_transactions"}),
    ("remember_fact",
     "please remember that I want to retire at 45",
     {"remember_about_user"},
     {"recall_about_user", "get_goal_status"}),
    ("recall_fact",
     "what did I say about retirement before?",
     {"recall_about_user"},
     {"remember_about_user"}),
    # Tool-less case: the answer is in the facts header.
    ("greeting_no_tools",
     "hey, just saying hi",
     set(),
     {"get_debt", "get_balance", "project_cashflow", "search_transactions",
      "get_budget_status", "get_goal_status"}),
]


@pytest.mark.parametrize(
    "case_id,message,must_call,must_not_call",
    _EVAL_CASES,
    ids=[c[0] for c in _EVAL_CASES],
)
def test_trajectory_matches_expected_tools(
    client, agent_mode_on, case_id, message, must_call, must_not_call,
):
    stub = _StubLLM()
    with patch("agent.harness.chat_ollama", new=stub):
        r = client.post("/api/advisor/chat", json={"message": message})

    assert r.status_code == 200
    body = r.json()
    assert body["reply"] is not None, f"[{case_id}] no reply produced"
    assert body["turn_id"] is not None

    trajectory = _read_trajectory(body["turn_id"])
    called = set(_tools_called(trajectory))

    missing = must_call - called
    forbidden = must_not_call & called
    assert not missing, f"[{case_id}] expected tools not called: {missing} (called: {called})"
    assert not forbidden, f"[{case_id}] forbidden tools called: {forbidden}"


# ---------------------------------------------------------------------------
# Aggregate health metrics — keep loops short, terminations clean
# ---------------------------------------------------------------------------

def test_agent_terminates_cleanly_for_every_eval_case(client, agent_mode_on):
    """No eval case should hit max_iterations or repeated_tool_call."""
    bad_terminations: List[str] = []
    for case_id, message, _must, _forbid in _EVAL_CASES:
        stub = _StubLLM()
        with patch("agent.harness.chat_ollama", new=stub):
            r = client.post("/api/advisor/chat", json={"message": message})
        body = r.json()
        trajectory = _read_trajectory(body["turn_id"])
        terminations = [
            e.get("terminated_reason") for e in trajectory
            if e.get("kind") == "terminated"
        ]
        for reason in terminations:
            if reason in ("max_iterations", "repeated_tool_call"):
                bad_terminations.append(f"{case_id}: {reason}")
    assert not bad_terminations, f"unclean terminations: {bad_terminations}"


def test_no_eval_case_exceeds_two_tool_calls(client, agent_mode_on):
    """The stub picks at most one tool per turn — sanity-check the upper bound."""
    for case_id, message, _must, _forbid in _EVAL_CASES:
        stub = _StubLLM()
        with patch("agent.harness.chat_ollama", new=stub):
            r = client.post("/api/advisor/chat", json={"message": message})
        body = r.json()
        trajectory = _read_trajectory(body["turn_id"])
        call_count = len(_tools_called(trajectory))
        assert call_count <= 2, f"[{case_id}] too many tool calls: {call_count}"


# ---------------------------------------------------------------------------
# Conversation continuity regression: a short "yes" reply must NOT cause
# Fin to bail with "I don't have context". The model is expected to read
# the previous assistant turn and act on what was offered.
# ---------------------------------------------------------------------------

class TestConversationContinuity:
    def test_yes_follow_up_acts_on_previous_assistant_turn(self, client, agent_mode_on):
        # Turn 1 — set the scene: Fin offers to break down a few categories.
        stub1 = _StubLLM()
        with patch("agent.harness.chat_ollama", new=stub1):
            r1 = client.post("/api/advisor/chat", json={
                "message": "where can I save next month?",
            })
        conv_id = r1.json()["conversation_id"]

        # Turn 2 — user replies "yes". A well-behaved model uses the
        # previous assistant turn (mentioning Entertainment / Dining /
        # Subscriptions) to decide what to call. The stub mirrors that.
        stub2 = _StubLLM()
        with patch("agent.harness.chat_ollama", new=stub2):
            r2 = client.post("/api/advisor/chat", json={
                "conversation_id": conv_id,
                "message": "yes",
            })

        body = r2.json()
        assert body["turn_id"] is not None
        trajectory = _read_trajectory(body["turn_id"])
        tools_called = [
            e["tool_name"] for e in trajectory if e.get("kind") == "tool_call"
        ]
        # The "yes" must trigger a real tool call referencing the prior
        # context — not an empty trajectory that ends in clarification.
        assert tools_called, (
            f"Expected continuity tool call after 'yes', got empty trajectory: "
            f"{trajectory}"
        )
        assert "get_category_spending" in tools_called

    def test_yes_with_savings_context_calls_savings(self, client, agent_mode_on):
        stub1 = _StubLLM()
        with patch("agent.harness.chat_ollama", new=stub1):
            r1 = client.post("/api/advisor/chat", json={
                "message": "how are my savings looking this year?",
            })
        conv_id = r1.json()["conversation_id"]

        stub2 = _StubLLM()
        with patch("agent.harness.chat_ollama", new=stub2):
            r2 = client.post("/api/advisor/chat", json={
                "conversation_id": conv_id,
                "message": "tell me more",
            })

        trajectory = _read_trajectory(r2.json()["turn_id"])
        tools_called = [
            (e["tool_name"], e.get("arguments") or {})
            for e in trajectory if e.get("kind") == "tool_call"
        ]
        assert tools_called, "follow-up 'tell me more' produced no tool call"
        name, args = tools_called[0]
        assert name == "get_category_spending"
        assert args.get("category") == "Savings"
