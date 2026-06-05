"""Integration tests for the remember_about_user / recall_about_user agent tools.

Mocks ``embed_ollama`` so the embedding write/retrieval round-trips against
the real test DB without needing a live Ollama server.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from agent.schemas import RecallAboutUserArgs, RememberAboutUserArgs
from agent.tools import _recall_about_user, _remember_about_user
from db import user_facts_repo


_FAKE_VEC = [0.1] * 768


def _mock_embed():
    return patch(
        "embeddings.embed_ollama",
        new=AsyncMock(return_value={
            "ai_available": True, "embedding": _FAKE_VEC, "raw": None,
        }),
    )


def _run(coro):
    return asyncio.run(coro)


class TestRemember:
    def test_writes_proposed_row(self):
        with _mock_embed():
            out = _run(_remember_about_user(RememberAboutUserArgs(
                fact="User won't tap the 401k for daily expenses.",
                category="constraint",
                tags=["retirement", "401k"],
            )))
        assert out["status"] == "proposed"
        row = user_facts_repo.get_fact(out["fact_id"])
        assert row["fact"] == "User won't tap the 401k for daily expenses."
        assert row["status"] == "proposed"
        assert row["tags"] == ["retirement", "401k"]

    def test_tags_capped_at_five(self):
        with _mock_embed():
            out = _run(_remember_about_user(RememberAboutUserArgs(
                fact="x", category="pattern",
                tags=["a", "b", "c", "d", "e", "f", "g"],
            )))
        row = user_facts_repo.get_fact(out["fact_id"])
        assert len(row["tags"]) == 5


class TestRecall:
    def test_only_confirmed_facts_surface(self):
        user_facts_repo.create_fact(fact="proposed fact", category="goal", status="proposed")
        confirmed = user_facts_repo.create_fact(
            fact="confirmed fact", category="goal", status="confirmed",
        )
        # Embed both rows (mocked) so they have vectors to match against.
        with _mock_embed():
            from embeddings import embed_pending_user_facts
            _run(embed_pending_user_facts())

            out = _run(_recall_about_user(RecallAboutUserArgs(query="anything")))

        ids = [f["fact"] for f in out["facts"]]
        assert "confirmed fact" in ids
        assert "proposed fact" not in ids

    def test_rejected_facts_excluded(self):
        rejected = user_facts_repo.create_fact(
            fact="rejected fact", category="goal", status="rejected",
        )
        with _mock_embed():
            from embeddings import embed_pending_user_facts
            _run(embed_pending_user_facts())
            out = _run(_recall_about_user(RecallAboutUserArgs(query="anything")))
        assert all(f["fact"] != "rejected fact" for f in out["facts"])

    def test_no_confirmed_facts_returns_empty(self):
        with _mock_embed():
            out = _run(_recall_about_user(RecallAboutUserArgs(query="anything")))
        assert out == {"query": "anything", "count": 0, "facts": []}

    def test_category_filter(self):
        user_facts_repo.create_fact(
            fact="g", category="goal", status="confirmed",
        )
        user_facts_repo.create_fact(
            fact="p", category="preference", status="confirmed",
        )
        with _mock_embed():
            from embeddings import embed_pending_user_facts
            _run(embed_pending_user_facts())
            out = _run(_recall_about_user(RecallAboutUserArgs(
                query="anything", category="goal",
            )))
        cats = {f["category"] for f in out["facts"]}
        assert cats == {"goal"}
