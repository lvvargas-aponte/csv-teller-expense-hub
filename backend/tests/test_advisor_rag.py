"""Phase 6 — RAG slice for the advisor.

Exercises the three new surfaces introduced by ``backend/embeddings.py``:

* Every ``/advisor/chat`` call dual-writes turns into the structured
  ``conversation_turns`` table.
* When Ollama embeddings are available, the BackgroundTasks hook fills
  ``conversation_turn_embeddings`` for new turns.
* ``retrieve_similar`` returns past turns from *other* conversations,
  excluded from the current one to prevent trivial self-hits.

All Ollama calls are mocked so the tests run without a live LLM server.
"""
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

import state
from db.base import sync_engine


# A constant 768-dim vector so mocked ``embed_ollama`` returns something
# pgvector can store. Tests don't care about semantic similarity — only
# that the vector is the right dimension and round-trips cleanly.
_FAKE_VEC = [0.1] * 768


def _mock_chat(text_reply="ok"):
    return patch(
        "routers.advisor.chat_ollama",
        new=AsyncMock(return_value={
            "ai_available": True,
            "text": text_reply,
            "raw": None,
        }),
    )


def _mock_embed(available=True, vec=None):
    """Patch the embedding call at its use site in ``embeddings.py``."""
    if vec is None:
        vec = _FAKE_VEC
    return patch(
        "embeddings.embed_ollama",
        new=AsyncMock(return_value={
            "ai_available": available,
            "embedding": vec if available else None,
            "raw": None,
        }),
    )


def _count(sql: str, params: dict | None = None) -> int:
    with sync_engine.connect() as conn:
        return int(conn.execute(text(sql), params or {}).scalar() or 0)


class TestDualWritePersistsTurns:
    def test_chat_inserts_conversation_and_turns(self, client):
        with _mock_chat("hi"), _mock_embed():
            r = client.post("/api/advisor/chat", json={"message": "what's my spend?"})
        assert r.status_code == 200
        conv_id = r.json()["conversation_id"]

        assert _count(
            "SELECT COUNT(*) FROM conversations WHERE conversation_id = :id",
            {"id": conv_id},
        ) == 1
        # Two turns: one user, one assistant
        assert _count(
            "SELECT COUNT(*) FROM conversation_turns WHERE conversation_id = :id",
            {"id": conv_id},
        ) == 2

    def test_follow_up_appends_turns_without_duplicates(self, client):
        with _mock_chat("first"), _mock_embed():
            r1 = client.post("/api/advisor/chat", json={"message": "q1"})
        conv_id = r1.json()["conversation_id"]
        with _mock_chat("second"), _mock_embed():
            client.post("/api/advisor/chat", json={"conversation_id": conv_id, "message": "q2"})

        # 4 turns: q1, first, q2, second
        assert _count(
            "SELECT COUNT(*) FROM conversation_turns WHERE conversation_id = :id",
            {"id": conv_id},
        ) == 4


class TestBackgroundEmbedding:
    def test_embeddings_row_written_per_turn(self, client):
        with _mock_chat("hi"), _mock_embed():
            r = client.post("/api/advisor/chat", json={"message": "a new thought"})
        conv_id = r.json()["conversation_id"]

        embedded_count = _count(
            "SELECT COUNT(*) FROM conversation_turn_embeddings e "
            "JOIN conversation_turns t ON t.id = e.turn_id "
            "WHERE t.conversation_id = :id",
            {"id": conv_id},
        )
        # The BackgroundTasks + the RAG retrieval call both embed; either
        # way, by the time the TestClient returns, at least the two turns
        # created this request should have embeddings.
        assert embedded_count >= 2

    def test_embeddings_skipped_when_ollama_unavailable(self, client):
        with _mock_chat("hi"), _mock_embed(available=False):
            r = client.post("/api/advisor/chat", json={"message": "still saved?"})
        conv_id = r.json()["conversation_id"]

        # Turns still persist; embeddings are just empty.
        assert _count(
            "SELECT COUNT(*) FROM conversation_turns WHERE conversation_id = :id",
            {"id": conv_id},
        ) == 2
        assert _count(
            "SELECT COUNT(*) FROM conversation_turn_embeddings e "
            "JOIN conversation_turns t ON t.id = e.turn_id "
            "WHERE t.conversation_id = :id",
            {"id": conv_id},
        ) == 0


class TestRetrieveSimilar:
    @pytest.mark.asyncio
    async def test_retrieve_finds_past_turn_in_other_conversation(self, client):
        """Seed one conversation, then query from a different one."""
        # Conversation A — seed
        with _mock_chat("first reply"), _mock_embed():
            ra = client.post("/api/advisor/chat", json={"message": "how do I pay off debt?"})
        conv_a = ra.json()["conversation_id"]

        # Retrieve similar from a *different* conv — should pull A's turns
        from embeddings import retrieve_similar
        with _mock_embed():
            hits = await retrieve_similar(
                "debt payoff strategy",
                exclude_conv_id="conv_different",
                k=5,
                threshold=0.5,
            )
        assert len(hits) >= 1
        assert all(h["conversation_id"] == conv_a for h in hits)

    @pytest.mark.asyncio
    async def test_retrieve_excludes_current_conversation(self, client):
        with _mock_chat("reply"), _mock_embed():
            r = client.post("/api/advisor/chat", json={"message": "question"})
        conv_id = r.json()["conversation_id"]

        from embeddings import retrieve_similar
        with _mock_embed():
            hits = await retrieve_similar(
                "question",
                exclude_conv_id=conv_id,
                k=5,
                threshold=0.5,
            )
        # All turns came from conv_id — excluding it yields nothing.
        assert hits == []

    @pytest.mark.asyncio
    async def test_retrieve_empty_when_no_embeddings(self, client):
        from embeddings import retrieve_similar
        with _mock_embed():
            hits = await retrieve_similar("anything", exclude_conv_id=None)
        assert hits == []
