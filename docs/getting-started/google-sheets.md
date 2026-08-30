# Google Sheets (shared-expense export)

> Source: `backend/routers/sheets.py`, `backend/gsheet_integration.py`

Shared transactions can be exported to a Google Sheet via **📊 Send to Sheet** on the Transactions tab.

## One-time setup

1. Open [Google Cloud Console](https://console.cloud.google.com).
2. Create or select a project.
3. Enable the **Google Sheets API**.
4. Create a **Service Account**, generate a JSON key, save it as `backend/credentials.json` (gitignored).
5. Create a Google Sheet with these headers in row 1 (replace placeholders with your `PERSON_1_NAME` / `PERSON_2_NAME`):

   ```
   Transaction Date | Description | Amount | Who | What Alice Owes | What Bob Owes | Notes
   ```

   `Who` is the person who **paid**. Fill only the *other* person's Owes column;
   the payer's cell stays empty. A blank Owes cell means the row has not been
   split yet — it does not mean zero.

6. **Share the sheet** with the `client_email` from `credentials.json` — give it **Editor** access.
7. Copy the Sheet ID from the URL (between `/d/` and `/edit`) into `.env`:

   ```bash
   SPREADSHEET_ID=your_google_sheet_id
   SHEET_NAME=Sheet1   # optional; defaults to first tab
   ```

## Verifying the connection

```bash
curl http://localhost:8000/api/gsheet/verify
```

Returns the sheet title if everything is wired up; otherwise a structured error.

## Person names

`PERSON_1_NAME` and `PERSON_2_NAME` show up as the "What … Owes" column headers in your sheet, and as labels in the Transactions UI when assigning splits. Set them once in `.env`.

`INSTANCE_PERSON_SLOT` says which of the two this installation belongs to. It
defaults to `1`, which is correct for a single household copy. If a second copy
is ever set up for the other person, that one must use `2` — see
[Environment variables](env-vars.md#household).
