# Settings

> Source: `frontend/src/components/settings/SettingsPage.js`, `panes/*`, `backend/routers/profile.py`, `backend/routers/category_rules.py`

Reached at `/settings`, or deep-linked to a pane at `/settings/{pane}`. Two panes share one draft:
switching between them never drops an edit, and **Save** commits the whole form at once. Leaving with
unsaved changes warns first.

## Financial profile

What Fin knows about your situation that your transactions cannot tell it. Everything here feeds the
advisor's grounding context and several ratios on [Home](home.md).

| Card | Fields |
|---|---|
| **Risk & horizon** | Risk tolerance (conservative / balanced / aggressive), horizon in years, dependents, monthly take-home |
| **Debt & reserves** | Debt-payoff strategy (avalanche / snowball / minimums only), emergency-fund target (3/6/9/12 months) |
| **Retirement** *(optional)* | Birth year, target retirement age, annual spend in retirement, expected return % |
| **Tax** *(optional)* | Marginal tax rate %, and a **Show after-tax net worth** toggle that adds a second line to Home's hero |
| **Context** *(optional)* | Free-text notes for the advisor |

The emergency-fund target is what the **Runway** reading on Home is measured against; monthly
take-home is the denominator of the debt-to-income ratio on [Debt](debt.md).

Backend: `GET` / `PUT /api/profile`.

## Categories & rules

Two things in one pane:

- **Categories** — the list every transaction picks from, with a count of how many transactions use
  each. Deleting one clears it from every transaction using it.
- **Rules** — "when the description contains *this*, apply *that* category". Matching is a
  case-insensitive **substring** test in list order, first match wins — deliberately not regex, so a
  malformed pattern fails to match rather than raising mid-categorisation. Rules are consulted by
  `categorizer.suggest_category` **before** it reaches for Ollama, so a rule you wrote always beats
  the model's guess and still answers when Ollama is down. They do not retroactively recategorise
  history — use [Transactions → History](transactions-history.md) for that.

Backend: `GET` / `PUT /api/category-rules`, `GET /api/categories`, `DELETE /api/categories/{name}`.

## What is not here

- **Dark mode** and **Help** live in the sidebar footer, not in Settings.
- **Bank and brokerage connections** live on [Accounts](accounts.md).
- **Person names** for shared splits come from environment variables — see
  [Environment variables](../getting-started/env-vars.md).
