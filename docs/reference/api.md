# API endpoints

> Source: `backend/routers/*.py`, `backend/main.py`

Every endpoint is mounted under `/api`. The static help site lives at `/help/`; liveness is `/health`.

## Transactions & categories

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/transactions/all` | Every transaction |
| `PUT` | `/api/transactions/{id}` | Update one transaction |
| `DELETE` | `/api/transactions/{id}` | Delete one transaction |
| `PUT` | `/api/transactions/bulk` | Bulk apply share / category / notes |
| `PUT` | `/api/transactions/bulk/reviewed` | Bulk flip the reviewed flag |
| `PUT` | `/api/transactions/categories` | Bulk recategorize |
| `POST` | `/api/transactions/suggest-categories/bulk` | AI category suggestions for selected rows |
| `POST` | `/api/transactions/dedupe` | Duplicate cleanup — `mode: "preview"` or `"apply"` |
| `POST` | `/api/upload-csv` | Multipart CSV upload |
| `GET` | `/api/categories` | Category list with usage counts |
| `DELETE` | `/api/categories/{name}` | Delete a category and clear it everywhere |
| `GET` `PUT` | `/api/category-rules` | User-authored merchant→category rules (whole-list replace) |

## Accounts & balances

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/accounts` | All linked + manual accounts |
| `GET` | `/api/accounts/metadata` | Subtype vocabulary used for bucketing |
| `DELETE` | `/api/accounts/{id}` | Disconnect / remove |
| `GET` | `/api/accounts/details` | Limit / APR / statement metadata for every account |
| `GET` `PUT` `DELETE` | `/api/accounts/{id}/details` | Per-account metadata |
| `GET` | `/api/balances/summary` | Net-worth rollup, account list, connections |
| `PUT` | `/api/balances/{id}` | Edit a balance |
| `POST` | `/api/balances/manual` | Add a manual account |
| `PUT` `DELETE` | `/api/balances/manual/{id}` | Update / remove a manual account |
| `POST` | `/api/balances/snapshots/refresh` | Recompute the net-worth history |

## Debt & credit

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/accounts/credit-health` | Per-card and overall utilization |
| `GET` | `/api/accounts/borrowing-power` | Debt-to-income plus the payment breakdown |
| `POST` | `/api/tools/payoff-plan` | Avalanche / snowball calculator |
| `POST` | `/api/tools/payoff-advice` | Fin's narrative on the plan |

## Bank sync (SimpleFIN)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/simplefin/claim` | Exchange a Setup Token for a durable Access URL |
| `DELETE` | `/api/simplefin/connections` | Drop a stored Access URL (query param `access_url_masked`) |
| `POST` | `/api/simplefin/sync` | Pull transactions for a date range + account list |

## Investments (SnapTrade)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/config/snaptrade` | Whether SnapTrade is configured and connected |
| `POST` | `/api/snaptrade/register` | Register the household SnapTrade user (idempotent) |
| `POST` | `/api/snaptrade/connect` | Connection-portal URL for a new brokerage link |
| `GET` | `/api/snaptrade/connections` | List connected brokerages |
| `DELETE` | `/api/snaptrade/connections/{authorization_id}` | Disconnect one brokerage |
| `POST` | `/api/snaptrade/sync` | Pull every connected account |
| `POST` | `/api/snaptrade/sync/{account_id}` | Pull one account |

## Investments (read + analysis)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/investments/holdings` | All holdings grouped by account |
| `GET` | `/api/investments/portfolio` | Totals, unrealized gain, allocation, concentration |
| `PUT` `DELETE` | `/api/investments/holdings/{account_id}/{symbol}/cost-basis` | Set / clear a manual cost basis |
| `GET` | `/api/investments/quality` | Concentration flags and allocation drift vs. risk tolerance |
| `GET` | `/api/investments/fees` | Weighted expense ratio and annual fee cost |
| `GET` | `/api/investments/backtest` | Backtest of the current mix (needs the network) |

## Shared expenses (Google Sheets)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/sync/shared-rows` | One period's shared rows, settlement and peer identity |
| `GET` | `/api/sync/status` | Last sync and pending corrections |
| `POST` | `/api/sync/shared` | Push your rows and pull the peer's |
| `POST` `DELETE` | `/api/sync/periods/{period}/ready` | Mark ready / withdraw |
| `POST` `DELETE` | `/api/sync/periods/{period}/paid` | Mark paid / reopen |
| `POST` | `/api/sync/corrections/{id}/acknowledge` | Dismiss a correction |
| `PUT` | `/api/sync/peer-rows/{txn_id}/dispute` | Raise or clear a dispute |
| `POST` | `/api/send-to-gsheet` | One-way export of shared transactions |
| `GET` | `/api/gsheet/verify` | Smoke-test sheet connectivity |
| `GET` | `/api/config/person-names` | Configured person names |

## Advisor (Fin)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/advisor/chat` | One turn, non-streaming |
| `POST` | `/api/advisor/chat/stream` | One turn, streamed with tool events |
| `GET` | `/api/advisor/conversations` | List past chats |
| `GET` | `/api/advisor/conversations/{id}` | One chat's turns |
| `DELETE` | `/api/advisor/conversations/{id}` | Remove a conversation |
| `POST` | `/api/advisor/turns/{turn_id}/feedback` | Thumbs up / down |
| `GET` | `/api/advisor/style-profile` | Fin's read on how you like to be talked to |
| `POST` | `/api/advisor/style-profile/refresh` | Rebuild it |

## Fin's memory

| Method | Path | Purpose |
|---|---|---|
| `GET` `POST` | `/api/user-facts` | Facts Fin has extracted about you |
| `PUT` `DELETE` | `/api/user-facts/{id}` | Edit / remove one |
| `POST` | `/api/user-facts/{id}/confirm` | Confirm a proposed fact |
| `POST` | `/api/user-facts/{id}/reject` | Reject it (kept, but not re-proposed) |
| `POST` | `/api/documents` | File upload |
| `POST` | `/api/documents/from-url` | Fetch + extract from an allowlisted URL |
| `GET` | `/api/documents` | List |
| `GET` | `/api/documents/allowed-hosts` | The URL allowlist |
| `POST` | `/api/documents/{id}/reembed` | Retry embedding |
| `DELETE` | `/api/documents/{id}` | Remove |
| `GET` | `/api/seeds` | Suggested reference material |
| `GET` | `/api/seeds/hidden` | Seeds you dismissed |
| `POST` | `/api/seeds` | Add a seed |
| `DELETE` | `/api/seeds/{id}` | Hide a seed |
| `POST` | `/api/seeds/restore/{default_id}` | Restore a dismissed default |

## Home, insights & alerts

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/dashboard` | Home rollups — cash flow, spending, comparisons |
| `GET` | `/api/dashboard/income-vs-expenses` | Trend |
| `GET` `PUT` `DELETE` | `/api/dashboard/layout` | Card-layout persistence (unused by the current Home) |
| `GET` | `/api/alerts` | Budget / unusual-spend alerts |
| `GET` | `/api/digest/latest` | The weekly digest |
| `POST` | `/api/digest/{id}/read` | Mark it read |
| `POST` | `/api/insights/spending-summary` | Category breakdown + AI summary |
| `GET` | `/api/insights/forecast` | Next-month forecast |
| `GET` | `/api/health/score` | Financial health score with its signals |
| `GET` | `/api/health/ratios` | Emergency-fund runway and related ratios |
| `GET` | `/api/cashflow/projection` | Forward cash-flow projection |

## Commitments

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/subscriptions` | Detected charges + your decisions + summary totals |
| `GET` | `/api/subscriptions/candidates` | Merchants that missed the detection gates |
| `POST` | `/api/subscriptions/{merchant_key}/review` | Record a decision, `declared_cadence`, `declared_type` |
| `DELETE` | `/api/subscriptions/{merchant_key}/review` | Clear a decision |
| `POST` | `/api/subscriptions/{merchant_key}/merge` | Fold this merchant into another |
| `DELETE` | `/api/subscriptions/{merchant_key}/merge` | Undo a merge |
| `GET` | `/api/bills/upcoming` | Upcoming bills with projected due dates |

## Budgets & goals

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/budgets` | List with current-month spend |
| `PUT` | `/api/budgets/{category}` | Upsert a limit |
| `DELETE` | `/api/budgets/{category}` | Remove |
| `GET` | `/api/goals` | List with pace status |
| `POST` | `/api/goals` | Create |
| `PUT` `DELETE` | `/api/goals/{id}` | Update / remove |

## Retirement & tax

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/retirement/projection` | Projection, leading with the gap |
| `GET` | `/api/tax/after-tax-net-worth` | Net worth after the embedded tax liability |
| `GET` | `/api/tax/contribution-headroom` | Remaining room in tax-advantaged accounts |

## Profile & identity

| Method | Path | Purpose |
|---|---|---|
| `GET` `PUT` | `/api/profile` | Financial profile — risk, horizon, income, targets |
| `GET` `PUT` | `/api/identity` | Who this install is, for shared-expense sync |

## Misc

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness probe |
| `GET` | `/` | Root sanity check |
