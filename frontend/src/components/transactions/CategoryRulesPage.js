import React, { useCallback, useEffect, useState } from 'react';

import { useCategories } from '../../hooks/useCategories';
import { fmt$ } from '../../utils/formatting';
import { userMessage } from '../../utils/errorMessage';
import {
  applyCategoryRules,
  createCategoryRule,
  deleteCategoryRule,
  listCategoryRules,
  updateCategoryRule,
} from '../../api/categoryRules';

const EMPTY_DRAFT = {
  match: 'description_contains',
  value: '',
  amount: '',
  transaction_type: '',
  category: '',
  enabled: true,
};

const MATCH_LABELS = {
  description_contains: 'Description contains',
  merchant_key: 'Merchant matches',
};

const TYPE_LABELS = {
  debit: 'Money out',
  credit: 'Money in',
};

// Rules are user-authored standing decisions ("the $1,305.93 Zelle is Rent").
// They run on every CSV upload and SimpleFIN sync; this page is where they're
// written, and where they can be replayed over transactions already imported.
export default function CategoryRulesPage() {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  // { changed, matched, changes[], truncated, overwrite } while awaiting confirm.
  const [preview, setPreview] = useState(null);
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState(null);

  const { categories, addLocal: addCategoryLocal } = useCategories();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await listCategoryRules();
      setRules(r.data || []);
    } catch (e) {
      setError(userMessage(e, 'Could not load rules.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const resetForm = () => {
    setDraft(EMPTY_DRAFT);
    setEditingId(null);
  };

  const handleSave = async (e) => {
    e.preventDefault();
    const value = draft.value.trim();
    const category = draft.category.trim();
    if (!value || !category) {
      setError('A rule needs both something to match on and a category.');
      return;
    }
    // '' means "any amount" — only send a number when one was typed, so an
    // empty box doesn't become 0 and match nothing.
    const amount = draft.amount === '' ? null : Number(draft.amount);
    if (amount !== null && !(amount > 0)) {
      setError('Amount must be a positive number, or blank for any amount.');
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const body = {
        match: draft.match,
        value,
        category,
        amount,
        transaction_type: draft.transaction_type || null,
        enabled: draft.enabled,
      };
      if (editingId) {
        await updateCategoryRule(editingId, body);
      } else {
        await createCategoryRule(body);
      }
      addCategoryLocal(category);
      resetForm();
      await load();
    } catch (err) {
      setError(userMessage(err, 'Could not save the rule.'));
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (rule) => {
    setEditingId(rule.id);
    setDraft({
      match: rule.match,
      value: rule.value,
      amount: rule.amount === null || rule.amount === undefined ? '' : String(rule.amount),
      transaction_type: rule.transaction_type || '',
      category: rule.category,
      enabled: rule.enabled !== false,
    });
    setPreview(null);
  };

  const handleDelete = async (rule) => {
    // eslint-disable-next-line no-alert
    const ok = window.confirm(
      `Delete this rule?\n\n${MATCH_LABELS[rule.match]} “${rule.value}” → ${rule.category}\n\n`
      + 'Transactions it already categorized keep their category.'
    );
    if (!ok) return;
    try {
      await deleteCategoryRule(rule.id);
      if (editingId === rule.id) resetForm();
      await load();
    } catch (e) {
      setError(userMessage(e, 'Could not delete the rule.'));
    }
  };

  const handleToggleEnabled = async (rule) => {
    try {
      await updateCategoryRule(rule.id, {
        match: rule.match,
        value: rule.value,
        category: rule.category,
        amount: rule.amount,
        transaction_type: rule.transaction_type,
        enabled: !(rule.enabled !== false),
      });
      await load();
    } catch (e) {
      setError(userMessage(e, 'Could not update the rule.'));
    }
  };

  const runPreview = async (overwrite) => {
    setError(null);
    setApplied(null);
    try {
      const r = await applyCategoryRules({ mode: 'preview', overwrite });
      setPreview({ ...r.data, overwrite });
    } catch (e) {
      setError(userMessage(e, 'Could not check existing transactions.'));
    }
  };

  const confirmApply = async () => {
    setApplying(true);
    try {
      const r = await applyCategoryRules({ mode: 'apply', overwrite: preview.overwrite });
      setApplied(r.data);
      setPreview(null);
    } catch (e) {
      setError(userMessage(e, 'Could not apply the rules.'));
    } finally {
      setApplying(false);
    }
  };

  return (
    <main className="tx-page-wrap">
      <div className="tx-history-header">
        <h2 className="tx-history-title">Category Rules</h2>
        <p className="tx-history-sub">
          Standing decisions about your own money — “this payment is always Rent”.
          Every rule runs automatically on each CSV upload and bank sync, and beats
          whatever category the bank reported. Saving a rule doesn’t touch
          transactions you’ve already imported; use “Apply to existing” for that.
        </p>
      </div>

      {error && (
        <div className="tx-error-banner">
          <span>⚠️ {error}</span>
          <button
            type="button"
            className="tx-error-close"
            aria-label="Dismiss error"
            onClick={() => setError(null)}
          >✕</button>
        </div>
      )}

      <form className="rule-form" onSubmit={handleSave}>
        <div className="rule-form-row">
          <label className="rule-field rule-field--match">
            <span className="rule-field-label">When</span>
            <div className="tx-sel-wrap">
              <select
                value={draft.match}
                onChange={(e) => setDraft({ ...draft, match: e.target.value })}
              >
                <option value="description_contains">Description contains</option>
                <option value="merchant_key">Merchant matches</option>
              </select>
            </div>
          </label>

          <label className="rule-field rule-field--value">
            <span className="rule-field-label">Text</span>
            <input
              type="text"
              value={draft.value}
              placeholder="e.g. Luz Valeria"
              onChange={(e) => setDraft({ ...draft, value: e.target.value })}
            />
          </label>

          <label className="rule-field rule-field--amount">
            <span className="rule-field-label">Amount</span>
            <input
              type="number"
              step="0.01"
              min="0"
              value={draft.amount}
              placeholder="Any"
              onChange={(e) => setDraft({ ...draft, amount: e.target.value })}
            />
          </label>

          <label className="rule-field rule-field--dir">
            <span className="rule-field-label">Direction</span>
            <div className="tx-sel-wrap">
              <select
                value={draft.transaction_type}
                onChange={(e) => setDraft({ ...draft, transaction_type: e.target.value })}
              >
                <option value="">Either</option>
                <option value="debit">Money out</option>
                <option value="credit">Money in</option>
              </select>
            </div>
          </label>

          <label className="rule-field rule-field--cat">
            <span className="rule-field-label">Category</span>
            {/* Datalist rather than CategoryCombobox: the combobox only commits
                on blur/Enter, which is right for inline table edits but wrong
                in a form where the next click is the submit button. Same
                pattern the Suggest Categories modal uses. */}
            <input
              type="text"
              list="rule-category-options"
              value={draft.category}
              placeholder="Select or type…"
              onChange={(e) => setDraft({ ...draft, category: e.target.value })}
            />
            <datalist id="rule-category-options">
              {categories.map((c) => <option key={c} value={c} />)}
            </datalist>
          </label>

          <div className="rule-form-actions">
            <button type="submit" className="tx-btn tx-btn-sheet" disabled={saving}>
              {saving ? 'Saving…' : editingId ? 'Save rule' : '+ Add rule'}
            </button>
            {editingId && (
              <button type="button" className="tx-btn tx-btn-secondary" onClick={resetForm}>
                Cancel
              </button>
            )}
          </div>
        </div>
        <div className="rule-form-hint">
          Leave the amount blank to match any amount. “Merchant matches” ignores
          trailing reference numbers, so one rule keeps working when the bank
          changes them month to month.
        </div>
      </form>

      {applied && (
        <div className="rule-applied">
          ✅ Categorized {applied.changed} transaction{applied.changed === 1 ? '' : 's'}
          {applied.matched > applied.changed
            && ` · ${applied.matched - applied.changed} already matched and were left as-is`}.
        </div>
      )}

      {preview && (
        <div className="rule-preview">
          <div className="rule-preview-head">
            <strong>
              {preview.changed} transaction{preview.changed === 1 ? '' : 's'} would change
            </strong>
            <span className="rule-preview-sub">
              {preview.matched} matched a rule
              {preview.overwrite ? ' · including already-categorized ones' : ''}
            </span>
            <div className="rule-preview-actions">
              <button
                type="button"
                className="tx-btn tx-btn-sheet"
                onClick={confirmApply}
                disabled={applying || preview.changed === 0}
              >
                {applying ? 'Applying…' : `Apply to ${preview.changed}`}
              </button>
              <button
                type="button"
                className="tx-btn tx-btn-secondary"
                onClick={() => setPreview(null)}
              >Cancel</button>
            </div>
          </div>
          {preview.changed > 0 && (
            <ul className="rule-preview-list">
              {preview.changes.map((c) => (
                <li key={c.transaction_id}>
                  <span className="rule-preview-date">{c.date}</span>
                  <span className="rule-preview-desc">{c.description}</span>
                  <span className="rule-preview-amt">{fmt$(c.amount)}</span>
                  <span className="rule-preview-cat">
                    {c.from_category ? `${c.from_category} → ` : ''}{c.to_category}
                  </span>
                </li>
              ))}
              {preview.truncated && (
                <li className="rule-preview-more">
                  …and {preview.changed - preview.changes.length} more
                </li>
              )}
            </ul>
          )}
        </div>
      )}

      <div className="tx-table-card">
        <table className="tx-table">
          <thead>
            <tr>
              <th>Rule</th>
              <th>Amount</th>
              <th>Direction</th>
              <th>Category</th>
              <th>Active</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={6} className="rule-row-empty">Loading…</td></tr>
            )}
            {!loading && rules.length === 0 && (
              <tr>
                <td colSpan={6} className="rule-row-empty">
                  No rules yet. Add one above — for example, description contains
                  “Luz Valeria” for $1,305.93 → Rent.
                </td>
              </tr>
            )}
            {rules.map((rule) => (
              <tr key={rule.id} className={rule.enabled === false ? 'rule-row--off' : undefined}>
                <td>
                  <span className="rule-match-kind">{MATCH_LABELS[rule.match]}</span>{' '}
                  <span className="rule-match-value">“{rule.value}”</span>
                </td>
                <td>{rule.amount === null || rule.amount === undefined ? 'Any' : fmt$(rule.amount)}</td>
                <td>{TYPE_LABELS[rule.transaction_type] || 'Either'}</td>
                <td><span className="rule-cat-pill">{rule.category}</span></td>
                <td>
                  <input
                    type="checkbox"
                    checked={rule.enabled !== false}
                    onChange={() => handleToggleEnabled(rule)}
                    aria-label={`${rule.enabled !== false ? 'Disable' : 'Enable'} this rule`}
                  />
                </td>
                <td className="rule-row-actions">
                  <button type="button" className="tx-btn tx-btn-secondary" onClick={() => handleEdit(rule)}>
                    Edit
                  </button>
                  <button type="button" className="tx-btn tx-btn-secondary" onClick={() => handleDelete(rule)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {rules.length > 0 && (
        <div className="rule-backfill">
          <button type="button" className="tx-btn tx-btn-secondary" onClick={() => runPreview(false)}>
            Apply to existing transactions
          </button>
          <button type="button" className="tx-btn tx-btn-secondary" onClick={() => runPreview(true)}>
            Apply, replacing existing categories
          </button>
          <span className="rule-backfill-hint">
            The first only fills in transactions that have no category yet.
            Both show you what would change before writing anything.
          </span>
        </div>
      )}
    </main>
  );
}
