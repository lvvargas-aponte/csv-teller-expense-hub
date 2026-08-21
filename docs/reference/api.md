# API endpoints

> Source: `backend/routers/*.py`, `backend/main.py`

All endpoints are mounted under `/api`. The static help site lives at `/help/`. Health check at `/health`.

## Transactions

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/transactions/all` | Full review queue |
| `PUT` | `/api/transactions/{id}` | Update a single transaction |
| `PUT` | `/api/transactions/bulk` | Bulk apply share/category/notes |
| `POST` | `/api/upload-csv` | Multipart CSV upload |
| `POST` | `/api/suggest-categories/bulk` | AI category suggestions for selected rows |

## Category rules

Deterministic auto-categorization applied on CSV upload and bank sync. See [Transactions → Rules](../tabs/transactions-rules.md).

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/category-rules` | List rules in evaluation order |
| `POST` | `/api/category-rules` | Create a rule |
| `PUT` | `/api/category-rules/{id}` | Replace a rule |
| `DELETE` | `/api/category-rules/{id}` | Delete a rule |
| `POST` | `/api/category-rules/apply` | Replay rules over stored transactions (`mode: preview\|apply`) |

## Accounts & balances

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/accounts` | All linked + manual accounts |
| `GET` | `/api/accounts/{id}/transactions` | Transactions for one account |
| `DELETE` | `/api/accounts/{id}` | Disconnect / remove |
| `PUT` | `/api/accounts/{id}/details` | APR / limit / statement metadata |
| `GET` | `/api/accounts/credit-health` | Per-card utilization rollup |
| `GET` | `/api/balances/summary` | Net-worth rollup |
| `POST` | `/api/balances/manual` | Add a manual balance |
| `PUT` | `/api/balances/manual/{id}` | Update a manual balance |
| `DELETE` | `/api/balances/manual/{id}` | Remove a manual balance |

## SimpleFIN

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/simplefin/claim` | Exchange a Setup Token for a durable Access URL |
| `DELETE` | `/api/simplefin/connections` | Drop a stored Access URL (query param `access_url_masked`) |
| `POST` | `/api/simplefin/sync` | Pull transactions for date range + account list |

## SnapTrade (investments sync)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/config/snaptrade` | Whether SnapTrade is configured + whether the household is connected |
| `POST` | `/api/snaptrade/register` | Register the household SnapTrade user (idempotent) |
| `POST` | `/api/snaptrade/connect` | Return a SnapTrade connection-portal URL for a new brokerage link |
| `POST` | `/api/snaptrade/sync` | Pull every connected account's holdings + total value |
| `GET` | `/api/snaptrade/connections` | List connected brokerages |
| `DELETE` | `/api/snaptrade/connections/{id}` | Disconnect one brokerage |

## Investments (read-only)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/investments/holdings` | All holdings grouped by account |
| `GET` | `/api/investments/portfolio` | Totals, unrealized gain, allocation, concentration, by-account breakdown |

## Sheets

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/send-to-gsheet` | Export shared transactions |
| `GET` | `/api/gsheet/verify` | Smoke-test sheet connectivity |
| `GET` | `/api/config/person-names` | Configured person names |

## Advisor

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/advisor/chat` | Send a message; get reply |
| `GET` | `/api/advisor/conversations` | List past conversations |
| `DELETE` | `/api/advisor/conversations/{id}` | Delete a conversation |

## Insights & dashboard

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/insights/spending-summary` | Category breakdown + AI summary |
| `GET` | `/api/insights/forecast` | Next-month forecast |
| `GET` | `/api/dashboard` | Dashboard rollups |
| `GET` | `/api/dashboard/income-vs-expenses` | Trend |
| `GET` | `/api/dashboard/layout` / `PUT` / `DELETE` | Card layout, hidden cards; `DELETE` restores the default |
| `GET` | `/api/alerts` | Flat projection of the coach's rules — see below |
| `GET` | `/api/bills/upcoming` | Recurring charges + due dates |

## Budgets & goals

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/budgets` | List with current-month spend |
| `GET` | `/api/budgets/safe-to-spend` | Today's / this week's discretionary allowance (`?as_of=`) |
| `PUT` | `/api/budgets/{category}` | Upsert |
| `DELETE` | `/api/budgets/{category}` | Remove |
| `GET` | `/api/goals` | List |
| `POST` | `/api/goals` | Create |
| `PUT` | `/api/goals/{id}` | Update |
| `DELETE` | `/api/goals/{id}` | Remove |

## Properties

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/properties` | All properties, each with economics attached |
| `POST` | `/api/properties` | Create (a purchase price + date seeds a valuation) |
| `GET` | `/api/properties/portfolio` | Totals: value, debt, equity, NOI, cash flow, underperformers |
| `GET` | `/api/properties/suggest-transactions` | Proposed property tags for untagged transactions |
| `GET/PUT/DELETE` | `/api/properties/{id}` | Fetch / update / remove one |
| `GET/POST` | `/api/properties/{id}/valuations` | Value history; POST refreshes `current_value` |

## Loans

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/loans` | All loans; `?property_id=` filters to one property |
| `POST` | `/api/loans` | Create |
| `GET/PUT/DELETE` | `/api/loans/{id}` | Fetch / update / remove one |
| `GET` | `/api/loans/{id}/current-payment` | Interest vs. principal for the payment due now |
| `GET` | `/api/loans/{id}/schedule` | Amortization schedule (`from_period`, `limit`; 60 default) |
| `POST` | `/api/loans/{id}/what-if` | Months and interest saved by paying extra |

## Equity & deals

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/equity/capacity` | Borrowing capacity across every property |
| `GET` | `/api/equity/capacity/{id}` | One property; `?max_ltv_pct=` / `?max_cltv_pct=` |
| `POST` | `/api/equity/analyze-deal` | Model a purchase; reports portfolio-level cash-flow delta |

## Retirement

| Method | Path | Purpose |
|---|---|---|
| `GET/PUT` | `/api/retirement/assumptions` | Projection assumptions, merged over defaults |
| `GET` | `/api/retirement/projection` | Year-by-year projection + earliest sustainable year |
| `POST` | `/api/retirement/projection` | What-if against supplied assumptions, not saved |

## Coach

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/coach/actions` | Ranked next actions with amounts and deadlines (`?limit=`, `?as_of=`) |
| `POST` | `/api/coach/narrate` | Optional LLM voice-over; numbers verified against the rules |
| `POST/DELETE` | `/api/coach/actions/{id}/dismiss` | Hide / restore one action |

`GET /api/alerts` is the same rule set flattened to `{severity, category, message, link}`
for the dashboard's Alerts card. One rule set, two presentations — a dismissal
applies to both.

## Tools

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/tools/payoff-plan` | Avalanche / snowball calculator |
| `POST` | `/api/tools/payoff-advice` | AI narrative on the plan |
| `POST` | `/api/tools/allocate` | Where spare money goes: `{amount, cadence}` → ordered split, skipped tiers, questions, caveats |
| `GET/PUT` | `/api/tools/allocation-settings` | Employer match, buffer months, contribution room |

## Documents (RAG)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/documents` | File upload |
| `POST` | `/api/documents/from-url` | Fetch + extract from URL |
| `GET` | `/api/documents` | List |
| `POST` | `/api/documents/{id}/reembed` | Retry embedding |
| `DELETE` | `/api/documents/{id}` | Remove |

## Misc

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/profile` / `PUT` | User settings |
| `GET` | `/api/seeds` / `POST` / `DELETE /{id}` | Category seed data |
| `GET` | `/health` | Liveness probe |
| `GET` | `/` | Root sanity check |
