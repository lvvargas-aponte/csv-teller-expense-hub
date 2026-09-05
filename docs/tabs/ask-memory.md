# Ask → Memory

> Source: `frontend/src/components/finances/KnowledgeSection.js`, `knowledge/SuggestedSeeds.js`, `backend/routers/documents.py`, `backend/routers/seeds.py`, `backend/embeddings.py`

The document library **Fin** searches. Uploaded files are chunked, embedded, and retrieved by Fin's
`search_documents` tool when a question calls for them.

## Two kinds of document

| Kind | Categories |
|---|---|
| **External (reference)** | Tax / IRS guidance · Credit / debt strategy · Investing / retirement · General financial literacy |
| **Personal** | Tax return (1040 / W-2 / 1099) · Account statement · Pay stub / benefits · Loan / mortgage doc |

The category is what tells Fin *how* to weigh a document — external reference is general advice,
personal is a fact about you.

## Suggested seeds

A curated list of public PDFs and URLs you can add with one click as starter reference material.
Dismissing one hides it; hidden seeds can be restored.

Backend: `GET /api/seeds`, `GET /api/seeds/hidden`, `POST /api/seeds`,
`DELETE /api/seeds/{id}`, `POST /api/seeds/restore/{default_id}`.

## Adding a document

- **Upload** — pick a local file.
- **From URL** — paste a public URL; the backend fetches it and extracts the text. Fetching is
  restricted to an allowlist (`GET /api/documents/allowed-hosts`), so a URL is not an arbitrary
  outbound request.
- **Re-embed** — retry a failed embed without re-uploading.

### Status badges

| Status | Meaning |
|---|---|
| **Pending** | Queued, not started |
| **Embedding…** | In flight — the list polls until it settles |
| **Ready** | Chunked and embedded; Fin can find it |
| **Failed** | Extraction or embedding failed. **Re-embed** retries — the usual cause is Ollama being down. |
| **Duplicate** | The same content is already in the library |
| **Superseded** | A newer version of the same document replaced it |

## Privacy

Personal documents stay in your Postgres instance and are never sent off-device. Embedding runs
against your **local** Ollama. Fin pulls matching chunks at chat time and puts them in a local
prompt.

## Under the hood

- `POST /api/documents` — file upload
- `POST /api/documents/from-url` — fetch + extract
- `GET /api/documents` — list
- `GET /api/documents/allowed-hosts` — the URL allowlist
- `POST /api/documents/{id}/reembed` — retry
- `DELETE /api/documents/{id}` — remove
- Embeddings: Ollama `nomic-embed-text` → 768-dim vectors → pgvector

Embedding degrades gracefully: when Ollama is unreachable the upload still lands, the document sits
at **Failed**, and everything else in the app keeps working.

See also: [Embeddings & RAG concept](../concepts/embeddings.md), [Ask → Advisor](ask-advisor.md).
