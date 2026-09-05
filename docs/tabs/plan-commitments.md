# Plan → Commitments

> Source: `frontend/src/components/finances/SubscriptionsSection.js`, `cards/UpcomingBillsCard.js`, `cards/RecurringChargesCard.js`, `backend/routers/subscriptions.py`, `backend/routers/bills.py`, `backend/analytics.py`

Everything that charges you on a repeat. This one page replaced the old separate **Bills** and
**Subscriptions** tabs — there are three kinds of repeat, so there are three sections, but they all
come from one detector.

Nothing here comes from a merchant list or an external service. It is inferred from your own
transactions, so it works for CSV-imported accounts too.

## The three sections

| Section | What lands here | `commitment_type` |
|---|---|---|
| **Upcoming bills** | What is owed soon — credit-card statement and due dates, plus detected bills with a projected next date | `bill` |
| **Subscriptions** | The review queue: what renews, and what you have decided about it | `subscription` |
| **Recurring spend** | Everything else that merely recurs — the merchant you hit every month without it being a subscription | `recurring_spend` |

`analytics._classify_commitment()` decides which list a merchant lands in. Category wins when you
have set one; otherwise the description decides, which is what keeps an uncategorised mortgage out of
the subscriptions list. Card payments and transfers are dropped entirely.

## Subscriptions review queue

| Element | What it does |
|---|---|
| **Active per month** | Monthly cost of everything you are keeping, normalised across cadences. |
| **Savings once canceled** | What you would stop paying each month once the charges you marked **Cancel it** actually lapse. |
| **N to review** badge | How many charges are waiting on a decision. |
| **Charge rows** | One per detected merchant — review queue first, biggest spend on top within each group. |

Each row shows the merchant, its cadence (and the typical interval in days), category, when it was
last seen, and its estimated cost **per month** — so a yearly renewal and a weekly charge can be
compared directly. A cadence you set yourself is labelled *(you set this)*.

### Badges

| Badge | Meaning |
|---|---|
| **Review** | No decision recorded yet, or the price moved ≥10% since your last decision. |
| **▲ N%** | The latest charge is ≥10% above what it cost when you last reviewed it. Price creep. |
| **Overlaps** | Two or more active charges share a subscription-ish category (entertainment, streaming, music) — a hint you may be paying twice for the same thing. |
| **Keeping / Canceling / Not a subscription** | Your recorded decision. |

### Deciding

- **Keep** — counts toward *Active per month*.
- **Cancel it** — moves its cost into *Savings once canceled* and dims the row. This records your
  intent; it does **not** cancel anything with the merchant. You still have to do that yourself.
- **Ignore** — "not a subscription". Leaves the queue for good and stops counting toward overlaps.

Once decided, the row offers **Undo**. If a reviewed charge's price moves ≥10% it resurfaces with a
**Review** badge and a **Confirm** button — one click re-blesses it at the new price, which becomes
the new baseline.

## When the detector cannot settle it, it asks

Two questions appear inline on a row rather than the app guessing and being wrong in silence:

- **"No steady pattern here. How often is this billed?"** — when the gaps between charges fit no
  cadence band. Pick a frequency, or say **One-time thing**.
- **"Nothing since \<date\>. Is this still active?"** — when a charge has gone quiet. Answer, or say
  **It ended**.

Your answer is stored as `declared_cadence` / `declared_type` (Alembic `0029`) and **overrides the
inference everywhere** — the monthly-cost normalisation and the staleness check both read the
declared value first, and the question is never asked again. A declared cadence also lifts every
detection gate for that merchant: you have already settled it.

## Merging split merchants

A merchant that renames itself (*Google FIBER* → *GFiber*) or varies its own suffix forks into two
merchant keys, so one commitment reads as two — each with half the history, and neither with enough
to look recurring.

**Merge into** on a row folds it into another merchant. A merged row shows *Includes N merged names*
and lists them; the merge can be undone. Mapping is stored in `merchant_aliases` (Alembic `0030`) and
is deliberately **user-declared** — automatic fuzzy matching merges things that merely look alike.

## Adding one the detector missed

**+ Add a commitment we missed** lists merchants that appear in your transactions but did not clear
the detection gates. Pick one, say how often it bills and what kind it is, and it becomes a
commitment. This is the only way in for a charge invisible to the detector — invisible means it could
never be declared either.

Backend: `GET /api/subscriptions/candidates`.

## How charges are detected

`analytics.detect_recurring_charges()` groups expense transactions by normalised merchant name
(after applying your merges) and keeps a group when:

- it appears in **at least 2 distinct months**, and
- its amounts stay within a **60%** spread of their average.

The spread gate is skipped for categories that are always bills regardless of how much they swing —
utilities, insurance, rent, mortgage, phone, internet.

A merchant with **no category and no bill-shaped description** faces stricter gates, because two
grocery runs in two months look exactly like a subscription otherwise. It needs a recognised cadence,
**3** months of history, and amounts inside a **35%** spread.

The gaps between consecutive charges classify the cadence — weekly, every 2 weeks, monthly, every
2 months, quarterly, twice a year, yearly, or irregular — and that is what makes
`estimated_monthly_cost` comparable across rows (an annual renewal contributes 1/12 of its price; a
weekly charge ~4.3×).

**Consequences worth knowing:**

- A brand-new subscription will not appear until it has charged you in two different months (three,
  if it is uncategorised).
- Re-issuing a card can split one subscription into two merchant groups — use **Merge into**.
- Detection quality improves as categories get filled in — see
  [Transactions → History](transactions-history.md).

## Under the hood

- `GET /api/subscriptions` — detected charges joined with your decisions, plus the summary totals
- `GET /api/subscriptions/candidates` — merchants that missed the gates, for the add form
- `POST /api/subscriptions/{merchant_key}/review` — `{"decision": "keep" | "cancel" | "ignore", "declared_cadence": …, "declared_type": …}`
- `DELETE /api/subscriptions/{merchant_key}/review` — clear a decision
- `POST /api/subscriptions/{merchant_key}/merge` — fold this merchant into another
- `DELETE /api/subscriptions/{merchant_key}/merge` — undo a merge
- `GET /api/bills/upcoming` — the Upcoming bills section

Decisions persist in `subscription_reviews` (Alembic `0011`, extended by `0029`), keyed by normalised
merchant along with the amount at review time — that stored amount is the baseline the ±10% price
check compares against. Merges live in `merchant_aliases` (Alembic `0030`).

## Related

- Upcoming bills also appear as a card on [Home](home.md).
