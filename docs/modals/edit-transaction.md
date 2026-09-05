# Transaction detail

> Source: `frontend/src/components/transactions/TransactionDetailRow.js`, `backend/routers/transactions.py`

The full editor for a single transaction. It is **not** a modal — it expands inline as a
full-width row directly beneath the transaction you clicked, so the rest of the table stays
visible. Available on both **Transactions** and **Historical transactions**.

## Opening and closing

- Click anywhere on a row (outside the checkbox, category cell, or action buttons) to expand it.
- **Collapse** closes it. Clicking a different row moves the editor to that row.
- Opening another row **discards unsaved edits** — save first if you want to keep them.

## Fields

| Field | Notes |
|---|---|
| **Category** | Combobox — type to filter, pick an existing category, or enter a new one. Existing categories can be removed from the list here. |
| **Split** | `Personal` / `Shared` toggle. Choosing Shared reveals the four fields below. |
| **Who paid** | Free text; defaults to the configured person names. |
| **What for** | Free text label (e.g., "Groceries", "Rent"). |
| **⟨Person 1⟩ owes / ⟨Person 2⟩ owes** | Numeric. The **50/50** button between them fills in an even split. |
| **Type** | `Debit` / `Credit` toggle. |
| **Reviewed** | Switch — marks the row done without changing anything else. |
| **Notes** | Free text; the same field as the inline 🗒️ note editor. |

Switching **Split** back to `Personal` clears who / what / both owed amounts on save.

## Source record

A read-only panel showing where the row came from: posted date, institution, account type,
source channel, direction, transfer target, account ID, and transaction ID. Fields that are
empty for a given transaction are hidden.

## Saving

Edits go to a local draft. While the draft differs from what's stored you'll see **Unsaved
changes**, plus:

- **Save** — commits every field at once.
- **Cancel** — reverts the draft, leaves the row open.
- **Delete** — removes the transaction.

While a row is expanded, the [supporting rail](../tabs/transactions-current.md#supporting-rail) offers
**Apply to similar**, which pushes the draft's category and shared flag to every other
transaction from the same merchant.

## Inline alternatives

For quick single-field edits you don't need to expand the row at all:

- The **½ / P** pill (toggle shared)
- **🧮** for inline split adjustment
- **🗒️** for inline notes

## Under the hood

- `PUT /api/transactions/{id}` — payload covers all fields above.
