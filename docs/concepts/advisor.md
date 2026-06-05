# AI advisor

> Source: `backend/routers/advisor.py`, `backend/llm_client.py`, `backend/embeddings.py`, `backend/db/models.py`, `backend/agent/`

A multi-turn chat advisor (**Fin**) that runs on a **local** Ollama LLM and is grounded in real data. Two execution modes are available, gated by the `ADVISOR_AGENT_MODE` flag.

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

## Agent harness mode (opt-in)

> Source: `backend/agent/{harness,tools,schemas}.py`, `backend/routers/advisor.py`

Set `ADVISOR_AGENT_MODE=true` to swap the single-shot RAG pipeline above for a **bounded tool-use loop**. Instead of stuffing a full financial snapshot into one system prompt, Fin gets a lean "facts header" (net worth, cash, debt, investments) plus a registry of typed tools it can call on demand.

### RAG mode vs agent mode — what actually changes

Same goal (ground Fin in your real data), different strategy for getting that data into the model.

**RAG mode (default):** push everything up front, hope the model uses the right bits.

1. Build a ~50 KB JSON snapshot (balances, 6 mo spending, debts, budgets, goals, recurring charges, income, splits, investments, profile).
2. Run three pgvector searches in parallel (similar past turns, similar transactions, similar documents) and append those.
3. Stuff the pile into the system prompt.
4. **One** call to Ollama. The model is a passive consumer — we decide what it sees before it asks.

**Agent mode (opt-in):** send a tiny header, let the model pull what it needs.

1. Send ~200 bytes: net worth, cash, debt, investments + a tool guide.
2. **Loop** calls to Ollama. Each iteration the model either emits a tool call (e.g. `get_debt(account_name="chase")`) — harness validates, runs the handler, feeds the result back — or emits a final reply and the loop exits.
3. Capped at `ADVISOR_AGENT_MAX_ITERS` (default 6), with guards against hallucinated tools, repeated calls, and empty replies.

The model is an active consumer — it decides what to fetch based on the question.

#### Trade-offs

| | RAG | Agent |
|---|---|---|
| **Prompt size** | Big (everything always) | Tiny header + tool results on demand |
| **Latency** | 1 Ollama call | 2-N Ollama calls (typically 2-3) |
| **Precision** | Model may grab the wrong number from a crowded snapshot | Tool returns exactly the field asked for |
| **Hallucination surface** | Can invent numbers if it skims the snapshot | Must show its work — answers cite `tool_result` payloads |
| **Local-model demand** | Works on 7B models | Needs reliable tool-calling (Qwen 2.5 14B+) |
| **Observability** | Just the reply | Full trajectory: which tools, what args, what came back |
| **Stale data** | Snapshot rebuilt each turn but monolithic | Each tool reads fresh from `state.*` / DB at call time |
| **Cost of "I don't know"** | Snapshot was built whether needed or not | Greeting / chitchat = 1 call, no tool work |

#### Shared plumbing

Both modes share the Fin persona + Wealth Architect prompts, the `chat_ollama` client, conversation persistence, the style-learning loop, and the Ollama-only invariant. Agent-mode tools wrap the **same** analytics functions RAG mode uses to build the snapshot (`_balances_snapshot`, `compute_budget_statuses`, `retrieve_similar_transactions`, etc.) — no parallel pipeline, just a different access pattern.

#### When each wins

- **RAG mode** when your chat model is small (≤8B), Fin gets broad questions ("how am I doing financially"), or you want minimum latency per turn.
- **Agent mode** when Fin gets specific questions ("how much do I owe on Chase", "am I over on dining"), you want to audit *why* Fin said something, or you plan to add tools later (it's the extensible path).

In practice: keep RAG as default until you've upgraded `OLLAMA_CHAT_MODEL` and run the eval suite green, then flip the flag.

### Per-turn pipeline (agent mode)

1. **User sends a message** → `POST /api/advisor/chat`.
2. **Build a lean system prompt** — base persona + facts header + tool guide. No bulk snapshot, no parallel RAG injections.
3. **Run the harness loop** (`agent.harness.run_agent`) up to `ADVISOR_AGENT_MAX_ITERS` iterations:
    - Send messages + tools to Ollama's `/api/chat`.
    - If the model emits `tool_calls`, validate each against its Pydantic schema, execute the handler, feed the result back as a `role: tool` message.
    - If the model emits a final reply, terminate.
4. **Persist the turn** as usual, plus the structured `trajectory` JSONB on `conversation_turns`.

### Tools

| Tool | Wraps | When Fin uses it |
|---|---|---|
| `search_transactions` | `embeddings.retrieve_similar_transactions` + date/category filters | "what was that $300 charge", "find subscription-like hits" |
| `get_balance` | `analytics._balances_snapshot` | "how much cash do I have", "what's my net worth" |
| `get_debt` | balances + `state.account_details` side-car | "how much do I owe on Chase", "show me all my cards" |
| `get_budget_status` | `analytics.compute_budget_statuses` | "am I over on dining" |
| `get_goal_status` | `analytics.compute_goal_statuses` | "am I on pace with my emergency fund" |
| `project_cashflow` | new analytic composing recurring outflow + income estimate + inbound transfers | "what does the next 30 days look like" |

### Guards

The loop terminates safely on every known failure mode for local models:

- **Max iterations** — capped by `ADVISOR_AGENT_MAX_ITERS` (default 6).
- **Empty reply** — Llama / Qwen sometimes return an empty string after a failed tool call; we break instead of looping.
- **Repeated identical tool call** — same fingerprint twice in a row → break.
- **Hallucinated tool name** — corrective error fed back to the model, then it can answer without the tool.
- **Invalid arguments** — Pydantic `ValidationError` returned as an error tool-result; one retry, then skip.
- **Per-tool exception** — caught and returned as a tool-error message so the loop never crashes the request.

### Trajectory persistence

Every agent turn's full reasoning chain (tool calls + arguments + result previews + termination reason) is stored as JSONB on `conversation_turns.trajectory` (Alembic `0009`). Inspect with:

```sql
SELECT trajectory FROM conversation_turns
WHERE trajectory IS NOT NULL
ORDER BY id DESC LIMIT 5;
```

This is the foundation for offline trajectory eval and future UI surfacing of "what tools Fin used to answer this".

### Testing

The agent layer has dedicated coverage that runs in CI:

| Suite | Path | What it covers |
|---|---|---|
| Harness unit | `backend/tests_unit/test_agent_harness.py` | Every guard path with mocked LLM + tools |
| Tool handlers | `backend/tests_unit/test_agent_tools.py` | Each tool's shape, filters, edge cases |
| Schemas | `backend/tests_unit/test_agent_schemas.py` | JSON-schema shape pinned + bounds/enums |
| Router branch | `backend/tests_unit/test_advisor.py` (`TestAgentModeBranch`) | Flag flips path correctly |
| Trajectory integration | `backend/tests/test_agent_trajectories.py` | Real DB, scripted LLM, asserts on persisted trajectory |
| Eval harness | `backend/tests/test_agent_evals.py` | Table-driven prompt → expected tools + clean-termination checks |

Live-model smoke testing (real Ollama, real prompts) is intentionally **not** in CI — run it manually before flipping the flag in your environment.

See also: [AI Advisor tab](../tabs/finances-advisor.md), [Embeddings & RAG](embeddings.md), [Environment variables](../getting-started/env-vars.md).
