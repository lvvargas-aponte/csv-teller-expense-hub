# Note modal

> Source: `frontend/src/components/transactions/NoteModal.js`, `frontend/src/components/transactions/NoteExpandRow.js`

Add or edit free-text notes on a transaction.

## Two surfaces

- **Inline expand** (`NoteExpandRow.js`) — the default; opens below the row when you click **🗒️**.
- **Modal** (`NoteModal.js`) — used in some flows (legacy paths) for the same purpose.

## Behavior

- Existing note text is pre-filled.
- **Save** persists immediately and changes the row icon from 🗒️ → 📝.
- **Cancel** closes without saving.

## Under the hood

- `PUT /api/transactions/{id}` with `notes: "..."`.

The note is also exported to the Google Sheet's **Notes** column when the transaction is shared.
