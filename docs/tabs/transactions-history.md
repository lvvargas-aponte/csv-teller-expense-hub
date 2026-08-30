# Transactions → History

> Source: `frontend/src/components/transactions/HistoryPage.js`, `backend/routers/transactions.py`

Reached from **Transactions → History** in the sidebar (🕓). Where [Current](transactions.md)
is a review queue for what just came in, History is the full record — every transaction ever
synced or uploaded, regardless of reviewed state — for cleaning up categories after the fact.

It reuses the same filter bar, table, detail editor, and
[supporting rail](transactions.md#supporting-rail) as Current.

## What you see

| Element | What it does |
|---|---|
| **Find duplicates** (header) | Scans the whole history for duplicate transactions. See [below](#find-duplicates). |
| **Filter bar** | Bank, month, split-type, **category**, and search. Shows visible/total count. |
| **Bulk bar** (only when rows selected) | **Suggest categories**, **Mark unreviewed**, **Clear selection**. |
| **Transaction table** | Same rows as Current, but the category cell is **directly editable** without expanding the row. |
| **Supporting rail** | Review progress, shared total, category breakdown, and Apply to similar. Figures reflect the current filters. |

## How it differs from Current

- **No sync panel, no CSV upload, no Send to Sheet** — History is for correcting records, not ingesting or reporting them.
- **Category filter** — the filter bar has an extra category dropdown.
- **Inline category editing** — click the category cell on any row and type; a new name is added to the category list, an existing one can be removed via the ⋯ menu. Editing a category deliberately does **not** flip the row's reviewed flag.
- **Mark unreviewed in bulk** — instead of "mark personal / 50-50", the bulk bar lets you push rows back into the review queue.

## Common workflows

### Recategorize past transactions

1. Filter to the month or merchant you're cleaning up.
2. Click the category cell on a row and type the new name, or pick an existing one.
3. Changes save on the spot.

### Get AI-suggested categories

1. Select rows.
2. Click **✨ Suggest** → the [Suggest Categories preview modal](../modals/suggest-preview.md) opens.
3. Review per-row suggestions and apply.

### Edit everything about one transaction

Click the row to expand the [transaction detail editor](../modals/edit-transaction.md) beneath it.

### Send rows back to the review queue

1. Select them.
2. **Mark unreviewed** in the bulk bar — they reappear as unreviewed on Current.

### Remove a category everywhere

Use the ⋯ menu next to a category name in the combobox. The category is deleted and cleared from
every transaction using it, then the table reloads.

## Find duplicates

CSV re-uploads and overlapping bank syncs can leave the same transaction in twice.
**⎘ Find duplicates** runs a two-step, confirm-before-delete cleanup:

1. A **preview** pass reports how many duplicates were found and across how many groups.
2. If you confirm, the **apply** pass keeps the reviewed/categorized copy in each group and
   removes the rest, then reports how many rows were deleted.

Nothing is deleted without the confirmation prompt.

## Under the hood

- Transactions endpoint: `GET /api/transactions/all`
- Single edit: `PUT /api/transactions/{id}`
- Bulk reviewed flag: `PUT /api/transactions/bulk/reviewed`
- Bulk suggest: `POST /api/suggest-categories/bulk`
- Duplicate preview / apply: `POST /api/transactions/dedupe` with `mode: "preview"` or `"apply"`
