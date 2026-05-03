"""Transaction embeddings — backfill, drift re-embed, and retrieval.

The transaction RAG pipeline (``embed_pending_transactions``,
``retrieve_similar_transactions``) lets the advisor surface specific
historical charges when the user asks "what was that..." style
questions. These tests pin the round-trip behavior without requiring a
live Ollama server — all embedding calls are mocked.
"""
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

import state
from db.base import sync_engine


# 768-dim constant vector — the right shape for pgvector(768) storage.
# Tests don't need real semantic similarity; they just verify that what
# we embed is what comes back.
_FAKE_VEC = [0.1] * 768


def _mock_embed(available=True, vec=None):
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


@pytest.fixture(autouse=True)
def _clear_txns_before_each_test():
    """Belt-and-suspenders: ensure stored_transactions is empty at the
    start of every test in this module.

    The repo-wide ``clear_storage`` fixture in conftest already TRUNCATEs
    ``json_stores`` between tests, but a couple of unrelated test files
    on this branch leak account/transaction state via different code
    paths, so we explicitly clear before each test.
    """
    state.stored_transactions.clear()
    yield


def _seed_txn(tid: str, description: str, amount: float, category: str = "") -> None:
    state.stored_transactions[tid] = {
        "transaction_id": tid,
        "id": tid,
        "date": "2026-02-14",
        "description": description,
        "amount": amount,
        "source": "discover",
        "is_shared": False,
        "category": category,
        "transaction_type": "debit",
        "notes": "",
    }


def _embedding_count(tid: str | None = None) -> int:
    sql = "SELECT COUNT(*) FROM transaction_embeddings"
    params: dict = {}
    if tid is not None:
        sql += " WHERE transaction_id = :tid"
        params["tid"] = tid
    with sync_engine.connect() as conn:
        return int(conn.execute(text(sql), params).scalar() or 0)


def _embedding_hash(tid: str) -> str | None:
    with sync_engine.connect() as conn:
        row = conn.execute(
            text("SELECT content_hash FROM transaction_embeddings WHERE transaction_id = :t"),
            {"t": tid},
        ).fetchone()
    return row[0] if row else None


class TestBackfill:
    @pytest.mark.asyncio
    async def test_embeds_all_pending_transactions(self):
        _seed_txn("t1", "NETFLIX", 15.99, "Entertainment")
        _seed_txn("t2", "STARBUCKS", 4.50, "Restaurants")

        from embeddings import embed_pending_transactions
        with _mock_embed():
            embedded = await embed_pending_transactions()
        assert embedded == 2
        assert _embedding_count() == 2

    @pytest.mark.asyncio
    async def test_idempotent_when_hashes_unchanged(self):
        _seed_txn("t1", "NETFLIX", 15.99, "Entertainment")

        from embeddings import embed_pending_transactions
        with _mock_embed():
            first = await embed_pending_transactions()
            second = await embed_pending_transactions()
        assert first == 1
        assert second == 0
        assert _embedding_count("t1") == 1

    @pytest.mark.asyncio
    async def test_skips_when_ollama_unavailable(self):
        _seed_txn("t1", "NETFLIX", 15.99, "Entertainment")

        from embeddings import embed_pending_transactions
        with _mock_embed(available=False):
            embedded = await embed_pending_transactions()
        assert embedded == 0
        assert _embedding_count() == 0

    @pytest.mark.asyncio
    async def test_no_op_when_no_transactions(self):
        from embeddings import embed_pending_transactions
        with _mock_embed():
            embedded = await embed_pending_transactions()
        assert embedded == 0


class TestDriftReembed:
    @pytest.mark.asyncio
    async def test_category_edit_triggers_reembed(self):
        _seed_txn("t1", "NETFLIX", 15.99, "Uncategorized")
        from embeddings import embed_pending_transactions
        with _mock_embed():
            await embed_pending_transactions()
        original_hash = _embedding_hash("t1")
        assert original_hash is not None

        # Simulate the user re-categorizing.
        txn = state.stored_transactions["t1"]
        txn["category"] = "Entertainment"
        state.stored_transactions["t1"] = txn

        with _mock_embed():
            embedded = await embed_pending_transactions()
        assert embedded == 1
        new_hash = _embedding_hash("t1")
        assert new_hash != original_hash
        # Still exactly one row — UPSERT, not INSERT.
        assert _embedding_count("t1") == 1


class TestRetrieve:
    @pytest.mark.asyncio
    async def test_retrieve_returns_embedded_transactions(self):
        _seed_txn("t1", "NETFLIX", 15.99, "Entertainment")
        _seed_txn("t2", "STARBUCKS", 4.50, "Restaurants")

        from embeddings import embed_pending_transactions, retrieve_similar_transactions
        with _mock_embed():
            await embed_pending_transactions()
            hits = await retrieve_similar_transactions(
                "streaming charge",
                k=5,
                threshold=0.5,
            )
        assert {h["transaction_id"] for h in hits} == {"t1", "t2"}
        # Each hit carries the user-facing fields needed for the system prompt.
        h_by_id = {h["transaction_id"]: h for h in hits}
        assert h_by_id["t1"]["description"] == "NETFLIX"
        assert h_by_id["t1"]["amount"] == 15.99
        assert h_by_id["t1"]["category"] == "Entertainment"

    @pytest.mark.asyncio
    async def test_retrieve_drops_orphaned_embeddings(self):
        """Embedding rows whose source txn was deleted are silently filtered."""
        _seed_txn("t1", "NETFLIX", 15.99, "Entertainment")
        from embeddings import embed_pending_transactions, retrieve_similar_transactions
        with _mock_embed():
            await embed_pending_transactions()

        # Delete the source txn but leave the embedding row in place.
        del state.stored_transactions["t1"]
        assert _embedding_count("t1") == 1

        with _mock_embed():
            hits = await retrieve_similar_transactions("anything", k=5, threshold=0.5)
        assert hits == []

    @pytest.mark.asyncio
    async def test_retrieve_empty_when_ollama_down(self):
        _seed_txn("t1", "NETFLIX", 15.99, "Entertainment")
        from embeddings import retrieve_similar_transactions
        with _mock_embed(available=False):
            hits = await retrieve_similar_transactions("anything")
        assert hits == []


class TestFormatContext:
    def test_renders_compact_bullets(self):
        from embeddings import format_txn_rag_context
        block = format_txn_rag_context([
            {
                "transaction_id": "t1",
                "date": "2026-02-14",
                "description": "NETFLIX",
                "amount": 15.99,
                "category": "Entertainment",
                "distance": 0.1,
            },
        ])
        assert "Related past transactions" in block
        assert "2026-02-14" in block
        assert "NETFLIX" in block
        assert "$15.99" in block
        assert "Entertainment" in block

    def test_empty_hits_returns_empty_string(self):
        from embeddings import format_txn_rag_context
        assert format_txn_rag_context([]) == ""
