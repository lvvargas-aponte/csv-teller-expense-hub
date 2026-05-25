# Finances → Knowledge

> Source: `frontend/src/components/finances/KnowledgeSection.js`, `backend/routers/documents.py`, `backend/embeddings.py`

A document library that grounds the **AI Advisor**. Uploaded files are chunked, embedded, and made available to the chat as retrieval context (RAG).

## Two categories

| Category | Examples |
|---|---|
| **External (reference)** | Tax-bracket explainers, credit-utilization guides, investing primers |
| **Personal** | Tax returns, brokerage statements, paystubs, lease agreements |

The UI offers **suggested seeds** — curated public PDFs/URLs you can add with one click as starter reference material.

## Adding a document

- **Upload PDF** — pick a local file. Status: `processing` → `embedded` (or `failed`).
- **From URL** — paste a public URL; the backend fetches, extracts text, embeds.
- **Re-embed** — if embeddings failed (Ollama was down, etc.), retry without re-uploading.

## Privacy

Personal documents stay in your Postgres instance — they are never sent off-device. The advisor pulls relevant chunks at chat time and includes them in the local Ollama prompt.

## Under the hood

- `POST /api/documents` (file upload)
- `POST /api/documents/from-url`
- `GET /api/documents`
- `POST /api/documents/{id}/reembed`
- `DELETE /api/documents/{id}`
- Embeddings: `sentence-transformers` → 768-dim vectors → pgvector

See also: [Embeddings & RAG concept](../concepts/embeddings.md).
