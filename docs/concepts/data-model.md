# Data model

> Source: `backend/db/models.py`, `backend/alembic/versions/*`

All data lives in **Postgres 16** with the **pgvector** extension. Migrations are managed by Alembic and applied on container start.

## Core tables

| Table | Purpose |
|---|---|
| `accounts` | One row per account (SimpleFIN bank, SnapTrade brokerage, manual, or CSV-synth) |
| `transactions` | Every transaction; the heart of the app |
| `account_details` | Credit-card metadata (APR, limit, statement/due day) |
| `balance_snapshots` | Point-in-time balance (live + manual + SnapTrade) — feeds net-worth history |
| `holdings` | Per-position brokerage / crypto detail (symbol, quantity, cost basis, market value) — current snapshot, replaced each SnapTrade sync |
| `budgets` | Monthly category limits |
| `goals` | Savings goals with target + pace |
| `user_profile` | Person names + global settings |
| `seeds` | Category-suggestion seed data (customizable) |

## Conversation tables

| Table | Purpose |
|---|---|
| `conversations` | One row per chat session (id, title, timestamps) |
| `conversation_turns` | Each message; `role` ∈ {user, assistant}; `embedding` (vector) for semantic recall |

## Knowledge tables

| Table | Purpose |
|---|---|
| `documents` | Uploaded files / URLs (filename, type, extracted text, status) |
| `document_chunks` | Chunked text + embedding (vector) for RAG |
| `transaction_embeddings` | One per transaction, used for semantic search by the advisor |

## Lifecycle highlights

- **Transactions** — inserted from SimpleFIN sync or CSV upload; rows persist (the in-memory "review queue" is a working set, not the source of truth).
- **Balances** — live values come from the SimpleFIN API per request; manual values from `balance_snapshots`.
- **Embeddings** — written async; backfilled on startup if any are NULL.
- **Conversations** — soft state; safe to delete entire rows.

## Migrations

Schema changes live in `backend/alembic/versions/`. Examples:

- `0001_initial.py` — base schema
- `0005_documents.py` — document RAG
- `0006_seeds.py` — category seeds
- `0008_holdings.py` — per-position investment detail (SnapTrade)

Container entry script (`backend/entrypoint.sh`) runs `alembic upgrade head` before launching uvicorn.
