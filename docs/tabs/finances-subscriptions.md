# Finances → Subscriptions

> Source: `frontend/src/components/finances/SubscriptionsSection.js`, `backend/routers/subscriptions.py`, `backend/analytics.py`

A review queue for everything that charges you on a repeating cadence. The app detects recurring
charges from your transaction history; this page is the **judgment layer** on top — which ones you've
blessed, which you plan to cancel, and which need another look because they're new or the price moved.

Nothing here is detected from a merchant list or an external service. It's inferred from your own
transactions, so it works for CSV-imported accounts too.

## What you see

| Element | What it does |
|---|---|
| **Active per month** | Total monthly cost of everything you're keeping, normalised across cadences. |
| **Savings once canceled** | What you'd stop paying each month once the charges you marked **Cancel it** actually lapse. |
| **N to review** badge | How many charges are waiting on a decision from you. |
| **Charge rows** | One per detected merchant, review queue first, biggest spend on top within each group. |

Each row shows the merchant, its cadence (and typical interval in days), category, the date it was
last seen, and its estimated cost **per month** — so a yearly renewal and a weekly charge can be
compared directly.

## Badges

| Badge | Meaning |
|---|---|
| **Review** | No decision recorded yet, or the price moved ≥10% since your last decision. |
| **▲ N%** | The latest charge is ≥10% more than what it cost when you last reviewed it. Price creep. |
| **Overlaps** | Two or more active charges share a subscription-ish category (entertainment, streaming, music) — a hint you may be paying for the same thing twice. |
| **Keeping / Canceling / Not a subscription** | Your recorded decision, once it's settled. |

## Deciding

Each unreviewed row offers three buttons:

- **Keep** — counts toward *Active per month*.
- **Cancel it** — moves its cost into *Savings once canceled* and dims the row. This records your
  intent; it does **not** cancel anything with the merchant. You still have to do that yourself.
- **Ignore** — "not a subscription". Hides it from the review queue for good and excludes it from
  overlap detection.

Once decided, the row shows **Undo** to clear the decision and put it back in the queue.

If a reviewed charge's price moves ≥10%, it resurfaces with a **Review** badge and a **Confirm**
button — one click to re-bless it at the new price, which becomes the new baseline.

## How charges are detected

`analytics.detect_recurring_charges()` groups expense transactions by normalised merchant name and
keeps a group when:

- it appears in **at least 2 distinct months**, and
- its amounts stay within **60%** spread of their average.

The spread gate is skipped for categories that are always bills regardless of how much they swing —
utilities, insurance, rent, mortgage, phone, internet.

The gaps between consecutive charges classify the cadence — weekly, every 2 weeks, monthly, every
2 months, quarterly, twice a year, yearly, or irregular — and that's what makes
`estimated_monthly_cost` comparable across rows (an annual renewal contributes 1/12 of its price;
a weekly charge ~4.3×).

**Consequences worth knowing:**

- A brand-new subscription won't appear until it has charged you in two different months.
- Renaming or re-issuing a card can split one subscription into two merchant groups.
- Detection quality improves as categories get filled in — see [Transactions → History](transactions-history.md).

## Related

- Recurring charges also appear as a card on the [Dashboard](finances-dashboard.md).
- Bills with due-date projections live on [Finances → Bills](finances-bills.md), driven by the same detector.

## Under the hood

- List: `GET /api/subscriptions` — detected charges joined with your decisions plus the summary totals
- Record a decision: `POST /api/subscriptions/{merchant_key}/review` with `{"decision": "keep" | "cancel" | "ignore"}`
- Clear a decision: `DELETE /api/subscriptions/{merchant_key}/review`

Decisions persist in the `subscription_reviews` table (Alembic `0011`), keyed by normalised merchant
along with the amount at review time — that stored amount is the baseline the ±10% price check
compares against.
