"""Repository for the documents + document_chunks tables.

Sync SQL via ``sync_engine`` to match the rest of the embeddings pipeline
(``embeddings.py`` is sync for DB, async only for the Ollama HTTP call).

Retrieval uses pgvector's ``<=>`` cosine-distance operator with the same
threshold conventions as ``retrieve_similar_transactions`` so the
advisor sees consistent precision across all three RAG sources
(turns / transactions / documents).
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from db.base import sync_engine
from embeddings import EMBED_DIM, _vec_literal

logger = logging.getLogger(__name__)


def content_hash(raw_text: str) -> str:
    """sha256 over the document body — used for dedupe + change detection."""
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def insert_document(
    *,
    scope: str,
    category: str,
    title: str,
    source: str,
    raw_text: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """Insert a document row.  Returns the new id, or ``None`` if a row
    with the same content_hash already exists (dedupe — the caller can
    treat this as success)."""
    h = content_hash(raw_text)
    meta_json = json.dumps(metadata or {})

    with sync_engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM documents WHERE content_hash = :h LIMIT 1"),
            {"h": h},
        ).fetchone()
        if existing:
            logger.info(
                f"[documents] dedupe hit: content_hash={h[:12]}… already at id={existing[0]}"
            )
            return None

        row = conn.execute(
            text(
                "INSERT INTO documents "
                "  (scope, category, title, source, raw_text, content_hash, "
                "   doc_metadata, status) "
                "VALUES "
                "  (:scope, :category, :title, :source, :raw, :hash, "
                "   CAST(:meta AS JSONB), 'pending') "
                "RETURNING id"
            ),
            {
                "scope": scope,
                "category": category,
                "title": title,
                "source": source,
                "raw": raw_text,
                "hash": h,
                "meta": meta_json,
            },
        ).fetchone()
        return int(row[0]) if row else None


def find_latest_by_source(source: str) -> Optional[Dict[str, Any]]:
    """Return the most-recent document with this exact ``source`` (URL).

    Used by the URL-import path to detect content drift on re-fetch:
    same source + different content_hash means the upstream page changed
    since we last imported it.  Returns None when nothing matches.
    """
    if not source:
        return None
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, content_hash, title, uploaded_at, doc_metadata "
                "FROM documents WHERE source = :src "
                "ORDER BY uploaded_at DESC LIMIT 1"
            ),
            {"src": source},
        ).fetchone()
    if not row:
        return None
    return {
        "id": int(row[0]),
        "content_hash": row[1],
        "title": row[2],
        "uploaded_at": row[3].isoformat() if row[3] else None,
        "metadata": row[4] or {},
    }


def mark_superseded(document_id: int, replaced_by_id: int) -> None:
    """Annotate an older version as superseded by ``replaced_by_id``.

    Doesn't delete — the user controls cleanup so prior citations stay
    auditable.  We just set ``status='superseded'`` and stash the
    successor id in metadata so the UI can render a "View replacement"
    affordance later.
    """
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                # CAST(...) rather than ``:patch::jsonb`` — the trailing
                # ``::`` stops text() from recognizing :patch as a bind
                # param, which reaches the driver as literal SQL.
                "UPDATE documents "
                "SET status = 'superseded', "
                "    doc_metadata = doc_metadata || CAST(:patch AS JSONB) "
                "WHERE id = :id"
            ),
            {
                "id": document_id,
                "patch": json.dumps({"replaced_by_id": replaced_by_id}),
            },
        )


def set_status(document_id: int, status: str, error: Optional[str] = None) -> None:
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE documents SET status = :s, error = :e WHERE id = :id"
            ),
            {"s": status, "e": error, "id": document_id},
        )


def replace_chunks(
    document_id: int,
    chunks: List[Dict[str, Any]],
    model: str,
) -> None:
    """Atomically replace the chunks for a document.

    Used both on first ingest and on re-embed (chunking strategy or
    embedding model change).  Each chunk dict must carry
    ``chunk_index``, ``content``, ``token_count``, and ``embedding``
    (a 768-element list of floats).
    """
    with sync_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM document_chunks WHERE document_id = :id"),
            {"id": document_id},
        )
        for ch in chunks:
            conn.execute(
                text(
                    "INSERT INTO document_chunks "
                    "  (document_id, chunk_index, content, token_count, "
                    "   embedding, model, dim) "
                    "VALUES "
                    "  (:id, :idx, :content, :tokens, "
                    f"   CAST(:vec AS vector({EMBED_DIM})), :model, :dim)"
                ),
                {
                    "id": document_id,
                    "idx": ch["chunk_index"],
                    "content": ch["content"],
                    "tokens": ch["token_count"],
                    "vec": _vec_literal(ch["embedding"]),
                    "model": model,
                    "dim": EMBED_DIM,
                },
            )


def delete_document(document_id: int) -> int:
    """Cascade-delete a document (chunks go with it via FK)."""
    with sync_engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM documents WHERE id = :id"),
            {"id": document_id},
        )
        return result.rowcount or 0


def list_documents() -> List[Dict[str, Any]]:
    """Return all documents with chunk counts.  Light enough for the
    Knowledge tab list view at single-user scale."""
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT d.id, d.scope, d.category, d.title, d.source, "
                "       d.uploaded_at, d.status, d.error, d.doc_metadata, "
                "       (SELECT COUNT(*) FROM document_chunks c WHERE c.document_id = d.id) "
                "FROM documents d ORDER BY d.uploaded_at DESC"
            )
        ).fetchall()
    return [
        {
            "id": int(r[0]),
            "scope": r[1],
            "category": r[2],
            "title": r[3],
            "source": r[4],
            "uploaded_at": r[5].isoformat() if r[5] else None,
            "status": r[6],
            "error": r[7],
            "metadata": r[8] or {},
            "chunk_count": int(r[9] or 0),
        }
        for r in rows
    ]


def get_document(document_id: int) -> Optional[Dict[str, Any]]:
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, scope, category, title, source, raw_text, "
                "       doc_metadata, status, error "
                "FROM documents WHERE id = :id"
            ),
            {"id": document_id},
        ).fetchone()
    if not row:
        return None
    return {
        "id": int(row[0]),
        "scope": row[1],
        "category": row[2],
        "title": row[3],
        "source": row[4],
        "raw_text": row[5],
        "metadata": row[6] or {},
        "status": row[7],
        "error": row[8],
    }


def retrieve_similar_docs(
    query_vec: List[float],
    *,
    scope: Optional[str] = None,
    category: Optional[str] = None,
    k: int = 4,
    max_distance: float = 0.4,
) -> List[Dict[str, Any]]:
    """Top-K chunks most similar to ``query_vec``.

    ``scope`` / ``category`` apply as SQL WHERE filters when set so the
    advisor can lean external for "how does X work" questions and
    personal for "based on my docs" questions.  ``max_distance`` is a
    cosine-distance ceiling — better to inject nothing than weak hits.
    """
    where = [
        f"(c.embedding <=> CAST(:vec AS vector({EMBED_DIM}))) < :thresh"
    ]
    params: Dict[str, Any] = {
        "vec": _vec_literal(query_vec),
        "thresh": max_distance,
        "k": k,
    }
    if scope:
        where.append("d.scope = :scope")
        params["scope"] = scope
    if category:
        where.append("d.category = :category")
        params["category"] = category

    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.document_id, c.chunk_index, c.content, "
                "       d.title, d.scope, d.category, "
                f"       (c.embedding <=> CAST(:vec AS vector({EMBED_DIM}))) AS distance "
                "FROM document_chunks c "
                "JOIN documents d ON d.id = c.document_id "
                f"WHERE {' AND '.join(where)} "
                "ORDER BY distance ASC LIMIT :k"
            ),
            params,
        ).fetchall()

    return [
        {
            "document_id": int(r[0]),
            "chunk_index": int(r[1]),
            "content": r[2],
            "title": r[3],
            "scope": r[4],
            "category": r[5],
            "distance": float(r[6]),
        }
        for r in rows
    ]


def format_doc_rag_context(
    hits: List[Dict[str, Any]],
    max_chars: int = 1500,
    snippet_len: int = 240,
) -> str:
    """Render document hits as a system-prompt appendix.

    Citation-friendly: each line carries title + chunk_index so the
    advisor can name its source per the SYSTEM_PROMPT update.
    """
    if not hits:
        return ""
    lines = [
        "Reference material (cite by title when you rely on it; "
        "do not invent rules absent from these excerpts):"
    ]
    for h in hits:
        snippet = (h.get("content") or "")[:snippet_len].replace("\n", " ").strip()
        title = h.get("title") or "Untitled"
        category = h.get("category") or "?"
        idx = h.get("chunk_index", 0)
        lines.append(f"- [{category}] {title} (chunk {idx}): {snippet}")
    block = "\n".join(lines)
    if len(block) > max_chars:
        block = block[: max_chars - 3] + "..."
    return block
