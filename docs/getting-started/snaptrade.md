# SnapTrade (investments sync)

> Source: `backend/routers/snaptrade.py`, `backend/snaptrade.py`, `frontend/src/components/finances/InvestmentsTab.js`

[SnapTrade](https://snaptrade.com) provides the brokerage connection used by the **Investments** tab. It aggregates accounts and positions from Robinhood (stocks + crypto), M1 Finance, E-trade, Schwab, Fidelity, and 20+ other brokers — neither Teller nor plain bank APIs surface this data.

## One-time setup

1. Sign up at [SnapTrade](https://snaptrade.com) and create an application in the dashboard.
2. Copy the two credentials into `.env`:
   ```bash
   SNAPTRADE_CLIENT_ID=your_client_id
   SNAPTRADE_CONSUMER_KEY=your_consumer_key
   ```
3. Restart the backend. The Investments tab will detect the keys and enable the "Connect a brokerage" button.

SnapTrade has **no sandbox/production switch** — these two credentials are the entire auth surface. To test against simulated data, connect a paper-trading broker (e.g. Alpaca Paper) through the same flow.

## Connecting a brokerage

1. Open **Finances → Investments**.
2. Click **+ Connect a brokerage**. The app opens SnapTrade's connection portal in a popup.
3. Pick your brokerage, sign in with the broker's credentials, authorize SnapTrade.
4. Close the popup. The app detects the close, runs a sync, and your holdings appear in the holdings tables grouped by account.

You can connect more than one brokerage — repeat the flow.

## How credentials are stored

On first connect the app registers a household-level SnapTrade `userId` + `userSecret` and persists them in Postgres (`json_stores` row `snaptrade_creds`/`household`). They are **never written to `.env`**.

To revoke, delete the row directly in Postgres or use `DELETE /api/snaptrade/connections/{id}` to remove individual brokerage links. See the [API reference](../reference/api.md#snaptrade-investments-sync).

## What gets pulled per sync

For each connected account, one call to `GET all user holdings`:

- The account itself (upserted into the `accounts` table with `source='snaptrade'`, `type='investment'`)
- Every position (replaces the account's rows in the `holdings` table — sold positions disappear)
- Account total value (appended to `balance_snapshots` so net-worth history includes it)

The current price is bundled with each position — there is no separate quote API to call.

## What it's used for

- The **Investments** tab — holdings table grouped by account, allocation breakdown, unrealized gain/loss.
- The dashboard **PortfolioCard** — total value, allocation, top positions.
- Net worth (`/api/balances/summary`) — investment account values are added to `total_investments` and `net_worth`.
- The **AI advisor** — Fin sees the `investments` block in its grounding snapshot (per-holding cost basis, allocation, concentration) and can advise on structural fit with your risk tolerance and time horizon. Fin does **not** have live market prices or news — see [AI advisor](../tabs/finances-advisor.md).

See also: [Investments tab](../tabs/finances-investments.md), [Data model](../concepts/data-model.md).
