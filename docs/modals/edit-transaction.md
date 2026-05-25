# Edit Transaction modal

> Source: `frontend/src/components/transactions/EditModal.js`, `backend/routers/transactions.py`

A full editor for a single transaction. Opens from a row's edit action.

## Fields

| Field | Notes |
|---|---|
| **Description** | Read-only; shown as the modal title |
| **Category** | Free text or pick from suggestions |
| **Shared (½)** | Toggle. When on, who-paid / what-for / per-person owed amounts become editable |
| **Who paid** | One of the two configured person names |
| **What for** | Free text label (e.g., "Groceries", "Rent") |
| **Person 1 owes / Person 2 owes** | Numeric. Use **50/50** quick button for an even split |
| **Notes** | Free text; same field as the inline note |

## Inline alternatives

For most edits you don't need this modal — the row itself supports:

- The **½ / P** pill (toggle shared)
- **🧮** for inline split adjustment
- **🗒️** for inline notes

The full modal is for cases where you want to edit several fields at once.

## Under the hood

- `PUT /api/transactions/{id}` — payload covers all fields above.
