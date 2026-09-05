# Invest

> Source: `frontend/src/components/finances/InvestmentsTab.js`, `PortfolioQuality.js`, `RetirementSection.js`, `backend/routers/investments.py`, `backend/routers/snaptrade.py`, `backend/routers/retirement.py`, `backend/routers/tax.py`

Reached at `/invest`. Per-position view of every stock, ETF, and crypto holding across your
brokerages, plus a read on the portfolio's quality and a retirement projection. Powered by
[SnapTrade](../getting-started/snaptrade.md) — see that page for one-time setup.

## Summary header

At the top of the tab:

- **Portfolio Value** — sum of every position's current market value
- **Unrealized gain/loss** — market value minus cost basis (colored: green positive, red negative), with both the dollar amount and the percentage
- **Cost basis** — total purchase cost across all holdings

Two action buttons:

- **+ Connect a brokerage** — opens SnapTrade's connection portal in a popup. When you close it, the app syncs automatically.
- **↺ Sync now** — re-pulls every connected account (current prices + any new positions). Visible once you have at least one connection.

A row of chips below lists every connected brokerage. A chip turns red and says `· needs reconnect` when SnapTrade has lost authorization (re-run the connect flow to fix).

## Allocation

A stacked horizontal bar shows the asset-class mix (stocks, ETFs, crypto, options, cash, other) by market value, with a legend underneath. Hover any segment for the exact percentage.

## Holdings tables

One table per connected account, headed by the account name and institution (e.g. "Robinhood Individual · Robinhood"). Columns:

| Column | Notes |
|---|---|
| Symbol | With a colored asset-type chip and the position's description |
| Qty | Quantity held (fractional for crypto) |
| Avg cost | Average purchase price per unit |
| Price | Current price (bundled with the sync — no separate quote API) |
| Value | `qty × price`, the per-position market value |
| Gain / loss | Unrealized gain in dollars and percent, colored by direction |

Tables are sorted with the largest positions first.

## Empty state

- **SnapTrade not configured** — the tab shows a message pointing at `SNAPTRADE_CLIENT_ID` / `SNAPTRADE_CONSUMER_KEY` in `.env`.
- **No connections yet** — a "No holdings yet" prompt sits below the Connect button.

## Cost basis

SnapTrade does not always carry a cost basis. Any holding's **Avg cost** cell can be edited by hand;
an overridden figure is marked *"You entered this cost basis"* and the gain/loss column recomputes
from it. Clearing the override returns to whatever the brokerage reports.

Backend: `PUT` / `DELETE /api/investments/holdings/{account_id}/{symbol}/cost-basis`.

## Portfolio quality

Appears once you have holdings. Three readings, each fetched independently so one failing does not
blank the others:

| Reading | What it says | Backend |
|---|---|---|
| **Concentration** | Positions large enough to be a single point of failure | `GET /api/investments/quality` |
| **Allocation drift** | Your actual asset mix against what your **risk tolerance** in [Settings](settings.md) implies, as a bar per class | `GET /api/investments/quality` |
| **Fees** | Weighted expense ratio and the annual dollar cost of your funds' fees | `GET /api/investments/fees` |

A **mix backtest** (`GET /api/investments/backtest`) loads separately — it needs the network, so the
card renders without it.

## Retirement

A projection, leading with the **gap** rather than the headline number. It lives here rather than in
its own route because a projection is a view of the same holdings.

Nothing is guessed for you: if birth year, target retirement age, annual spend or expected return is
missing from [Settings](settings.md), the section names what it needs instead of inventing a default.

**Contribution headroom** renders independently of the projection — it needs no birth year, no return
assumption and no target. It shows, per tax-advantaged account group, how much of this year's limit
you have used. If it detects no contributions at all it says so rather than showing a full bar, since
the over-contribution penalty is real money.

Backend: `GET /api/retirement/projection`, `GET /api/tax/contribution-headroom`.

## Behind the scenes

- `GET /api/config/snaptrade` — checks whether the integration is configured
- `POST /api/snaptrade/connect` — returns the portal URL for the popup
- `POST /api/snaptrade/sync` — runs after the popup closes (also bound to ↺ Sync now)
- `GET /api/investments/portfolio` — feeds the summary, allocation, and tables
- `POST /api/snaptrade/sync/{account_id}` — the per-row **Sync only this account** button
- `GET /api/snaptrade/connections` — drives the chips row

See [API reference](../reference/api.md#investments-snaptrade) for the full surface.

## Net worth + advisor integration

- Synced account values flow into `total_investments` and `net_worth` on `GET /api/balances/summary`,
  so the [Home](home.md) hero and net-worth card pick them up automatically.
- Fin reads your holdings through its `get_investments` tool and can comment on concentration,
  allocation against your risk tolerance, and unrealised-gain candidates for rebalancing or tax-loss
  harvesting. It **does** have market data — `get_stock_quote`, `get_stock_history` and
  `get_stock_fundamentals` reach yfinance — but it still will not advise on market timing.

See also: [SnapTrade setup](../getting-started/snaptrade.md), [Ask → Advisor](ask-advisor.md), [Data model](../concepts/data-model.md).
