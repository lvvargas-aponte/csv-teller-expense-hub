# AI advisor

> Source: `backend/routers/advisor.py`, `backend/llm_client.py`, `backend/embeddings.py`, `backend/db/models.py`

A multi-turn chat advisor that runs on a **local** Ollama LLM and is grounded in real data.

## Why local-only

- **Privacy** — your transactions never leave your machine.
- **Cost** — no per-token billing; runs as long as Ollama runs.
- **Offline-friendly** — works on a laptop with no internet.

The trade-off is hardware: a 14B model needs ~10 GB VRAM. Smaller fallbacks (`qwen2.5:7b`, `llama3.2:3b`) work on weaker setups; quality scales with size.

## Per-turn pipeline

1. **User sends a message** → `POST /api/advisor/chat`.
2. **Embed the message** with `sentence-transformers` (768-dim).
3. **Retrieve context**:
   - Recent transactions (last 6 months, summarized)
   - Live + manual balances, net worth
   - Active shared splits
   - Budgets, goals, recurring charges
   - Top-K document chunks by cosine similarity (RAG over the [Knowledge library](../tabs/finances-knowledge.md))
   - Past conversation turns by similarity (long-term memory across chats)
4. **Compose prompt** — system message + context + conversation history + new message.
5. **Call Ollama** at `OLLAMA_HOST` with `OLLAMA_CHAT_MODEL`.
6. **Persist the turn** (`conversation_turns` row) with the assistant reply and its embedding.

## Conversation lifecycle

- New chats get a UUID conversation_id.
- The first user turn auto-titles the chat (LLM-generated).
- Sidebar lists all conversations; deleting removes the row + its turns.

## Backfill on startup

If Ollama was down when a turn was saved, its embedding is `NULL`. On every backend start, `embed_pending_turns()` and `embed_pending_transactions()` catch up — see `backend/main.py` lifespan handler.

## When Ollama is unreachable

The endpoint returns a clear error; the chat UI shows it inline. Insights and Payoff Advice show a setup nudge card instead of failing.

See also: [AI Advisor tab](../tabs/finances-advisor.md), [Embeddings & RAG](embeddings.md).
