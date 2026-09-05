# Ask → Advisor

> Source: `frontend/src/components/finances/AdvisorChat.js`, `AdvisorMemory.js`, `backend/routers/advisor.py`, `backend/agent/*`

**Fin** — a multi-turn chat advisor grounded in your real financial data, running entirely on a
**local** Ollama model. Nothing leaves the machine except what you explicitly ask Fin to look up on
the web.

## How Fin answers

Fin is an **agent**, not a retrieval-and-answer bot. Rather than being handed a fixed context bundle,
it calls tools in a loop until it has what it needs, then answers. The reply **streams** as it is
generated, and while Fin is working the UI narrates which tool is running — *Searching your
transactions…*, *Checking live prices…*, *Noting that down…*.

### Tools available to Fin

| Group | Tools |
|---|---|
| **Reasoning** | `think` |
| **Your money** | `search_transactions`, `get_balance`, `list_accounts`, `get_debt`, `get_budget_status`, `get_goal_status`, `get_category_spending`, `get_investments`, `project_cashflow` |
| **Your memory** | `search_documents`, `recall_past_conversation`, `remember_about_user`, `recall_about_user` |
| **Actions** | `sync_transactions`, `refresh_balances`, `sync_investments`, `schedule_sync`, `list_scheduled_tasks`, `cancel_scheduled_task` |
| **Web** | `web_search`, `fetch_webpage` |
| **Market** | `get_stock_quote`, `get_stock_history`, `get_stock_fundamentals` |

The action tools mean Fin can *do* things, not just report — "sync my bank and tell me what changed"
is a single request. Web and market tools are the one place data leaves the machine.

Sources: `backend/agent/tools.py`, `action_tools.py`, `web_tools.py`, `market_tools.py`. The loop
itself is `backend/agent/harness.py`, which forces a final answer if the model keeps calling tools
past its budget.

## What Fin remembers

Three separate stores, all local:

| Store | What it holds |
|---|---|
| **Conversations** | Every past chat, in the left rail. Open or delete any. Each turn is embedded so `recall_past_conversation` can retrieve it later. |
| **Facts about you** | Things Fin extracted proactively from your messages — "getting married in the spring", "hates budgeting apps". Listed below the messages. |
| **Documents** | The library on [Ask → Memory](ask-memory.md), searched by `search_documents`. |

### Reviewing facts

Fin proposes facts; you rule on them. Each row offers **Confirm**, **Reject**, **Edit**, mark
**sensitive**, or delete. A rejected fact is kept but dimmed, so Fin does not re-propose it.

Backend: `GET`/`POST`/`PUT`/`DELETE /api/user-facts`, plus `/confirm` and `/reject`.

## Feedback and style

- **👍 / 👎** on any of Fin's messages (`POST /api/advisor/turns/{turn_id}/feedback`).
- **"Fin's read on you"** — a collapsible panel below the chat holding the style profile Fin maintains about how you
  like to be talked to, built from your feedback and past turns. It can be refreshed on demand.

Backend: `GET /api/advisor/style-profile`, `POST /api/advisor/style-profile/refresh`.

## Good questions to ask

- *"How did our dining spending change this month?"*
- *"Are our shared splits fair between the two of us?"*
- *"Can I afford $300 extra toward my credit card debt?"*
- *"Where is our biggest opportunity to save next month?"*

## Requirements

Ollama running locally with `OLLAMA_CHAT_MODEL` set — see [Ollama setup](../getting-started/ollama.md).
The model must support tool calling; without it Fin cannot work. When Ollama is unreachable the chat
says so rather than degrading silently.

## Under the hood

- `POST /api/advisor/chat` — one turn, non-streaming
- `POST /api/advisor/chat/stream` — one turn, streamed with tool events (what the UI uses)
- `GET /api/advisor/conversations` — list past chats
- `GET /api/advisor/conversations/{id}` — one chat's turns
- `DELETE /api/advisor/conversations/{id}` — remove
- `POST /api/advisor/turns/{id}/feedback` — thumbs
- `GET` / `POST /api/advisor/style-profile[/refresh]`

See also: [AI advisor concept](../concepts/advisor.md), [Advisor evals](../concepts/advisor-evals.md),
[Embeddings & RAG](../concepts/embeddings.md).
