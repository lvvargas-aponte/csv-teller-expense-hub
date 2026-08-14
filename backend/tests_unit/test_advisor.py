"""Tests for the virtual advisor router: chat + conversation CRUD."""
from unittest.mock import AsyncMock, patch

import pytest

import state
from agent.schemas import AgentResult, TrajectoryEvent


def _agent_result(text="advisor reply"):
    return AgentResult(
        reply=text,
        trajectory=[TrajectoryEvent(iteration=1, kind="final", result_summary=text)],
        terminated_reason="ok",
        iterations=1,
    )


def _mock_agent(ai_available=True, text="advisor reply"):
    """Patch run_agent inside the advisor router to avoid real Ollama calls."""
    if ai_available:
        result = _agent_result(text)
    else:
        result = AgentResult(
            reply=None, trajectory=[], terminated_reason="ollama_unavailable", iterations=0,
        )
    return patch("routers.advisor.run_agent", new=AsyncMock(return_value=result))


# ---------------------------------------------------------------------------
# POST /api/advisor/chat
# ---------------------------------------------------------------------------

class TestAdvisorChat:
    _endpoint = "/api/advisor/chat"

    def test_new_conversation_created_when_id_omitted(self, client):
        with _mock_agent():
            r = client.post(self._endpoint, json={"message": "hello"})
        assert r.status_code == 200
        body = r.json()
        assert body["conversation_id"].startswith("conv_")
        assert body["reply"] == "advisor reply"
        assert body["ai_available"] is True
        assert body["conversation_id"] in state.conversations

    def test_empty_message_rejected(self, client):
        r = client.post(self._endpoint, json={"message": "   "})
        assert r.status_code == 400

    def test_follow_up_appends_to_existing_conversation(self, client):
        with _mock_agent(text="first"):
            r1 = client.post(self._endpoint, json={"message": "q1"})
        conv_id = r1.json()["conversation_id"]

        with _mock_agent(text="second"):
            r2 = client.post(self._endpoint, json={"conversation_id": conv_id, "message": "q2"})

        assert r2.json()["conversation_id"] == conv_id
        conv = state.conversations[conv_id]
        roles = [m["role"] for m in conv["messages"]]
        assert roles == ["user", "assistant", "user", "assistant"]
        assert conv["messages"][0]["content"] == "q1"
        assert conv["messages"][3]["content"] == "second"

    def test_unknown_conversation_id_starts_new(self, client):
        with _mock_agent():
            r = client.post(self._endpoint, json={
                "conversation_id": "conv_does_not_exist",
                "message": "hello",
            })
        assert r.status_code == 200
        # A fresh conversation is created (unknown id is ignored)
        new_id = r.json()["conversation_id"]
        assert new_id != "conv_does_not_exist"
        assert new_id in state.conversations

    def test_ai_unavailable_still_persists_user_message(self, client):
        with _mock_agent(ai_available=False):
            r = client.post(self._endpoint, json={"message": "hello"})
        assert r.status_code == 200
        body = r.json()
        assert body["ai_available"] is False
        assert body["reply"] is None

        conv = state.conversations[body["conversation_id"]]
        # User message persisted; no assistant message (no reply to store)
        roles = [m["role"] for m in conv["messages"]]
        assert roles == ["user"]

    def test_run_agent_receives_history_and_system_prompt(self, client):
        agent_mock = AsyncMock(return_value=_agent_result("agent reply"))
        with patch("routers.advisor.run_agent", new=agent_mock):
            r = client.post(self._endpoint, json={"message": "hi"})

        assert r.status_code == 200
        assert r.json()["reply"] == "agent reply"
        agent_mock.assert_awaited_once()
        kwargs = agent_mock.call_args.kwargs
        assert kwargs["messages"][-1] == {"role": "user", "content": "hi"}
        assert "FINANCIAL_FACTS" in kwargs["system"]


# ---------------------------------------------------------------------------
# POST /api/advisor/chat/stream — SSE
# ---------------------------------------------------------------------------

def _parse_sse(body: str):
    import json
    return [
        json.loads(line[len("data: "):])
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


class TestAdvisorChatStream:
    _endpoint = "/api/advisor/chat/stream"

    def test_streams_events_then_done(self, client):
        async def fake_run_agent(messages, registry, system=None, on_event=None, **_kw):
            await on_event({"type": "token", "text": "hel"})
            await on_event({"type": "tool_call", "name": "get_balance", "arguments": {}})
            await on_event({"type": "tool_result", "name": "get_balance", "summary": "{}"})
            await on_event({"type": "token", "text": "lo"})
            return _agent_result("hello")

        with patch("routers.advisor.run_agent", new=fake_run_agent):
            r = client.post(self._endpoint, json={"message": "hi"})

        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(r.text)
        types = [e["type"] for e in events]
        assert types == ["token", "tool_call", "tool_result", "token", "done"]
        done = events[-1]
        assert done["reply"] == "hello"
        assert done["ai_available"] is True
        assert done["conversation_id"].startswith("conv_")

        # The turn persisted exactly like the blocking endpoint's would.
        conv = state.conversations[done["conversation_id"]]
        assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
        assert conv["messages"][1]["content"] == "hello"

    def test_empty_message_rejected(self, client):
        r = client.post(self._endpoint, json={"message": "  "})
        assert r.status_code == 400

    def test_ollama_down_yields_done_without_reply(self, client):
        from agent.schemas import AgentResult

        async def fake_run_agent(messages, registry, system=None, on_event=None, **_kw):
            return AgentResult(
                reply=None, trajectory=[], terminated_reason="ollama_unavailable", iterations=0,
            )

        with patch("routers.advisor.run_agent", new=fake_run_agent):
            r = client.post(self._endpoint, json={"message": "hi"})

        events = _parse_sse(r.text)
        assert [e["type"] for e in events] == ["done"]
        assert events[0]["ai_available"] is False
        assert events[0]["reply"] is None


# ---------------------------------------------------------------------------
# GET /api/advisor/conversations
# ---------------------------------------------------------------------------

class TestListConversations:
    def test_empty_list(self, client):
        r = client.get("/api/advisor/conversations")
        assert r.status_code == 200
        assert r.json() == []

    def test_lists_with_preview_and_sorted_by_updated(self, client):
        with _mock_agent(text="a"):
            first = client.post("/api/advisor/chat", json={"message": "groceries budget?"}).json()
        with _mock_agent(text="b"):
            second = client.post("/api/advisor/chat", json={"message": "debt plan?"}).json()

        r = client.get("/api/advisor/conversations")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        # Most recently updated first
        assert data[0]["conversation_id"] == second["conversation_id"]
        assert data[1]["conversation_id"] == first["conversation_id"]
        assert data[0]["preview"] == "debt plan?"
        assert data[1]["message_count"] == 2


# ---------------------------------------------------------------------------
# GET /api/advisor/conversations/{id}
# ---------------------------------------------------------------------------

class TestGetConversation:
    def test_returns_full_history(self, client):
        with _mock_agent(text="reply1"):
            body = client.post("/api/advisor/chat", json={"message": "hello"}).json()

        r = client.get(f"/api/advisor/conversations/{body['conversation_id']}")
        assert r.status_code == 200
        data = r.json()
        assert data["conversation_id"] == body["conversation_id"]
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][1]["role"] == "assistant"

    def test_404_for_unknown_id(self, client):
        r = client.get("/api/advisor/conversations/conv_nope")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/advisor/conversations/{id}
# ---------------------------------------------------------------------------

class TestDeleteConversation:
    def test_deletes_existing(self, client):
        with _mock_agent():
            body = client.post("/api/advisor/chat", json={"message": "hi"}).json()
        conv_id = body["conversation_id"]

        r = client.delete(f"/api/advisor/conversations/{conv_id}")
        assert r.status_code == 204
        assert conv_id not in state.conversations

    def test_404_for_unknown_id(self, client):
        r = client.delete("/api/advisor/conversations/conv_nope")
        assert r.status_code == 404
