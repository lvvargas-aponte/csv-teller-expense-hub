# Personal Finance Hub

A self-hosted **Personal Finance Hub with an AI Virtual Financial Advisor**. It pulls transactions from your banks (via SimpleFIN) and CSV uploads, tracks balances and net worth, manages budgets and savings goals, plans debt payoff, and includes a chat advisor grounded in your real financial data via a local LLM.

This knowledge base reflects the application **as it is today** — every page links back to the file paths it documents.

## Who this is for

- **Household members** — you want to know what each tab and button does.
- **Self-hosting developers** — you want to fork, configure, and extend the app.
- **The owner** — single source of truth for how everything currently fits together.

## Quick map

| Area | What lives there |
|---|---|
| **Transactions** tab | The review queue: filter, mark shared splits, add notes, bulk-categorize, send to Google Sheets |
| **Finances** tab | 9 sub-sections (Dashboard, Overview, Accounts, Investments, Budgets, Goals, Bills, Knowledge, AI Advisor) |
| **Modals** | Upload CSV, Sync banks, Linked accounts, Add account, Edit/Note/Suggest |
| **Backend** | FastAPI + Postgres (pgvector) + optional local Ollama for AI |

## How to use this site

- **First time?** Start with [Install & Run](getting-started/install.md).
- **Looking for what a button does?** Use **search** (top right), or browse **Tabs & Pages** / **Modals**.
- **Want to know how something works under the hood?** See **Concepts**.
- **Stuck?** Try [Troubleshooting](reference/troubleshooting.md).
