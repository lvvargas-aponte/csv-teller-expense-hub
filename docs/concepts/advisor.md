# AI advisor

> Source: `backend/routers/advisor.py`, `backend/llm_client.py`, `backend/embeddings.py`, `backend/agent/`, `backend/fact_reflection.py`

A multi-turn chat advisor (**Fin**) that runs on a **local** Ollama LLM and is grounded in real data through a **bounded tool-use loop**. Fin is designed to be a financial advisor *and* a friend: it learns durable facts about you over time, gives direct, opinionated takes on strategy questions ("should I keep my NVDA?"), and can reach live market data and the open web — while the LLM itself stays fully local.

## Why a local LLM

- **Privacy** — your transactions never leave your machine; only tool-initiated web/market lookups go out.
- **Cost** — no per-token billing; runs as long as Ollama runs.

The trade-off is hardware: reliable tool-calling needs Qwen 2.5 14B+ (~10 GB VRAM); quality scales with size.

## Per-turn pipeline

1. **User sends a message** → `POST /api/advisor/chat` (blocking) or `POST /api/advisor/chat/stream` (SSE — the chat UI's default; emits live `token` / `tool_call` / `tool_result` events, then a `done` payload).
2. **Build a lean system prompt** — Fin persona + style notes + tool guide + confirmed user-facts memory block + rolling conversation summary + a ~200-byte facts header (net worth, cash, debt, investments).
3. **Run the harness loop** (`agent.harness.run_agent`) up to `ADVISOR_AGENT_MAX_ITERS` (default 10) iterations:
    - Send messages + tools to Ollama's `/api/chat`.
    - If the model emits `tool_calls`, validate each against its Pydantic schema, execute the batch **concurrently** (`asyncio.gather`), feed results back as `role: tool` messages in call order.
    - If the model emits a final reply, terminate.
4. **Persist the turn** (`conversation_turns` row) plus the structured `trajectory` JSONB, then schedule background embedding, style reflection, fact extraction, and conversation compaction.

**Conversation compaction** (`conversation_compaction.py`): only the last 20 messages are sent per turn; a background job rolls anything older into a ≤12-bullet summary stored on the conversation and injected each turn, so long chats keep continuity.

The model is an active consumer — it decides what to fetch based on the question. Simple questions cost 1-2 tool calls; strategy questions chain `get_investments → get_stock_quote → web_search → fetch_webpage` before synthesizing.

## Learning about the user

Two complementary loops run in the background:

- **Style reflection** (`style_reflection.py`) — every 10 user turns, summarizes how you talk + thumbed-up replies into a 6-bullet style guide injected each turn.
- **Fact extraction** (`fact_reflection.py`) — every 8 user turns, scans recent messages for durable personal facts (life events, goals, constraints, preferences, patterns) and proposes them into `user_facts`. Near-duplicates of existing facts — including ones you **rejected** — are skipped via embedding similarity. Fin can also propose facts mid-conversation via the `remember_about_user` tool.

Proposed facts appear in the Memory panel for confirm/reject; confirmed facts are injected into every turn's prompt (capped by `ADVISOR_MEMORY_INJECT_LIMIT`) and searchable via `recall_about_user`.

## Tools

| Tool | Wraps | When Fin uses it |
|---|---|---|
| `think` | nothing (planning scratchpad) | first call on multi-step strategy questions |
| `search_transactions` | `embeddings.retrieve_similar_transactions` + filters | "what was that $300 charge" |
| `get_balance` | `analytics._balances_snapshot` | "how much cash do I have" (totals) |
| `list_accounts` | `analytics._balances_snapshot` account rows | "what accounts do I have", account names + per-account balances |
| `get_debt` | balances + `state.account_details` side-car | "how much do I owe on Chase" |
| `get_budget_status` | `analytics.compute_budget_statuses` | "am I over on dining" |
| `get_goal_status` | `analytics.compute_goal_statuses` | "am I on pace with my emergency fund" |
| `get_category_spending` | `analytics.category_spending_summary` | "how much did I spend on X this year" |
| `get_investments` | `analytics._investments_snapshot` | portfolio, allocation, concentration |
| `project_cashflow` | recurring outflow + income estimate + inbound transfers | "what does the next 30 days look like" |
| `search_documents` | pgvector over the document library | "what does the IRS say about Roth limits" |
| `recall_past_conversation` | pgvector over past chat turns | "like we talked about last time" |
| `remember_about_user` / `recall_about_user` | `user_facts` + embeddings | personal memory |
| `sync_transactions` | `POST /simplefin/sync` logic | "what did I spend today?" — pulls latest bank transactions first |
| `refresh_balances` | `GET /balances/summary?force=true` logic | "what do I have right now?" — live balance refresh |
| `sync_investments` | `POST /snaptrade/sync` logic | refresh brokerage holdings before portfolio advice |
| `schedule_sync` / `list_scheduled_tasks` / `cancel_scheduled_task` | `scheduled_tasks` table + `backend/scheduler.py` | "sync my transactions every week" — recurring background syncs |
| `web_search` | DuckDuckGo via `ddgs` | market news, rate benchmarks, candidate tickers |
| `fetch_webpage` | `url_fetcher` (SSRF-guarded, allowlist off) + `document_extractor` | read one promising search result |
| `get_stock_quote` / `get_stock_history` / `get_stock_fundamentals` | `yfinance` | live prices, trends, PE/yield/analyst targets |

**Scheduler** (`backend/scheduler.py`): an asyncio loop started in the FastAPI lifespan polls `scheduled_tasks` (Alembic `0014`) every 60 s and runs due jobs — the same sync coroutines the endpoints and tools use. Each run records `last_status`/`last_result` on the row and rolls `next_run_at` forward by `interval_days`.

The web + market tools are gated by `ADVISOR_WEB_TOOLS_ENABLED` (default `true`). Set it `false` for offline installs — Fin degrades to DB-grounded answers. The `fetch_webpage` path keeps all of `url_fetcher`'s SSRF defenses (https-only, DNS/private-IP guard, manual redirect re-validation) but skips the host allowlist, with a 2 MiB / 20 s cap; the [Ask → Memory](../tabs/ask-memory.md) import path keeps its allowlist unchanged.

## Guards

The loop terminates safely on every known failure mode for local models:

- **Max iterations** — capped by `ADVISOR_AGENT_MAX_ITERS` (default 10).
- **Empty reply** — Llama / Qwen sometimes return an empty string after a failed tool call; we break instead of looping.
- **Repeated identical tool call** — same fingerprint twice → break (also stops `web_search` retry loops).
- **Transient-error retry** — tools can raise `TransientToolError` (ddgs rate limits, network blips); the harness exempts exactly one retry of that call from the repeated-call guard, then treats it as final.
- **Forced final answer** — if a guard trips with no reply yet, one tool-free LLM call synthesizes an answer from the tool results already gathered instead of returning nothing.
- **Hallucinated tool name** — corrective error fed back to the model, then it can answer without the tool.
- **Invalid arguments** — Pydantic `ValidationError` returned as an error tool-result; one retry, then skip.
- **Per-tool exception** — caught and returned as a tool-error message, never a crash.
- **Per-tool result caps** — tool results are truncated before being fed back (4000 chars default, 8000 for web tools).

## Conversation lifecycle

- New chats get a UUID conversation_id.
- Sidebar lists all conversations; deleting removes the row + its turns.
- Only the last 20 turns are sent per request; older context comes back via `recall_past_conversation` and confirmed user facts.

## Backfill on startup

If Ollama was down when a turn was saved, its embedding is `NULL`. On every backend start, `embed_pending_turns()` and `embed_pending_transactions()` catch up — see `backend/main.py` lifespan handler.

## When Ollama is unreachable

The endpoint returns a clear error; the chat UI shows it inline. Insights and Payoff Advice show a setup nudge card instead of failing.

## Trajectory persistence

Every turn's full reasoning chain (tool calls + arguments + result previews + termination reason) is stored as JSONB on `conversation_turns.trajectory` (Alembic `0009`). Inspect with:

```sql
SELECT trajectory FROM conversation_turns
WHERE trajectory IS NOT NULL
ORDER BY id DESC LIMIT 5;
```

## Testing

| Suite | Path | What it covers |
|---|---|---|
| Harness unit | `backend/tests_unit/test_agent_harness.py` | Every guard path with mocked LLM + tools |
| Tool handlers | `backend/tests_unit/test_agent_tools.py` | Each tool's shape, filters, edge cases |
| Web tools | `backend/tests_unit/test_web_tools.py` | Search shape, fetch limits, allowlist-off |
| Market tools | `backend/tests_unit/test_market_tools.py` | Quote/history/fundamentals with mocked yfinance |
| Schemas | `backend/tests_unit/test_agent_schemas.py` | JSON-schema shape pinned + bounds/enums |
| Router | `backend/tests_unit/test_advisor.py` | Chat + conversation CRUD with mocked agent |
| Trajectory integration | `backend/tests/test_agent_trajectories.py` | Real DB, scripted LLM, asserts on persisted trajectory |
| Eval harness | `backend/tests/test_agent_evals.py` | Table-driven prompt → expected tools + clean-termination checks |
| Fact extraction | `backend/tests/test_fact_reflection.py` | Proposal, dedup (incl. rejected), watermark, malformed JSON |

Live-model smoke testing (real Ollama, real prompts) is intentionally **not** in CI — run it manually after changing prompts or tools.

See also: [Ask → Advisor](../tabs/ask-advisor.md), [Embeddings & RAG](embeddings.md), [Environment variables](../getting-started/env-vars.md).
