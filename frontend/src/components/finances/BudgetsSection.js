import React, { useState, useEffect, useCallback } from 'react';
import Spin from '../ui/Spin';
import { fmt$ } from '../../utils/formatting';
import { listBudgets, upsertBudget, deleteBudget } from '../../api/budgets';

export default function BudgetsSection() {
  const [budgets, setBudgets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [draft, setDraft] = useState({ category: '', monthly_limit: '', notes: '' });
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    listBudgets()
      .then((r) => setBudgets(r.data))
      .catch(() => setError('Could not load budgets — is the backend running?'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSave = useCallback(async () => {
    if (!draft.category.trim()) return;
    setSaving(true);
    try {
      await upsertBudget(draft.category.trim(), {
        category:      draft.category.trim(),
        monthly_limit: parseFloat(draft.monthly_limit) || 0,
        notes:         draft.notes,
      });
      setDraft({ category: '', monthly_limit: '', notes: '' });
      setShowForm(false);
      load();
    } catch {
      setError('Could not save budget.');
    } finally {
      setSaving(false);
    }
  }, [draft, load]);

  const handleDelete = useCallback(async (category) => {
    try {
      await deleteBudget(category);
      load();
    } catch { /* silent */ }
  }, [load]);

  return (
    <div className="finances-section">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 className="finances-section-title" style={{ margin: 0 }}>Monthly Budgets</h2>
        <button type="button" className="btn btn-secondary btn-sm"
                onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ Add Budget'}
        </button>
      </div>

      {showForm && (
        <div className="manual-acct-form">
          <div className="form-row-2">
            <div className="field-group">
              <label className="field-label">Category</label>
              <input className="form-input" type="text" placeholder="e.g. Dining"
                     value={draft.category}
                     onChange={(e) => setDraft((d) => ({ ...d, category: e.target.value }))} />
            </div>
            <div className="field-group">
              <label className="field-label">Monthly Limit ($)</label>
              <input className="form-input" type="number" min="0" step="0.01" placeholder="0.00"
                     value={draft.monthly_limit}
                     onChange={(e) => setDraft((d) => ({ ...d, monthly_limit: e.target.value }))} />
            </div>
          </div>
          <div className="form-row-2">
            <div className="field-group" style={{ gridColumn: '1 / -1' }}>
              <label className="field-label">Notes (optional)</label>
              <input className="form-input" type="text"
                     value={draft.notes}
                     onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))} />
            </div>
          </div>
          <div style={{ marginTop: 8 }}>
            <button type="button" className="btn btn-primary"
                    onClick={handleSave}
                    disabled={saving || !draft.category.trim()}>
              {saving ? <><Spin /> Saving…</> : 'Save Budget'}
            </button>
          </div>
        </div>
      )}

      {loading && <div style={{ textAlign: 'center', padding: '20px 0' }}><Spin /> Loading…</div>}
      {error && <div style={{ color: '#f87171', fontSize: 14 }}>{error}</div>}

      {!loading && !error && budgets.length === 0 && (
        <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>
          No budgets yet — add one to track monthly category spending.
        </div>
      )}

      {!loading && budgets.map((b) => (
        <BudgetRow key={b.category} budget={b} onDelete={() => handleDelete(b.category)} />
      ))}
    </div>
  );
}

function BudgetRow({ budget, onDelete }) {
  const pct = Math.min(budget.percent_used, 100);
  const overflow = Math.max(budget.percent_used - 100, 0);
  const barColor = budget.over_budget ? '#f87171' : (budget.percent_used > 80 ? '#fbbf24' : '#10b981');

  return (
    <div className="balance-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div className="balance-row-name">{budget.category}</div>
          {budget.notes && <div className="balance-row-inst">{budget.notes}</div>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ textAlign: 'right' }}>
            <div className="balance-available">
              {fmt$(budget.current_month_spent)}
              <span style={{ fontSize: 11, opacity: 0.6, marginLeft: 4 }}>
                / {fmt$(budget.monthly_limit)}
              </span>
            </div>
            <div style={{ fontSize: 12, color: budget.over_budget ? '#f87171' : 'var(--text-muted)' }}>
              {budget.percent_used}% used
            </div>
          </div>
          <button type="button" className="btn btn-ghost btn-sm"
                  onClick={onDelete} aria-label="Remove budget"
                  style={{ padding: '1px 6px' }}>✕</button>
        </div>
      </div>
      <div style={{ background: 'var(--bg-secondary)', borderRadius: 4, height: 6, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: barColor, transition: 'width .3s' }} />
        {overflow > 0 && (
          <div style={{ width: `${Math.min(overflow, 100)}%`, height: '100%',
                        background: '#dc2626', marginTop: -6, opacity: 0.7 }} />
        )}
      </div>
    </div>
  );
}
