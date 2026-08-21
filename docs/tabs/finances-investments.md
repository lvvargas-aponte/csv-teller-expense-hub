# Finances → Investments

> Source: `frontend/src/components/finances/InvestmentsTab.js`, `backend/routers/snaptrade.py`, `backend/routers/investments.py`

Every investment account the app knows about, with per-position detail wherever it's available. Brokerage connections are powered by [SnapTrade](../getting-started/snaptrade.md) — see that page for one-time setup — and accounts SnapTrade can't reach (a 401(k) through your employer's plan administrator, a balance on an exchange it doesn't support) sit alongside them as long as they're [added manually](finances-accounts.md) with an investment type or a retirement subtype.

## Summary header

At the top of the tab:

- **Portfolio Value** — every investment account's value: position-level market value where the brokerage reports positions, account totals where it doesn't
- **Unrealized gain/loss** — market value minus cost basis (colored: green positive, red negative), with both the dollar amount and the percentage
- **Cost basis** — total purchase cost across all holdings
- **Balance-only total** — how much of the portfolio value comes from accounts with no position detail. Gain/loss and allocation cover the position-level portion only, since there's nothing to attribute the rest to.

Portfolio Value matches `total_investments` on the [dashboard](finances-dashboard.md) — both count the same set of accounts.

Two action buttons:

- **+ Connect a brokerage** — opens SnapTrade's connection portal in a popup. When you close it, the app syncs automatically.
- **↺ Sync now** — re-pulls every connected account (current prices + any new positions). Visible once you have at least one connection.

A row of chips below lists every connected brokerage. A chip turns red and says `· needs reconnect` when SnapTrade has lost authorization (re-run the connect flow to fix).

## Allocation

A stacked horizontal bar shows the asset-class mix (stocks, ETFs, crypto, options, cash, other) by market value, with a legend underneath. Hover any segment for the exact percentage.

## Holdings tables

One card per account, headed by the account name, institution (e.g. "Robinhood Individual · Robinhood"), and the account's value. SnapTrade-connected accounts also get a **↺ Sync** button that refreshes just that one. Columns:

| Column | Notes |
|---|---|
| Symbol | With a colored asset-type chip and the position's description |
| Qty | Quantity held (fractional for crypto) |
| Avg cost | Average purchase price per unit |
| Price | Current price (bundled with the sync — no separate quote API) |
| Value | `qty × price`, the per-position market value |
| Gain / loss | Unrealized gain in dollars and percent, colored by direction |

Tables are sorted with the largest positions first, and cards with the largest accounts first.

An account with a value but no position table is showing a **balance-only** balance, with a note explaining which case it is:

| Case | What it means |
|---|---|
| Manual account | You typed the balance in — update it from [Accounts](finances-accounts.md). |
| Linked institution | SimpleFIN reports a total for the account but no position breakdown. |
| Freshly connected brokerage | SnapTrade can take ~30 minutes after a new connection to surface positions. Some plan tiers (Personal API keys) never return position detail at all and only ever report the account total. |

## Empty state

- **SnapTrade not configured** — the tab shows a message pointing at `SNAPTRADE_CLIENT_ID` / `SNAPTRADE_CONSUMER_KEY` in `.env`.
- **No accounts yet** — a "No holdings yet" prompt sits below the Connect button.
- **Synced accounts worth $0** — hidden here and in Accounts. Several brokerages hand SnapTrade an auto-created sub-account every customer gets whether or not they ever funded it (Robinhood's separate crypto account is the usual one), and a $0 card for an account you don't use is just noise. Nothing is deleted — the account reappears the moment it reports a balance. See `analytics.is_empty_synced_account`.

## Behind the scenes

- `GET /api/config/snaptrade` — checks whether the integration is configured
- `POST /api/snaptrade/connect` — returns the portal URL for the popup
- `POST /api/snaptrade/sync` — runs after the popup closes (also bound to ↺ Sync now)
- `GET /api/investments/portfolio` — feeds the summary, allocation, and tables
- `GET /api/snaptrade/connections` — drives the chips row

See [API reference](../reference/api.md#snaptrade-investments-sync) for the full surface.

## Net worth + advisor integration

- Account values flow into `total_investments` and `net_worth` on `GET /api/balances/summary` — the dashboard's [Net Worth card](finances-dashboard.md) and the BalancesCard pick them up automatically. `analytics._classify_account_bucket` decides what counts as an investment, so this tab, the dashboard, and the advisor snapshot always agree.
- The advisor sees the full holdings list (capped at the top 30 by value) as the `investments` block in its grounding snapshot. Fin can comment on concentration, allocation vs. your `user_profile.risk_tolerance`, and unrealized-gain candidates for rebalancing or tax-loss harvesting. Fin does **not** have live market data and will not advise on market timing or call individual securities over/undervalued.

See also: [SnapTrade setup](../getting-started/snaptrade.md), [AI advisor](finances-advisor.md), [Data model](../concepts/data-model.md).
