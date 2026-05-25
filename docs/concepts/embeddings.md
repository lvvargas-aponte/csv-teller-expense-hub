# Embeddings & RAG

> Source: `backend/embeddings.py`, `backend/db/documents_repo.py`, `backend/routers/advisor.py`, `backend/db/models.py`, `backend/alembic/versions/*`

The advisor ("Fin") does **not** train on your data — there is no fine-tuning anywhere in this app. Personalization comes from **Retrieval-Augmented Generation (RAG)**: at every chat turn, the backend pulls the most relevant slices of your data from Postgres and pastes them into the system prompt before calling the LLM. The model sees fresh context every turn; nothing is baked into weights.

This page explains, in detail, how that retrieval works end-to-end.

## The big picture

```
                           ┌─────────────────────────┐
   user message  ─────►    │  POST /api/advisor/chat │
                           └────────────┬────────────┘
                                        │
                ┌───────────────────────┼────────────────────────┐
                ▼                       ▼                        ▼
       build_financial_       embed(user message)          load conversation
       snapshot()  (SQL)      with nomic-embed-text        history (last N turns)
                │                       │                        │
                │           ┌───────────┼───────────┐            │
                │           ▼           ▼           ▼            │
                │   retrieve_similar    │   retrieve_similar_    │
                │   (past chat turns)   │   transactions         │
                │                       ▼                        │
                │            retrieve_similar_docs               │
                │            (your uploads + curated seeds)      │
                ▼                       ▼                        ▼
        ┌────────────────────────────────────────────────────────┐
        │  Compose system prompt: persona + style notes +        │
        │  snapshot + 3 RAG blocks                               │
        └────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                       chat_ollama(messages, system)
                                  │
                                  ▼
                              assistant reply
```

There are **three independent vector indexes** and one **structured snapshot**, all fused into the prompt for each turn.

## The embedding model

| Property | Value |
|---|---|
| Model | `nomic-embed-text` (served by Ollama) |
| Dimensions | **768** |
| Distance metric | Cosine (`<=>` in pgvector) |
| Index type | **HNSW** |
| Storage | Postgres `vector(768)` columns via the `pgvector` extension |
| Failure mode | If Ollama is down or returns the wrong dim, `embed_text` logs and returns `None`. RAG silently skips for that turn — the chat still works, just with less context. |

The single embedding model is intentional: every vector in the system lives in the same 768-dim space, so a future cross-index retriever could compare them directly. Swapping to a higher-precision model later means **adding a parallel column** (e.g. `embedding_1024`) rather than mutating the existing 768 infrastructure.

## What gets embedded

| Source | Table | Trigger |
|---|---|---|
| Conversation turns | `conversation_turn_embeddings` (FK → `conversation_turns.id`) | Background task after each chat reply; startup backfill via `embed_pending_turns()` |
| Transactions | `transaction_embeddings` (keyed by `transaction_id`, with `content_hash`) | After import / edit / category change; startup backfill via `embed_pending_transactions()` |
| Document chunks | `document_chunks.embedding` (FK → `documents.id`) | After upload, URL fetch, or re-embed |

### Transaction embedding text

`_txn_embed_text` deliberately omits amount and date:

```
description | category | notes
```

The reasoning is in the code: Netflix at $15.99 in March vs. $17.99 in April should still cluster. SQL filters handle the numeric/temporal side when needed.

### Document chunking

`chunk_text` produces overlapping pieces tuned for `nomic-embed-text`'s 8K-token window:

- Target ~350 tokens per chunk (estimated as char ÷ 4)
- 50-token overlap so a sentence split across chunks doesn't lose context
- Splits on blank-line paragraphs first, then sentences, then hard-cuts as a last resort

Why small chunks? One bad sentence pollutes one chunk's vector, not an entire IRS publication.

### Content-hash drift detection

Transaction rows store `content_hash = sha1(description | category | notes)` next to the vector. The backfill loop compares hashes and **re-embeds only when the text actually changed** — editing a transaction's category triggers a re-embed; importing the same CSV twice does not.

## Retrieval at chat time

The retrievers all share the same shape:

1. Embed the user's message with `embed_text`.
2. Run a pgvector cosine search (`<=>`), `ORDER BY distance ASC LIMIT k`.
3. Drop hits above a distance threshold (0 = identical, 1 = orthogonal).

| Retriever | Source | Default `k` | Threshold | Notes |
|---|---|---|---|---|
| `retrieve_similar` | `conversation_turn_embeddings` | 5 | 0.35 | Excludes the **current** conversation to avoid trivial self-matches |
| `retrieve_similar_transactions` | `transaction_embeddings` | 5 | 0.35 | Joins back to `state.stored_transactions` for date/amount/category — silently drops hits whose source txn was deleted |
| `retrieve_similar_docs` | `document_chunks` | 4 | 0.40 (tighter) | Filters by `scope` (`external` reference vs. `personal` uploads) and optional `category` |

The doc retriever uses a **tighter** threshold (0.40) than turns/txns. Rationale from the code: for financial advice, "no excerpt" is preferable to a weakly-related one.

## How retrieved context becomes a prompt

`backend/routers/advisor.py::chat` rebuilds the system prompt from scratch on every turn:

1. **Persona** — `SYSTEM_PROMPT` ("Fin, the user's money-smart friend...")
2. **Style profile** — the 6-bullet `style_notes` blob from `advisor_style_profile`, written by `style_reflection.refresh_style_profile` based on your 👍/👎 thumbs feedback. This is the only thing that "learns" over time, and it's still just a prompt — the model itself doesn't change.
3. **Wealth architect prompt** — fixed instructional scaffold.
4. **Financial snapshot** — output of `analytics.build_financial_snapshot()`: accounts, balances, recurring charges, budgets with statuses, goals with statuses + live `available` overrides, credit debts (APR / min payment / due day / limit), and user profile (risk / horizon / dependents / debt strategy).
5. **RAG block A** — `format_rag_context(retrieve_similar(...))` — past chat discussions.
6. **RAG block B** — `format_txn_rag_context(retrieve_similar_transactions(...))` — specific historical charges that look related.
7. **RAG block C** — `format_doc_rag_context(retrieve_similar_docs(...))` — excerpts from your uploaded docs and curated knowledge seeds.

Each block formats hits as compact, character-budgeted bullets. The composed string is passed as `system` to `chat_ollama`; the conversation history (trimmed) is the `messages` payload.

Every retrieval block is wrapped in `try/except` and logs a warning on failure. **Embeddings are best-effort**: an Ollama hiccup degrades context, never breaks the chat.

## Backfill on startup

`backend/main.py`'s lifespan handler runs:

- `embed_pending_turns()` — embeds any conversation turn whose embedding row is missing (e.g. Ollama was down when the turn was saved).
- `embed_pending_transactions()` — same for transactions, plus re-embeds rows whose `content_hash` no longer matches.

Both are idempotent no-ops when everything is current. They stop early if Ollama reports unavailable and retry on the next trigger.

## Why pgvector instead of a dedicated vector DB?

One Postgres = one operational story (one backup, one connection pool, one transaction model). At household scale (~10⁴–10⁵ rows across all three indexes), pgvector with HNSW is comfortably fast and avoids the operational tax of running a separate Pinecone / Weaviate / Qdrant.

## Where to look in code

| Concern | File |
|---|---|
| Embedding + retrieval primitives | `backend/embeddings.py` |
| Document chunk retrieval | `backend/db/documents_repo.py` |
| Prompt composition + per-turn pipeline | `backend/routers/advisor.py::chat` |
| Structured snapshot builder | `backend/analytics.py::build_financial_snapshot` |
| Style-notes reflection (👍/👎 → prompt) | `backend/style_reflection.py`, `backend/db/style_profile_repo.py` |
| Vector schema + HNSW indexes | `backend/alembic/versions/0001_initial.py`, `0003_transaction_embeddings.py`, `0005_documents.py` |

See also: [AI advisor](advisor.md), [Finances → Knowledge tab](../tabs/finances-knowledge.md).
