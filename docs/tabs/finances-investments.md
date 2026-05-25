# Finances → Investments

> Source: `frontend/src/components/finances/InvestmentsTab.js`, `backend/routers/snaptrade.py`, `backend/routers/investments.py`

Per-position view of every stock, ETF, and crypto holding across your brokerages. Powered by [SnapTrade](../getting-started/snaptrade.md) — see that page for one-time setup.

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

## Behind the scenes

- `GET /api/config/snaptrade` — checks whether the integration is configured
- `POST /api/snaptrade/connect` — returns the portal URL for the popup
- `POST /api/snaptrade/sync` — runs after the popup closes (also bound to ↺ Sync now)
- `GET /api/investments/portfolio` — feeds the summary, allocation, and tables
- `GET /api/snaptrade/connections` — drives the chips row

See [API reference](../reference/api.md#snaptrade-investments-sync) for the full surface.

## Net worth + advisor integration

- Synced account values flow into `total_investments` and `net_worth` on `GET /api/balances/summary` — the dashboard's [Net Worth card](finances-dashboard.md) and the BalancesCard pick them up automatically.
- The advisor sees the full holdings list (capped at the top 30 by value) as the `investments` block in its grounding snapshot. Fin can comment on concentration, allocation vs. your `user_profile.risk_tolerance`, and unrealized-gain candidates for rebalancing or tax-loss harvesting. Fin does **not** have live market data and will not advise on market timing or call individual securities over/undervalued.

See also: [SnapTrade setup](../getting-started/snaptrade.md), [AI advisor](finances-advisor.md), [Data model](../concepts/data-model.md).
