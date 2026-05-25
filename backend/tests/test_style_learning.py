"""Tests for the advisor style-learning feature.

Covers:
- ChatResponse returns a turn_id when ai_available
- POST /advisor/turns/{id}/feedback persists ratings
- GET /advisor/style-profile returns a sensible empty default
- POST /advisor/style-profile/refresh regenerates via mocked Ollama
- The style block is injected into the system prompt on the next turn
"""
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _block_auto_refresh():
    """Stop the background reflection task from hitting real Ollama between
    tests. Tests that exercise the refresh path mock it explicitly."""
    with patch(
        "routers.advisor._maybe_refresh_style_profile",
        new=AsyncMock(return_value=None),
    ):
        yield


def _mock_chat(ai_available=True, text="advisor reply"):
    return patch(
        "routers.advisor.chat_ollama",
        new=AsyncMock(return_value={
            "ai_available": ai_available,
            "text": text,
            "raw": None,
        }),
    )


def _mock_ask(text="- bullet 1\n- bullet 2\n- bullet 3"):
    return patch(
        "style_reflection.ask_ollama",
        new=AsyncMock(return_value={
            "ai_available": True,
            "text": text,
            "raw": None,
        }),
    )


class TestChatReturnsTurnId:
    def test_assistant_turn_id_returned(self, client):
        with _mock_chat(text="hi"):
            r = client.post("/api/advisor/chat", json={"message": "hello"})
        assert r.status_code == 200
        body = r.json()
        assert body["ai_available"] is True
        # Assistant turn = index 1 in a fresh conversation. The id is the
        # autoincrement PK assigned by sync_conversation_turns.
        assert isinstance(body["turn_id"], int)
        assert body["turn_id"] >= 1

    def test_turn_id_none_when_ai_unavailable(self, client):
        with _mock_chat(ai_available=False, text=None):
            r = client.post("/api/advisor/chat", json={"message": "hi"})
        assert r.status_code == 200
        assert r.json()["turn_id"] is None


class TestFeedbackEndpoint:
    def test_thumbs_up_recorded(self, client):
        with _mock_chat(text="reply"):
            r = client.post("/api/advisor/chat", json={"message": "hi"})
        turn_id = r.json()["turn_id"]

        fb = client.post(
            f"/api/advisor/turns/{turn_id}/feedback",
            json={"rating": 1},
        )
        assert fb.status_code == 204

        # Verify the row is reachable by the reflection corpus.
        from db import feedback_repo
        assert feedback_repo.get_feedback_for_turn(turn_id) == 1
        liked = feedback_repo.get_positive_turn_contents(limit=5)
        assert "reply" in liked

    def test_unknown_turn_returns_404(self, client):
        r = client.post(
            "/api/advisor/turns/999999/feedback",
            json={"rating": 1},
        )
        assert r.status_code == 404

    def test_rating_overwrites_previous(self, client):
        with _mock_chat(text="reply"):
            r = client.post("/api/advisor/chat", json={"message": "hi"})
        turn_id = r.json()["turn_id"]

        client.post(f"/api/advisor/turns/{turn_id}/feedback", json={"rating": 1})
        client.post(f"/api/advisor/turns/{turn_id}/feedback", json={"rating": -1})

        from db import feedback_repo
        assert feedback_repo.get_feedback_for_turn(turn_id) == -1

    def test_invalid_rating_rejected(self, client):
        r = client.post(
            "/api/advisor/turns/1/feedback",
            json={"rating": 5},
        )
        assert r.status_code == 422


class TestStyleProfileEndpoints:
    def test_get_returns_empty_default(self, client):
        r = client.get("/api/advisor/style-profile")
        assert r.status_code == 200
        body = r.json()
        assert body["style_notes"] == ""
        assert body["turn_count_at_last_update"] == 0
        assert body["updated_at"] is None

    def test_refresh_populates_profile(self, client):
        # Need at least one user message in the corpus.
        with _mock_chat(text="reply"):
            client.post("/api/advisor/chat", json={"message": "what's my cash?"})

        with _mock_ask(text="- bullet a\n- bullet b\n- bullet c"):
            r = client.post("/api/advisor/style-profile/refresh")
        assert r.status_code == 200
        body = r.json()
        assert "bullet a" in body["style_notes"]
        assert body["turn_count_at_last_update"] >= 1
        assert body["updated_at"] is not None

    def test_refresh_no_op_when_no_user_messages(self, client):
        with _mock_ask():
            r = client.post("/api/advisor/style-profile/refresh")
        assert r.status_code == 200
        assert r.json()["style_notes"] == ""


class TestStyleProfileInjection:
    def test_profile_appears_in_system_prompt(self, client):
        # Seed a user message + a profile.
        with _mock_chat(text="reply"):
            client.post("/api/advisor/chat", json={"message": "hi"})
        with _mock_ask(text="- be warm\n- lead with the number"):
            client.post("/api/advisor/style-profile/refresh")

        # Now send another message and capture the system prompt passed to Ollama.
        captured = {}

        async def _capture(messages, system=None, **_kw):
            captured["system"] = system
            return {"ai_available": True, "text": "ok", "raw": None}

        with patch("routers.advisor.chat_ollama", new=_capture):
            client.post("/api/advisor/chat", json={"message": "again"})

        assert "USER_STYLE_NOTES" in captured["system"]
        assert "lead with the number" in captured["system"]
