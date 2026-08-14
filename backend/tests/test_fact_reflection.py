"""Proactive fact extraction — real test DB, mocked Ollama.

Covers: proposed rows created with source_turn_id, watermark advance,
near-duplicate skip (including rejected facts), and malformed-JSON
resilience.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

import fact_reflection
from db import fact_reflection_repo, user_facts_repo
from db.base import sync_engine
from sqlalchemy import text


_FAKE_VEC = [0.1] * 768


def _mock_embed(available=True):
    return patch(
        "embeddings.embed_ollama",
        new=AsyncMock(return_value={
            "ai_available": available,
            "embedding": _FAKE_VEC if available else None,
            "raw": None,
        }),
    )


def _mock_ask(payload):
    text_out = payload if isinstance(payload, str) else json.dumps(payload)
    return patch(
        "fact_reflection.ask_ollama",
        new=AsyncMock(return_value={
            "ai_available": True, "text": text_out, "raw": None,
        }),
    )


def _seed_user_turns(*contents: str) -> list[int]:
    ids = []
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO conversations (conversation_id, created, updated) "
                "VALUES ('conv_fact_test', NOW(), NOW()) ON CONFLICT DO NOTHING"
            )
        )
        for i, content in enumerate(contents):
            row = conn.execute(
                text(
                    "INSERT INTO conversation_turns "
                    "  (conversation_id, turn_index, role, content, ts) "
                    "VALUES ('conv_fact_test', :idx, 'user', :content, NOW()) "
                    "RETURNING id"
                ),
                {"idx": i, "content": content},
            ).fetchone()
            ids.append(int(row[0]))
    return ids


@pytest.mark.asyncio
class TestExtractUserFacts:
    async def test_proposes_facts_with_source_turn_id(self):
        turn_ids = _seed_user_turns("we're expecting a baby in March!")
        payload = {"facts": [{
            "fact": "Expecting a baby in March 2027.",
            "category": "life_event",
            "tags": ["family"],
            "sensitive": False,
            "source_index": 1,
        }]}
        with _mock_ask(payload), _mock_embed():
            created = await fact_reflection.extract_user_facts()

        assert created == 1
        facts = user_facts_repo.list_facts(status="proposed")
        assert len(facts) == 1
        assert facts[0]["fact"] == "Expecting a baby in March 2027."
        assert facts[0]["category"] == "life_event"
        assert facts[0]["source_turn_id"] == turn_ids[0]

    async def test_watermark_advances_even_when_nothing_found(self):
        _seed_user_turns("what's my balance?")
        assert fact_reflection_repo.get_turn_count_at_last_scan() == 0
        with _mock_ask({"facts": []}), _mock_embed():
            created = await fact_reflection.extract_user_facts()
        assert created == 0
        assert fact_reflection_repo.get_turn_count_at_last_scan() == 1

    async def test_near_duplicate_of_rejected_fact_skipped(self):
        _seed_user_turns("I really won't touch my 401k, stop asking")
        # Seed an existing REJECTED fact and embed it — with the constant
        # fake vector, any new candidate is distance 0 (an exact dupe).
        row = user_facts_repo.create_fact(
            fact="Will not touch the 401k.",
            category="constraint",
            status="rejected",
        )
        with _mock_embed():
            from embeddings import embed_pending_user_facts
            await embed_pending_user_facts()

        payload = {"facts": [{
            "fact": "Refuses to tap the 401k.",
            "category": "constraint",
            "tags": [],
            "sensitive": False,
            "source_index": 1,
        }]}
        with _mock_ask(payload), _mock_embed():
            created = await fact_reflection.extract_user_facts()

        assert created == 0
        assert user_facts_repo.list_facts(status="proposed") == []

    async def test_malformed_json_creates_nothing_and_does_not_raise(self):
        _seed_user_turns("hello")
        with _mock_ask("this is not json {"), _mock_embed():
            created = await fact_reflection.extract_user_facts()
        assert created == 0
        assert user_facts_repo.list_facts() == []

    async def test_invalid_category_skipped(self):
        _seed_user_turns("I like trains")
        payload = {"facts": [{
            "fact": "Likes trains.",
            "category": "hobby",  # not a valid category
            "source_index": 1,
        }]}
        with _mock_ask(payload), _mock_embed():
            created = await fact_reflection.extract_user_facts()
        assert created == 0

    async def test_no_turns_short_circuits(self):
        ask = AsyncMock()
        with patch("fact_reflection.ask_ollama", new=ask):
            created = await fact_reflection.extract_user_facts()
        assert created == 0
        ask.assert_not_awaited()


class TestShouldExtractFacts:
    def test_false_with_no_turns(self):
        assert fact_reflection.should_extract_facts() is False

    def test_true_after_interval_crossed(self):
        _seed_user_turns(*[f"message {i}" for i in range(
            fact_reflection.FACT_REFLECTION_TURN_INTERVAL
        )])
        assert fact_reflection.should_extract_facts() is True

    def test_false_right_after_scan(self):
        _seed_user_turns(*[f"message {i}" for i in range(
            fact_reflection.FACT_REFLECTION_TURN_INTERVAL
        )])
        fact_reflection_repo.set_turn_count_at_last_scan(
            fact_reflection.FACT_REFLECTION_TURN_INTERVAL
        )
        assert fact_reflection.should_extract_facts() is False
