# Finances → AI Advisor

> Source: `frontend/src/components/finances/AdvisorChat.js`, `backend/routers/advisor.py`

A multi-turn chat advisor grounded in your real financial data via a **local** Ollama LLM.

## What the advisor sees

Every turn, the backend assembles a context bundle:

- **Last 6 months of transactions** (trimmed for token budget)
- **Live + manual balances** and net worth rollup
- **Active shared splits** (who owes what)
- **Budgets** and current-month progress
- **Goals** and pace status
- **Recurring charges**
- **Document chunks** retrieved from the [Knowledge library](finances-knowledge.md) by semantic similarity to your message

## Conversation persistence

- Conversations are saved to Postgres (`conversations` + `conversation_turns` tables).
- The sidebar lists past chats; you can open or delete any.
- Each turn is also embedded so future turns can retrieve relevant prior context.

## Good questions to ask

- *"How did our dining spending change this month?"*
- *"Are our shared splits fair between the two of us?"*
- *"Can I afford $300 extra toward my credit card debt?"*
- *"What's the most efficient way to fund my emergency goal?"*

## Requirements

Needs Ollama running locally with `OLLAMA_CHAT_MODEL` (default: `qwen2.5:14b-instruct`). See [Ollama setup](../getting-started/ollama.md).

## Under the hood

- `POST /api/advisor/chat` — new turn (returns assistant reply, conversation_id)
- `GET /api/advisor/conversations` — list past chats
- `DELETE /api/advisor/conversations/{id}` — remove

See also: [AI advisor concept](../concepts/advisor.md).
