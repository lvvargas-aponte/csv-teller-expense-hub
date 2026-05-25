# Suggest Categories modal

> Source: `frontend/src/components/transactions/SuggestPreviewModal.js`, `backend/routers/transactions.py`

Title: **Suggest categories**. Opens after clicking **Suggest** in the bulk bar.

## Purpose

Review AI-generated category suggestions for selected transactions before applying them.

## What you see

A table with one row per selected transaction:

| Column | Notes |
|---|---|
| **Description** | Original transaction text |
| **Current category** | What it has now (may be empty) |
| **Suggested** | AI suggestion + confidence indicator |
| **Apply?** | Checkbox; defaults to checked for high-confidence rows |
| **Override** | Free-text field — type your own category instead of accepting the suggestion |

## Submit

Click **Apply** — only the checked rows are written. Unchecked rows keep their existing category.

## When Ollama isn't running

Info text shown: *"Ollama is not running — start it to get suggestions. You can still type categories manually below."* You can still apply manual overrides.

## Under the hood

- `POST /api/suggest-categories/bulk` — returns suggestions
- Apply uses a per-transaction `PUT /api/transactions/{id}` (or a category-batch endpoint)
