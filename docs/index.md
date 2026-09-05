# Financial Freedom

**Financial Freedom** is a self-hosted personal finance hub with **Fin**, a local AI financial
advisor. It pulls transactions from your banks (via SimpleFIN) and CSV uploads, tracks balances and
net worth, plans debt payoff, manages budgets, goals and recurring commitments, settles shared
expenses with a partner, and answers questions through a chat agent grounded in your real data —
running entirely on your own machine.

This knowledge base reflects the application **as it is today** — every page links back to the file
paths it documents.

## Who this is for

- **Household members** — you want to know what each page and button does.
- **Self-hosting developers** — you want to fork, configure, and extend the app.
- **The owner** — single source of truth for how everything currently fits together.

## The eight pages

| Page | What lives there |
|---|---|
| [**Home**](tabs/home.md) | Net worth and its composition, the health score, and a ranked **Needs you** feed of what wants a decision today |
| [**Transactions**](tabs/transactions-current.md) | Three views — **Current** (review queue), [**Shared**](tabs/transactions-shared.md) (two-person settle-up), [**History**](tabs/transactions-history.md) (the full record) |
| [**Accounts**](tabs/accounts.md) | What is linked and whether it is healthy; cash, investments, property, and manual accounts |
| [**Debt**](tabs/debt.md) | Cards and loans, utilization, the payoff planner, and borrowing power (debt-to-income) |
| [**Invest**](tabs/invest.md) | Holdings per brokerage, allocation, portfolio quality, fees, and a retirement projection |
| [**Plan**](tabs/plan-budgets.md) | [Budgets](tabs/plan-budgets.md), [Goals](tabs/plan-goals.md), and [Commitments](tabs/plan-commitments.md) — bills, subscriptions and recurring spend |
| [**Ask**](tabs/ask-advisor.md) | [Fin](tabs/ask-advisor.md), the local agent, and [its memory](tabs/ask-memory.md) — your document library |
| [**Settings**](tabs/settings.md) | Financial profile, and categories & rules |

Help and the dark-mode toggle live in the **sidebar footer**, under the health score.

## Under the hood

| Layer | Stack |
|---|---|
| **Backend** | FastAPI (Python 3.11), async SQLAlchemy 2.0 + asyncpg |
| **Store** | Postgres with pgvector |
| **AI** | Local Ollama only — chat, categorisation, and `nomic-embed-text` embeddings. No cloud LLM anywhere. |
| **Frontend** | React 18 (CRA + craco), axios, recharts |
| **Bank sync** | SimpleFIN; SnapTrade for brokerages |

## How to use this site

- **First time?** Start with [Install & Run](getting-started/install.md).
- **Looking for what a button does?** Use **search** (top right), or browse **Pages** / **Modals**.
- **Want to know how something works under the hood?** See **Concepts**.
- **Stuck?** Try [Troubleshooting](reference/troubleshooting.md).
