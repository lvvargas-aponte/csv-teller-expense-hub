# AI advisor — evals & best practices

> Source: `backend/scripts/fin_live_eval.py`, `backend/tests/test_agent_evals.py`, `backend/agent/`

Fin's agent harness is tested at three levels: unit tests (mocked LLM, every guard path), CI trajectory evals (scripted tool-call sequences against the real test DB), and a **live eval battery** that drives the real stack — running backend, real Ollama, live internet (DuckDuckGo + Yahoo Finance) — through realistic scenarios and grades each turn on the persisted trajectory.

## Running the live battery

```bash
# backend + Ollama must be running
docker compose run --rm backend python -m scripts.fin_live_eval

# keep the eval conversations for inspection (skips cleanup)
docker compose run --rm backend python -m scripts.fin_live_eval --keep

# run a single scenario
docker compose run --rm backend python -m scripts.fin_live_eval -k ticker
```

Each scenario runs in a fresh conversation and is graded on four checks: the expected tool was called, no forbidden tool was called, the reply matches a scenario predicate (e.g. contains a dollar figure, cites a source), and the loop terminated cleanly. Unless `--keep` is passed, eval conversations and any user-facts proposed during the run are deleted afterward so the battery never pollutes Fin's style/fact/RAG corpora.

## Scenario coverage & latest results

Latest full run: **12/12 scenarios pass** (2026-07-12, `qwen2.5:14b-instruct`, 16k context, live internet).

| Scenario | What it proves | Tools observed | Latency |
|---|---|---|---|
| `live_ticker_quote` | Live price from Yahoo, never from memory | `get_stock_quote` | 5–50 s |
| `ticker_history` | 1-year performance with real percentages | `get_stock_history` | ~9 s |
| `web_analysis_with_source` | Web search + page read for analyst views, source cited | `web_search`, `fetch_webpage` | 11–15 s |
| `strategy_synthesis` | Multi-tool chain → opinionated "where should $2k go" answer | `think`, `get_investments`, `get_stock_quote`, `get_stock_fundamentals`, `web_search` | 40–80 s |
| `account_names` | Individual account names + balances, not invented | `list_accounts` | ~5 s |
| `category_aggregate` | Roll-up question routed to the aggregation tool, not similarity search | `get_category_spending` | 5–7 s |
| `continuity_short_reply` | A bare "yes, break that down" is acted on, not questioned | 3× `get_category_spending` | 10–45 s |
| `memory_capture` | "We're buying a house in 2028" reaches the Memory panel | `remember_about_user` **or** promise-fallback extraction | ~2 s + background |
| `action_refresh` | Live bank balance refresh mid-conversation | `refresh_balances` | ~21 s |
| `schedule_awareness` | Reports the weekly background syncs accurately | `list_scheduled_tasks` | ~6 s |
| `bogus_ticker_honesty` | Fake ticker → honest "no data", no hallucinated price | `get_stock_quote` | ~4 s |

!!! note "Local models are stochastic"
    Individual runs vary — the model may choose a different (valid) tool chain, phrase a correct answer differently, or occasionally skip the disclaimer line. Predicates grade *intent* (grounded numbers, honest no-data answers, expected tool families), and a scenario that fails once typically passes on re-run. Systematic failures — a tool never chosen, guard trips, fabricated numbers — are the signal to act on.

The `memory_capture` scenario documents a deliberate harness feature: 14B-class models sometimes *say* "I'll keep that in mind" without calling `remember_about_user`. The router detects that promise in the reply, and when no save occurred it immediately triggers the fact-extraction pass — so the promise holds either way (`routers/advisor.py:_promised_without_saving`).

## Harness best-practices audit

How `agent/harness.py` + the surrounding subsystems map to current (early-2026) agent-design practice:

| Practice | Fin's implementation |
|---|---|
| Bounded loop, explicit termination | `ADVISOR_AGENT_MAX_ITERS` cap; termination reasons `ok` / `empty_reply` / `repeated_tool_call` / `max_iterations` / `ollama_unavailable` recorded per turn |
| Typed tools + argument validation | Pydantic schema per tool; invalid args → corrective error fed back to the model, one retry then skip |
| Hallucinated-tool recovery | Unknown tool name → error listing real tools, model answers without it |
| Parallel tool execution | Independent calls in one iteration run via `asyncio.gather`, results returned in call order |
| Planning scratchpad | `think` tool; prompt directs a numbered plan before multi-step strategy questions |
| Transient vs permanent failures | `TransientToolError` (ddgs rate limits, network blips) exempts exactly one retry from the repeated-call guard |
| Never return nothing | Forced-final fallback: if a guard trips with no reply, one tool-free call synthesizes an answer from gathered results |
| Result size budgets | Per-tool truncation (4 000 chars default, 8 000 for web tools) |
| Streaming + progress | SSE endpoint emits `token` / `tool_call` / `tool_result` events; UI shows live status per tool |
| Full observability | Complete trajectory (calls, args, result previews, termination) persisted as JSONB on every turn |
| Context management | `OLLAMA_NUM_CTX` (16k) requested explicitly — Ollama's 4k default silently truncates the prompt; 20-turn window + rolling conversation summary for older turns |
| Long-term memory, human-in-the-loop | Background fact extraction proposes durable personal facts; user confirms/rejects in the Memory panel before injection |
| Grounding discipline | Hard prompt rules: never invent figures, prices, or account names — call the tool; web-sourced claims cite their source |
| Safety rails | HTTPS-only fetching with DNS/private-IP + redirect guards; `ADVISOR_WEB_TOOLS_ENABLED` kill-switch; action tools are idempotent syncs |
| Evals | Guard-path unit tests, CI trajectory evals (`tests/test_agent_evals.py`), and this live battery |

## Known limitations (honest list)

- **Model ceiling.** Tool selection and disambiguation quality are bounded by the local model (default Qwen 2.5 14B). Occasional wrong-tool picks and over-terse syntheses are model-level, not harness-level; a 20B-class model (`gpt-oss:20b`, `qwen3:14b`) measurably improves them.
- **One transient retry.** A tool that rate-limits twice is abandoned for the turn (by design — prevents retry loops).
- **Deleted conversations linger in RAG.** `DELETE /advisor/conversations/{id}` removes the conversation from the store but its structured turns remain retrievable by `recall_past_conversation`.
- **No self-critique pass.** The harness does not re-check the final answer against tool results before replying; grounding relies on prompt rules plus the trajectory being auditable after the fact.
- **Single-model routing.** All turns use `OLLAMA_CHAT_MODEL`; there is no cheap-model routing for trivial turns.

See also: [AI advisor](advisor.md), [Environment variables](../getting-started/env-vars.md).
