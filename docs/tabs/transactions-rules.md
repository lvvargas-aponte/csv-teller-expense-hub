# Transactions → Rules

> Source: `frontend/src/components/transactions/CategoryRulesPage.js`, `backend/category_rules.py`, `backend/routers/category_rules.py`

Standing decisions about your own money: *"the $1,305.93 Zelle to my landlord is always Rent."* Write the rule once and every future CSV upload and bank sync applies it automatically.

This is the deterministic counterpart to [Suggest Categories](../modals/suggest-preview.md). The AI suggester guesses once, for the rows you selected, and forgets. A rule is a fact you stated, and it keeps holding.

## What you see

| Element | What it does |
|---|---|
| **Rule form** (top) | Match kind, text, amount, direction, category. Saves a new rule or edits the selected one. |
| **Rules table** | One row per rule, in evaluation order. Toggle **Active**, **Edit**, or **Delete**. |
| **Apply to existing** | Replays the rules over transactions already imported. Previews first. |

## Writing a rule

| Field | Meaning |
|---|---|
| **When** | `Description contains` — plain case-insensitive substring.<br>`Merchant matches` — compares normalized merchant keys, so trailing reference numbers that change month to month don't break the match. |
| **Text** | What to look for, e.g. `Zelle payment to Luz Valeria`. |
| **Amount** | Exact amount, matched to the cent. Leave blank to match any amount. |
| **Direction** | `Money out` (debit), `Money in` (credit), or `Either`. |
| **Category** | What to assign. Pick an existing category or type a new one. |

### Example

To make every $1,305.93 Zelle to a landlord land in Rent:

1. **When** → `Description contains`, **Text** → `Zelle payment to Luz Valeria`
2. **Amount** → `1305.93`, **Direction** → `Money out`
3. **Category** → `Rent`
4. **Add rule**

Pinning the amount is what keeps the rule honest: if the rent changes, the new amount stops matching and the payment shows up uncategorized in your review queue instead of being silently mislabeled.

## Applying to transactions you already have

Saving a rule never touches existing transactions — it would be a nasty surprise to relabel a year of decisions as a side effect of typing in a form. Instead:

- **Apply to existing transactions** — fills in only transactions that have *no* category yet.
- **Apply, replacing existing categories** — also relabels transactions that are already categorized.

Both show a preview (what would change, from which category to which) and write nothing until you confirm.

## How rules are evaluated

Rules are checked most-specific-first:

1. Rules with an amount pinned.
2. Rules without one.

Ties break by creation date, oldest first. This means adding a broad catch-all later (*"any Zelle to this person is a Gift"*) never shadows the precise rule you wrote earlier (*"…except the $1,305.93 one, which is Rent"*).

A rule beats the category your bank reported. SimpleFIN's label is a guess about a merchant; your rule is you saying what the money was for. This matters on re-sync in particular — without it, each month's sync would overwrite the category with the bank's version again.

Rules never change the **reviewed** flag. Categorizing is prep work; the review is still yours to do.

## Under the hood

- List / create / update / delete: `GET|POST /api/category-rules`, `PUT|DELETE /api/category-rules/{id}`
- Backfill: `POST /api/category-rules/apply` with `{"mode": "preview" | "apply", "overwrite": bool}`
- Rules are stored in the `category_rules` JSON store (no migration needed to add a match kind).
- Applied at ingest by `routers/transactions.py` (CSV) and `routers/simplefin.py` (sync).

See also: [CSV ingest](../concepts/csv-ingest.md), [Bank sync](../concepts/bank-sync.md).
