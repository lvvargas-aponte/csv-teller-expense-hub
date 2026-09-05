# Data model

> Source: `backend/db/models.py`, `backend/alembic/versions/*`

All data lives in **Postgres 16** with the **pgvector** extension. Migrations are managed by Alembic and applied on container start.

## Core tables

| Table | Purpose |
|---|---|
| `accounts` | One row per account (SimpleFIN bank, SnapTrade brokerage, manual, or CSV-synth) |
| `transactions` | Every transaction; the heart of the app |
| `account_details` | Per-account metadata — APR, credit limit, statement/due day, monthly payment, opened/closed dates (`0022`), real-asset and tax-treatment fields (`0023`, `0027`) |
| `balance_snapshots` | Point-in-time balance (live + manual + SnapTrade) — feeds net-worth history |
| `holding_cost_overrides` | Cost basis you entered by hand, overriding the brokerage (`0026`) |
| `holdings` | Per-position brokerage / crypto detail (symbol, quantity, cost basis, market value) — current snapshot, replaced each SnapTrade sync |
| `budgets` | Monthly category limits |
| `goals` | Savings goals with target + pace |
| `user_profile` | Financial profile — risk, horizon, income, reserves (`0020`), retirement (`0025`), marginal rate (`0028`) |
| `seed_custom` / `seed_removed_defaults` | Suggested reference material — your additions, and the defaults you hid |

## Conversation tables

| Table | Purpose |
|---|---|
| `conversations` | One row per chat session (id, title, timestamps) |
| `conversation_turns` | Each message; `role` ∈ {user, assistant}; `embedding` (vector) for semantic recall |

## Fin's memory tables

| Table | Purpose |
|---|---|
| `documents` | Uploaded files / URLs (filename, type, extracted text, status) |
| `document_chunks` | Chunked text + embedding (vector) for RAG |
| `transaction_embeddings` | One per transaction, for semantic transaction search |
| `user_facts` | Durable facts Fin extracted about you, with confirm/reject state (`0010`) |
| `fact_reflection_state` | Watermark for the background fact-extraction job (`0013`) |
| `advisor_style_profile` | Fin's read on how you like to be talked to (`0007`) |
| `advisor_turn_feedback` | Your thumbs up/down per turn (`0007`) |
| `conversation_turn_embeddings` | Per-turn vectors for `recall_past_conversation` |
| `user_fact_embeddings` | Per-fact vectors, used to dedupe proposed facts (`0010`) |

## Commitments & planning

| Table | Purpose |
|---|---|
| `subscription_reviews` | Your keep / cancel / ignore decision per merchant, the amount at review time, and your `declared_cadence` / `declared_type` overrides (`0011`, `0029`) |
| `merchant_aliases` | User-declared merges — `alias_key` folds into `canonical_key` so a renamed merchant stays one commitment (`0030`) |
| `category_rules` | Merchant→category rules, in evaluation order (`0021`) |
| `digests` | The weekly digest surfaced in Home's Needs-you feed (`0012`) |
| `scheduled_tasks` | Recurring background syncs Fin can create (`0014`) |

## Shared expenses

| Table | Purpose |
|---|---|
| `instance_identity` | Who this install is, and its person slot (`0015`) |
| `peers` | The other household member's install (`0016`, `0017`) |
| `peer_shared_transactions` | Rows pulled from the peer via the sheet (`0016`) |
| `sync_runs` / `sync_row_state` | Push/pull history and per-row watermarks (`0018`) |
| `sync_corrections` | Edits the peer made to rows you had already synced (`0018`) |
| `period_settlements` | Per-month ready / paid state (`0019`) |

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
- `0014_scheduled_tasks.py` — recurring background syncs
- `0016`–`0019` — peer-to-peer shared expenses and settlement
- `0029_declared_cadence.py` — user overrides for a commitment's cadence and kind
- `0030_merchant_aliases.py` — folding several merchant keys into one commitment

The head revision is `0030`.

Container entry script (`backend/entrypoint.sh`) runs `alembic upgrade head` before launching uvicorn.
