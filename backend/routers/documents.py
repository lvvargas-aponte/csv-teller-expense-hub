"""Knowledge-base document routes — uploads, list, delete, re-embed.

The advisor reads from this corpus via ``retrieve_similar_docs`` so the
upload pipeline must:

1. Extract text (``document_extractor.extract``) and reject unusable
   files at the boundary, returning a clear 4xx.
2. Persist the document row eagerly with ``status='pending'`` so the UI
   can show it immediately, then run chunking + embedding in a
   background task — embedding a 200-page IRS publication can take
   minutes and would otherwise block the request.
3. Surface failures via ``status='failed'`` + ``error`` so the user can
   see which docs need attention and trigger a re-embed.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel

import state
from db import documents_repo
from document_extractor import ExtractionError, extract, extract_by_content_type
from embeddings import chunk_text, embed_text
from url_fetcher import FetchError, fetch as fetch_url, get_allowed_hosts

logger = logging.getLogger(__name__)
router = APIRouter()


_VALID_SCOPES = {"external", "personal"}
_VALID_CATEGORIES = {
    "tax", "credit", "investing", "literacy",       # external
    "tax_return", "statement", "paystub", "loan",   # personal
    "unknown",
}


class DocumentSummary(BaseModel):
    id: int
    scope: str
    category: str
    title: str
    source: str
    uploaded_at: Optional[str]
    status: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}
    chunk_count: int = 0


class UploadResponse(BaseModel):
    id: Optional[int]
    status: str
    detected_type: Optional[str] = None
    duplicate: bool = False
    warning: Optional[str] = None
    # Set when a URL re-import detected upstream content drift.  The new
    # row's id is in ``id``; ``replaces_id`` points at the prior version
    # (now marked ``status='superseded'``).  UI can show a "Replaces
    # previous version" notice + diff link.
    replaces_id: Optional[int] = None
    replaces_uploaded_at: Optional[str] = None


def _validate_scope_category(scope: str, category: str) -> None:
    if scope not in _VALID_SCOPES:
        raise HTTPException(
            status_code=422,
            detail=f"scope must be one of {sorted(_VALID_SCOPES)}",
        )
    if category not in _VALID_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"category must be one of {sorted(_VALID_CATEGORIES)}",
        )


async def _embed_document(document_id: int) -> None:
    """Background task: chunk + embed + write chunks + flip status.

    Idempotent — replaces all chunks each run, so safe to retry.  On
    Ollama-unavailable we mark the doc 'failed' rather than leave it
    'pending' indefinitely; the user can re-trigger via the reembed
    endpoint once Ollama is back.
    """
    doc = documents_repo.get_document(document_id)
    if not doc:
        logger.warning(f"[documents] embed task: doc {document_id} vanished")
        return

    documents_repo.set_status(document_id, "embedding")
    try:
        chunks = chunk_text(doc["raw_text"])
        if not chunks:
            documents_repo.set_status(document_id, "failed", "no_text_to_embed")
            return

        embedded: List[Dict[str, Any]] = []
        for ch in chunks:
            vec = await embed_text(ch["content"])
            if vec is None:
                documents_repo.set_status(
                    document_id,
                    "failed",
                    "ollama_unavailable_or_dim_mismatch",
                )
                return
            embedded.append({**ch, "embedding": vec})

        documents_repo.replace_chunks(
            document_id, embedded, model=state.OLLAMA_EMBED_MODEL
        )
        documents_repo.set_status(document_id, "ready")
        logger.info(
            f"[documents] embedded doc {document_id} into {len(embedded)} chunks"
        )
    except Exception as e:
        logger.exception(f"[documents] embed failed for doc {document_id}")
        documents_repo.set_status(document_id, "failed", str(e)[:500])


@router.post("/documents", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    scope: str = Form(...),
    category: str = Form(...),
    title: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
):
    """Upload a PDF / TXT / MD document to the advisor's knowledge base.

    ``metadata`` is an optional JSON string with arbitrary fields
    (tax_year, account_id, employer, ...).  Embedding runs in a
    background task; poll ``GET /api/documents`` to watch ``status``
    progress from ``pending`` → ``embedding`` → ``ready``.
    """
    _validate_scope_category(scope, category)

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")

    try:
        text_body, meta = extract(raw, file.filename or "upload")
    except ExtractionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # Merge user-supplied metadata (wins) on top of detector hints.
    merged_meta: Dict[str, Any] = dict(meta)
    if metadata:
        try:
            merged_meta.update(json.loads(metadata))
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=422,
                detail=f"metadata must be valid JSON: {e}",
            ) from e

    doc_title = (title or file.filename or "Untitled").strip()
    doc_id = documents_repo.insert_document(
        scope=scope,
        category=category,
        title=doc_title,
        source=file.filename or "",
        raw_text=text_body,
        metadata=merged_meta,
    )

    if doc_id is None:
        # Same content_hash already in the corpus.
        return UploadResponse(id=None, status="duplicate", duplicate=True)

    background_tasks.add_task(_embed_document, doc_id)

    return UploadResponse(
        id=doc_id,
        status="pending",
        detected_type=meta.get("detected_type"),
        warning=meta.get("warning"),
    )


@router.get("/documents", response_model=List[DocumentSummary])
async def list_documents():
    """List all knowledge-base documents (most recent first)."""
    return documents_repo.list_documents()


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: int):
    """Delete a document and cascade-remove its chunks."""
    deleted = documents_repo.delete_document(document_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Document not found")


class UrlImportRequest(BaseModel):
    url: str
    scope: str
    category: str
    title: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@router.get("/documents/allowed-hosts", response_model=List[str])
async def list_allowed_hosts():
    """Hosts the URL-import endpoint will accept.

    The frontend reads this to decide whether to render an "Import" button
    next to each suggested seed link, so the allowlist is source-of-truth
    in the backend.  Includes runtime additions from custom seeds.
    """
    return sorted(get_allowed_hosts())


@router.post("/documents/from-url", response_model=UploadResponse)
async def import_from_url(req: UrlImportRequest, background_tasks: BackgroundTasks):
    """Fetch a URL through the SSRF-guarded fetcher and ingest the body.

    Only allowlisted hosts (see ``url_fetcher.ALLOWED_HOSTS``) are
    accepted — we do NOT support arbitrary user-supplied URLs yet.

    Source-of-truth URL choice: ``source`` stores the **user-requested**
    URL (what the seed list / API caller asked for).  The redirected
    ``final_url`` is kept in ``metadata.fetched_url`` for diagnostics and
    for the frontend's import-state matching.  Storing the requested URL
    as source means re-imports of the same seed dedupe correctly even
    when upstream redirects change between fetches.
    """
    _validate_scope_category(req.scope, req.category)
    requested_url = req.url.strip()

    try:
        body, content_type, final_url = fetch_url(requested_url)
    except FetchError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    try:
        text_body, meta = extract_by_content_type(body, content_type, hint_url=final_url)
    except ExtractionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    merged_meta: Dict[str, Any] = dict(meta)
    merged_meta["requested_url"] = requested_url
    merged_meta["fetched_url"] = final_url
    merged_meta["content_type"] = content_type
    if req.metadata:
        merged_meta.update(req.metadata)

    # Drift check: same requested URL + different content_hash means the
    # upstream page was edited since our last import.  Match against the
    # requested URL (what the user asked for) so seed-list re-imports
    # work even when redirect targets shift.
    new_hash = documents_repo.content_hash(text_body)
    prior = documents_repo.find_latest_by_source(requested_url)
    is_replacement = bool(prior and prior["content_hash"] != new_hash)
    if is_replacement:
        merged_meta["previous_version_id"] = prior["id"]
        merged_meta["previous_content_hash"] = prior["content_hash"]
        merged_meta["previous_uploaded_at"] = prior["uploaded_at"]

    # Prefer the user-supplied title, then the <title> tag, then the URL.
    doc_title = (
        (req.title or "").strip()
        or merged_meta.get("html_title")
        or requested_url
    )

    doc_id = documents_repo.insert_document(
        scope=req.scope,
        category=req.category,
        title=doc_title,
        source=requested_url,
        raw_text=text_body,
        metadata=merged_meta,
    )

    if doc_id is None:
        # Same content_hash already exists — could be the same URL imported
        # twice unchanged, or a different source with identical bytes.
        # Either way the corpus is unchanged.
        return UploadResponse(id=None, status="duplicate", duplicate=True)

    if is_replacement:
        documents_repo.mark_superseded(prior["id"], replaced_by_id=doc_id)

    background_tasks.add_task(_embed_document, doc_id)

    return UploadResponse(
        id=doc_id,
        status="pending",
        detected_type=meta.get("detected_type"),
        warning=meta.get("warning"),
        replaces_id=prior["id"] if is_replacement else None,
        replaces_uploaded_at=prior["uploaded_at"] if is_replacement else None,
    )


@router.post("/documents/{document_id}/reembed", response_model=UploadResponse)
async def reembed_document(document_id: int, background_tasks: BackgroundTasks):
    """Re-run chunking + embedding on a document.

    Useful when Ollama was down at upload time, or after we change the
    chunking strategy / embedding model.
    """
    doc = documents_repo.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    documents_repo.set_status(document_id, "pending", error=None)
    background_tasks.add_task(_embed_document, document_id)
    return UploadResponse(id=document_id, status="pending")
