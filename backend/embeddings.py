"""RAG primitives built on pgvector + Ollama.

Two parallel pipelines share the same machinery (``embed_text``,
``_vec_literal``, ``EMBED_DIM``):

1. **Conversation turns** — chat history is mirrored into structured
   tables (``sync_conversation_turns``), embedded asynchronously
   (``embed_pending_turns``), and recalled per-message via
   ``retrieve_similar`` so the advisor remembers prior discussions.
2. **Transactions** — every ``transactions`` row gets an embedding
   (``embed_pending_transactions``) keyed by a ``content_hash`` so edits
   trigger re-embed; ``retrieve_similar_transactions`` lets the advisor
   answer "what was that $300 charge" / "find subscription-like charges"
   by surfacing semantically-nearest historical txns.

Intentionally sync for DB ops (uses ``db.base.sync_engine``) because the
advisor router and its call-sites are a mix of sync (``PgStore``) and
async (``httpx``); async DB on top would add driver complexity without
meaningful throughput gains at single-user scale.
"""
import hashlib
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text

import state
from db.base import sync_engine
from llm_client import embed_ollama

logger = logging.getLogger(__name__)

EMBED_DIM = 768                   # Column type is `vector(768)` in 0001_initial.
DEFAULT_K = 5
DEFAULT_THRESHOLD = 0.35          # Cosine distance; lower = more similar.
DEFAULT_BACKFILL_LIMIT = 500


def _vec_literal(vec: List[float]) -> str:
    """pgvector accepts text-literal vectors: ``'[0.1,0.2,...]'::vector(N)``.

    Using a text literal keeps us driver-agnostic — no need to register
    the pgvector adapter for asyncpg/psycopg2 separately.
    """
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def sync_conversation_turns(conv: Dict[str, Any]) -> None:
    """Ensure structured rows exist for a conversation + all its turns.

    Safe to call on every chat — ON CONFLICT DO NOTHING keeps already-
    persisted turns untouched; only new trailing turns are inserted.
    """
    conv_id = conv.get("conversation_id")
    if not conv_id:
        return
    messages = conv.get("messages") or []

    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO conversations (conversation_id, created, updated) "
                "VALUES (:id, "
                "  COALESCE(CAST(:created AS TIMESTAMPTZ), NOW()), "
                "  COALESCE(CAST(:updated AS TIMESTAMPTZ), NOW())) "
                "ON CONFLICT (conversation_id) DO UPDATE SET updated = NOW()"
            ),
            {
                "id": conv_id,
                "created": conv.get("created"),
                "updated": conv.get("updated"),
            },
        )
        for i, msg in enumerate(messages):
            conn.execute(
                text(
                    "INSERT INTO conversation_turns "
                    "  (conversation_id, role, content, ts, turn_index) "
                    "VALUES "
                    "  (:conv, :role, :content, "
                    "   COALESCE(CAST(:ts AS TIMESTAMPTZ), NOW()), :idx) "
                    "ON CONFLICT (conversation_id, turn_index) DO NOTHING"
                ),
                {
                    "conv": conv_id,
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "") or "",
                    "ts": msg.get("ts"),
                    "idx": i,
                },
            )


async def embed_text(content: str) -> Optional[List[float]]:
    """Return a 768-dim embedding, or None on any failure.

    Failures include: Ollama down, model not pulled, timeout, dimension
    mismatch (wrong model loaded). All are logged but never raised — the
    caller decides how to degrade (skip write, skip retrieval, etc.).
    """
    if not content or not content.strip():
        return None
    result = await embed_ollama(content)
    if not result.get("ai_available"):
        return None
    vec = result.get("embedding")
    if not vec:
        return None
    if len(vec) != EMBED_DIM:
        logger.warning(
            f"[embeddings] dim mismatch: got {len(vec)} want {EMBED_DIM} "
            f"(model={state.OLLAMA_EMBED_MODEL}); disabling RAG for this call"
        )
        return None
    return list(vec)


async def embed_pending_turns(
    conv_id: Optional[str] = None,
    limit: int = DEFAULT_BACKFILL_LIMIT,
) -> int:
    """Embed any conversation turns without a matching embeddings row.

    If ``conv_id`` is provided, only that conversation's turns are
    considered. Used both as a BackgroundTasks job after each chat and as
    a startup backfill over all conversations.

    Returns the number of turns embedded this call. Stops early (returns
    current count) if Ollama reports ``ai_available=False`` — we'll retry
    on the next trigger.
    """
    where = "WHERE e.turn_id IS NULL"
    params: Dict[str, Any] = {"lim": limit}
    if conv_id:
        where += " AND t.conversation_id = :conv"
        params["conv"] = conv_id

    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT t.id, t.content FROM conversation_turns t "
                f"LEFT JOIN conversation_turn_embeddings e ON e.turn_id = t.id "
                f"{where} ORDER BY t.id LIMIT :lim"
            ),
            params,
        ).fetchall()

    embedded = 0
    for turn_id, content in rows:
        vec = await embed_text(content or "")
        if vec is None:
            if embedded == 0:
                logger.info(
                    f"[embeddings] embed skipped for turn {turn_id} — "
                    "Ollama unavailable or dim mismatch"
                )
            break
        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO conversation_turn_embeddings "
                    "  (turn_id, model, dim, embedding) "
                    "VALUES "
                    f"  (:tid, :model, :dim, CAST(:vec AS vector({EMBED_DIM}))) "
                    "ON CONFLICT (turn_id) DO NOTHING"
                ),
                {
                    "tid": turn_id,
                    "model": state.OLLAMA_EMBED_MODEL,
                    "dim": EMBED_DIM,
                    "vec": _vec_literal(vec),
                },
            )
        embedded += 1
    if embedded:
        logger.info(f"[embeddings] embedded {embedded} turns"
                    + (f" for conv={conv_id}" if conv_id else ""))
    return embedded


async def retrieve_similar(
    query: str,
    exclude_conv_id: Optional[str] = None,
    k: int = DEFAULT_K,
    threshold: float = DEFAULT_THRESHOLD,
) -> List[Dict[str, Any]]:
    """Return the top-K past turns most similar to ``query``.

    Uses pgvector's ``<=>`` cosine-distance operator. Rows with distance
    >= ``threshold`` are filtered out (0 = identical, 1 = orthogonal).
    Self-matches within the current conversation can be excluded with
    ``exclude_conv_id`` to avoid trivial hits.
    """
    vec = await embed_text(query)
    if vec is None:
        return []

    where_extra = ""
    params: Dict[str, Any] = {
        "vec": _vec_literal(vec),
        "thresh": threshold,
        "k": k,
    }
    if exclude_conv_id:
        where_extra = "AND t.conversation_id <> :exclude "
        params["exclude"] = exclude_conv_id

    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT t.conversation_id, t.role, t.content, "
                f"       (e.embedding <=> CAST(:vec AS vector({EMBED_DIM}))) AS distance "
                f"FROM conversation_turn_embeddings e "
                f"JOIN conversation_turns t ON t.id = e.turn_id "
                f"WHERE (e.embedding <=> CAST(:vec AS vector({EMBED_DIM}))) < :thresh "
                f"{where_extra}"
                f"ORDER BY distance ASC LIMIT :k"
            ),
            params,
        ).fetchall()

    return [
        {
            "conversation_id": r[0],
            "role": r[1],
            "content": r[2],
            "distance": float(r[3]),
        }
        for r in rows
    ]


def format_rag_context(
    hits: List[Dict[str, Any]],
    max_chars: int = 800,
    snippet_len: int = 140,
) -> str:
    """Render retrieved hits as a compact system-prompt appendix."""
    if not hits:
        return ""
    lines = ["Related past discussions (for context only — do not repeat verbatim):"]
    for h in hits:
        snippet = (h.get("content") or "")[:snippet_len].replace("\n", " ").strip()
        lines.append(f"- [{h.get('role', '?')}] {snippet}")
    block = "\n".join(lines)
    if len(block) > max_chars:
        block = block[: max_chars - 3] + "..."
    return block


# ---------------------------------------------------------------------------
# Transaction embeddings — pipeline #2.
#
# Same model + dim as the conversation pipeline (single embed model keeps
# operational surface small). Differs in two ways: (a) keyed by
# ``transaction_id`` (string PK) not a serial id, and (b) we track a
# ``content_hash`` so we can re-embed in place when the user edits a
# transaction's description / category / notes.
# ---------------------------------------------------------------------------


def _txn_embed_text(txn: Dict[str, Any]) -> str:
    """Compose the embedding input for a transaction row.

    Description carries the merchant signal; category and notes add a
    little user-supplied semantics. Amount and date are deliberately
    omitted — they vary across legitimate matches (Netflix at $15.99 in
    March vs $17.99 in April should still cluster), and the SQL query
    can filter by them explicitly when needed.
    """
    parts = [
        (txn.get("description") or "").strip(),
        (txn.get("category") or "").strip(),
        (txn.get("notes") or "").strip(),
    ]
    return " | ".join(p for p in parts if p)


def _txn_content_hash(content: str) -> str:
    """sha1 of the embed-input string. Stored alongside the embedding so
    backfill can detect drift (description/category/notes edited) and
    re-embed in place without a separate dirty flag."""
    return hashlib.sha1(content.encode("utf-8")).hexdigest()


async def embed_pending_transactions(limit: int = DEFAULT_BACKFILL_LIMIT) -> int:
    """Embed transactions whose embedding is missing or whose
    ``content_hash`` no longer matches the current text.

    Source-of-truth for transactions is ``state.stored_transactions``
    (PgStore over ``json_stores``), not the structured ``transactions``
    table. We query the existing hashes in one shot, then iterate the
    PgStore snapshot. Stops early on Ollama-unavailable — next trigger
    retries.
    """
    txns = state.stored_transactions
    if not txns:
        return 0

    with sync_engine.connect() as conn:
        existing_rows = conn.execute(
            text("SELECT transaction_id, content_hash FROM transaction_embeddings")
        ).fetchall()
    existing_hashes: Dict[str, str] = {r[0]: r[1] for r in existing_rows}

    embedded = 0
    for tid, txn in list(txns.items())[:limit]:
        if not isinstance(txn, dict):
            continue
        content = _txn_embed_text(txn)
        if not content:
            continue
        new_hash = _txn_content_hash(content)
        if existing_hashes.get(tid) == new_hash:
            continue

        vec = await embed_text(content)
        if vec is None:
            if embedded == 0:
                logger.info(
                    f"[embeddings] txn embed skipped for {tid} — "
                    "Ollama unavailable or dim mismatch"
                )
            break

        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO transaction_embeddings "
                    "  (transaction_id, model, dim, embedding, content_hash) "
                    "VALUES "
                    f"  (:tid, :model, :dim, CAST(:vec AS vector({EMBED_DIM})), :hash) "
                    "ON CONFLICT (transaction_id) DO UPDATE SET "
                    "  embedding    = EXCLUDED.embedding, "
                    "  content_hash = EXCLUDED.content_hash, "
                    "  model        = EXCLUDED.model, "
                    "  dim          = EXCLUDED.dim, "
                    "  created_at   = NOW()"
                ),
                {
                    "tid": tid,
                    "model": state.OLLAMA_EMBED_MODEL,
                    "dim": EMBED_DIM,
                    "vec": _vec_literal(vec),
                    "hash": new_hash,
                },
            )
        embedded += 1

    if embedded:
        logger.info(f"[embeddings] embedded {embedded} transactions")
    return embedded


async def retrieve_similar_transactions(
    query: str,
    k: int = DEFAULT_K,
    threshold: float = DEFAULT_THRESHOLD,
) -> List[Dict[str, Any]]:
    """Return up to ``k`` transactions most similar to ``query``.

    Cosine search runs against ``transaction_embeddings``; per-hit fields
    (date, description, amount, category) are joined back from
    ``state.stored_transactions``. Hits whose source txn has been
    deleted are silently dropped (stale embedding rows are tolerated —
    next backfill / drift pass will not touch them, and they fall out
    on retrieval).
    """
    vec = await embed_text(query)
    if vec is None:
        return []

    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT transaction_id, "
                f"       (embedding <=> CAST(:vec AS vector({EMBED_DIM}))) AS distance "
                f"FROM transaction_embeddings "
                f"WHERE (embedding <=> CAST(:vec AS vector({EMBED_DIM}))) < :thresh "
                f"ORDER BY distance ASC LIMIT :k"
            ),
            {"vec": _vec_literal(vec), "thresh": threshold, "k": k},
        ).fetchall()

    out: List[Dict[str, Any]] = []
    for tid, distance in rows:
        txn = state.stored_transactions.get(tid)
        if not isinstance(txn, dict):
            continue
        out.append({
            "transaction_id": tid,
            "date": txn.get("date") or "",
            "description": txn.get("description") or "",
            "amount": float(txn.get("amount") or 0.0),
            "category": txn.get("category") or "",
            "distance": float(distance),
        })
    return out


def format_txn_rag_context(
    hits: List[Dict[str, Any]],
    max_chars: int = 600,
) -> str:
    """Render transaction hits as a compact system-prompt appendix."""
    if not hits:
        return ""
    lines = ["Related past transactions (the user may be referring to one of these):"]
    for h in hits:
        desc = (h.get("description") or "").replace("\n", " ").strip()[:60]
        category = h.get("category") or "Uncategorized"
        amount = h.get("amount", 0.0)
        date_str = h.get("date") or ""
        lines.append(f"- {date_str} | {desc} | ${amount:.2f} | {category}")
    block = "\n".join(lines)
    if len(block) > max_chars:
        block = block[: max_chars - 3] + "..."
    return block
