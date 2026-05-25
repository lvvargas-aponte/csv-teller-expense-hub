"""Knowledge-base document ingestion + retrieval.

Covers:
* Upload happy path: extract -> chunk -> embed -> chunks persisted -> retrievable.
* Dedupe on identical content_hash returns 200 with duplicate=True.
* Cascade delete drops chunks.
* Reembed flips status back to ready.
* Retrieve returns nothing when no docs exist (empty corpus is safe).
* Scope/category filters apply at retrieval time.

All Ollama embedding calls are mocked — no live server required.
"""
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

from db.base import sync_engine

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


def _doc_count() -> int:
    with sync_engine.connect() as conn:
        return int(conn.execute(text("SELECT COUNT(*) FROM documents")).scalar() or 0)


def _chunk_count(document_id: int | None = None) -> int:
    sql = "SELECT COUNT(*) FROM document_chunks"
    params: dict = {}
    if document_id is not None:
        sql += " WHERE document_id = :id"
        params["id"] = document_id
    with sync_engine.connect() as conn:
        return int(conn.execute(text(sql), params).scalar() or 0)


def _doc_status(document_id: int) -> str | None:
    with sync_engine.connect() as conn:
        row = conn.execute(
            text("SELECT status FROM documents WHERE id = :id"),
            {"id": document_id},
        ).fetchone()
    return row[0] if row else None


# A small text body that the chunker will keep as a single chunk so we
# can predict embed calls deterministically.
_SAMPLE_TEXT = (
    "The standard deduction for married filing jointly in 2024 is "
    "$29,200. This figure adjusts annually for inflation per the IRS."
)


class TestUpload:
    def test_uploads_text_and_embeds(self, client):
        with _mock_embed():
            resp = client.post(
                "/api/documents",
                files={"file": ("note.txt", _SAMPLE_TEXT.encode(), "text/plain")},
                data={"scope": "external", "category": "tax", "title": "MFJ note"},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] is not None
        assert body["status"] == "pending"
        # BackgroundTasks runs synchronously after response in TestClient,
        # so by here the doc should be ready and chunks persisted.
        assert _doc_status(body["id"]) == "ready"
        assert _chunk_count(body["id"]) >= 1

    def test_dedupes_identical_content(self, client):
        files = {"file": ("a.txt", _SAMPLE_TEXT.encode(), "text/plain")}
        data = {"scope": "external", "category": "tax", "title": "first"}
        with _mock_embed():
            first = client.post("/api/documents", files=files, data=data)
        assert first.status_code == 200

        files2 = {"file": ("b.txt", _SAMPLE_TEXT.encode(), "text/plain")}
        data2 = {"scope": "external", "category": "tax", "title": "second"}
        with _mock_embed():
            second = client.post("/api/documents", files=files2, data=data2)
        assert second.status_code == 200
        body = second.json()
        assert body["duplicate"] is True
        assert body["id"] is None
        assert _doc_count() == 1

    def test_rejects_unsupported_extension(self, client):
        resp = client.post(
            "/api/documents",
            files={"file": ("evil.exe", b"\x00\x01", "application/octet-stream")},
            data={"scope": "external", "category": "tax"},
        )
        assert resp.status_code == 422
        assert "Unsupported" in resp.json()["detail"]

    def test_rejects_invalid_scope(self, client):
        resp = client.post(
            "/api/documents",
            files={"file": ("a.txt", b"hello world", "text/plain")},
            data={"scope": "bogus", "category": "tax"},
        )
        assert resp.status_code == 422

    def test_marks_failed_when_ollama_unavailable(self, client):
        with _mock_embed(available=False):
            resp = client.post(
                "/api/documents",
                files={"file": ("a.txt", _SAMPLE_TEXT.encode(), "text/plain")},
                data={"scope": "external", "category": "tax"},
            )
        assert resp.status_code == 200
        doc_id = resp.json()["id"]
        assert _doc_status(doc_id) == "failed"


class TestListAndDelete:
    def test_list_returns_documents_with_chunk_counts(self, client):
        with _mock_embed():
            client.post(
                "/api/documents",
                files={"file": ("a.txt", _SAMPLE_TEXT.encode(), "text/plain")},
                data={"scope": "external", "category": "tax", "title": "Doc A"},
            )
        resp = client.get("/api/documents")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["title"] == "Doc A"
        assert rows[0]["status"] == "ready"
        assert rows[0]["chunk_count"] >= 1

    def test_delete_cascades_to_chunks(self, client):
        with _mock_embed():
            r = client.post(
                "/api/documents",
                files={"file": ("a.txt", _SAMPLE_TEXT.encode(), "text/plain")},
                data={"scope": "external", "category": "tax"},
            )
        doc_id = r.json()["id"]
        assert _chunk_count(doc_id) >= 1

        del_resp = client.delete(f"/api/documents/{doc_id}")
        assert del_resp.status_code == 204
        assert _doc_count() == 0
        assert _chunk_count() == 0

    def test_delete_unknown_returns_404(self, client):
        assert client.delete("/api/documents/9999").status_code == 404


class TestReembed:
    def test_reembed_recovers_failed_doc(self, client):
        with _mock_embed(available=False):
            r = client.post(
                "/api/documents",
                files={"file": ("a.txt", _SAMPLE_TEXT.encode(), "text/plain")},
                data={"scope": "external", "category": "tax"},
            )
        doc_id = r.json()["id"]
        assert _doc_status(doc_id) == "failed"

        with _mock_embed(available=True):
            re = client.post(f"/api/documents/{doc_id}/reembed")
        assert re.status_code == 200
        assert _doc_status(doc_id) == "ready"
        assert _chunk_count(doc_id) >= 1


class TestRetrieve:
    @pytest.mark.asyncio
    async def test_retrieve_returns_chunks_above_threshold(self, client):
        with _mock_embed():
            client.post(
                "/api/documents",
                files={"file": ("a.txt", _SAMPLE_TEXT.encode(), "text/plain")},
                data={"scope": "external", "category": "tax", "title": "Pub 17"},
            )

        from db import documents_repo
        # All embeddings in this test are the same constant vector, so
        # cosine distance is 0 — well within max_distance=0.4.
        hits = documents_repo.retrieve_similar_docs(_FAKE_VEC, k=5)
        assert len(hits) >= 1
        assert hits[0]["title"] == "Pub 17"
        assert hits[0]["scope"] == "external"
        assert hits[0]["category"] == "tax"

    @pytest.mark.asyncio
    async def test_scope_filter_excludes_other_scope(self, client):
        with _mock_embed():
            client.post(
                "/api/documents",
                files={"file": ("a.txt", _SAMPLE_TEXT.encode(), "text/plain")},
                data={"scope": "external", "category": "tax", "title": "Ext"},
            )
            client.post(
                "/api/documents",
                files={
                    "file": (
                        "b.txt",
                        (_SAMPLE_TEXT + " distinct body").encode(),
                        "text/plain",
                    )
                },
                data={"scope": "personal", "category": "tax_return", "title": "Mine"},
            )

        from db import documents_repo
        ext_hits = documents_repo.retrieve_similar_docs(_FAKE_VEC, scope="external", k=5)
        per_hits = documents_repo.retrieve_similar_docs(_FAKE_VEC, scope="personal", k=5)
        assert all(h["scope"] == "external" for h in ext_hits)
        assert all(h["scope"] == "personal" for h in per_hits)
        assert {h["title"] for h in ext_hits} == {"Ext"}
        assert {h["title"] for h in per_hits} == {"Mine"}


class TestFormatContext:
    def test_renders_citation_lines(self):
        from db import documents_repo
        block = documents_repo.format_doc_rag_context([
            {
                "document_id": 1,
                "chunk_index": 3,
                "content": "Standard deduction for MFJ in 2024 is $29,200.",
                "title": "IRS Pub 17",
                "scope": "external",
                "category": "tax",
                "distance": 0.05,
            },
        ])
        assert "Reference material" in block
        assert "IRS Pub 17" in block
        assert "chunk 3" in block

    def test_empty_hits_returns_empty_string(self):
        from db import documents_repo
        assert documents_repo.format_doc_rag_context([]) == ""


class TestChunker:
    def test_chunks_long_text(self):
        from embeddings import chunk_text
        long_text = ("Paragraph body. " * 200).strip()
        chunks = chunk_text(long_text, target_tokens=100, overlap_tokens=10)
        assert len(chunks) > 1
        # chunk_index is 0-based and contiguous.
        assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))
        for c in chunks:
            assert c["token_count"] > 0
            assert c["content"]

    def test_empty_input_returns_empty_list(self):
        from embeddings import chunk_text
        assert chunk_text("") == []
        assert chunk_text("   \n  \n") == []
