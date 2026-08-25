import React, { useState, useEffect, useCallback } from 'react';
import Spin from '../ui/Spin';
import { fmt$ } from '../../utils/formatting';
import { listBudgets, upsertBudget, deleteBudget } from '../../api/budgets';
import { useCategories } from '../../hooks/useCategories';
import BudgetPresetModal from './BudgetPresetModal';

export default function BudgetsSection() {
  const [budgets, setBudgets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [showPreset, setShowPreset] = useState(false);
  const [draft, setDraft] = useState({ category: '', monthly_limit: '', notes: '' });
  const [saving, setSaving] = useState(false);
  const { categories } = useCategories();

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
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" className="btn btn-secondary btn-sm"
                  onClick={() => setShowPreset(true)}>
            Use a preset
          </button>
          <button type="button" className="btn btn-secondary btn-sm"
                  onClick={() => setShowForm((v) => !v)}>
            {showForm ? 'Cancel' : '+ Add Budget'}
          </button>
        </div>
      </div>

      {showPreset && (
        <BudgetPresetModal
          categories={categories}
          existingBudgets={budgets}
          onClose={() => setShowPreset(false)}
          onApplied={() => { setShowPreset(false); load(); }}
        />
      )}

      {showForm && (
        <div className="manual-acct-form">
          <div className="form-row-2">
            <div className="field-group">
              <label className="field-label" htmlFor="budget-category">Category</label>
              <input id="budget-category" className="form-input" type="text" placeholder="e.g. Dining"
                     value={draft.category}
                     onChange={(e) => setDraft((d) => ({ ...d, category: e.target.value }))} />
            </div>
            <div className="field-group">
              <label className="field-label" htmlFor="budget-monthly-limit">Monthly Limit ($)</label>
              <input id="budget-monthly-limit" className="form-input" type="number" min="0" step="0.01" placeholder="0.00"
                     value={draft.monthly_limit}
                     onChange={(e) => setDraft((d) => ({ ...d, monthly_limit: e.target.value }))} />
            </div>
          </div>
          <div className="form-row-2">
            <div className="field-group" style={{ gridColumn: '1 / -1' }}>
              <label className="field-label" htmlFor="budget-notes">Notes (optional)</label>
              <input id="budget-notes" className="form-input" type="text"
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
      {error && <div style={{ color: 'var(--status-bad-text)', fontSize: 14 }}>{error}</div>}

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

// Pace states carry a word as well as a colour — the row used to encode
// budget health in bar colour alone, which says nothing to a colour-blind
// reader and nothing at all to someone scanning the list.
const PACE_CHIP = {
  over_budget: { label: 'Over budget', color: '#b91c1c', bg: '#fee2e2' },
  over_pace:   { label: 'Over pace',   color: '#92400e', bg: '#fef3c7' },
};

function BudgetRow({ budget, onDelete }) {
  const pct = Math.min(budget.percent_used, 100);
  const overflow = Math.max(budget.percent_used - 100, 0);
  const barColor = budget.over_budget
    ? 'var(--red)'
    : (budget.percent_used > 80 ? 'var(--amber)' : 'var(--accent)');
  const chip = PACE_CHIP[budget.pace_status];
  const progress = budget.month_progress_pct;
  const projected = budget.projected_month_end;

  return (
    <div className="balance-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div className="balance-row-name">
            {budget.category}
            {chip && (
              <span
                style={{
                  marginLeft: 8, padding: '1px 6px', borderRadius: 99,
                  fontSize: 11, fontWeight: 600,
                  color: chip.color, background: chip.bg,
                }}
              >
                {chip.label}
              </span>
            )}
          </div>
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
            <div style={{ fontSize: 12, color: budget.over_budget ? 'var(--status-bad-text)' : 'var(--text-muted)' }}>
              {budget.percent_used}% used
            </div>
          </div>
          <button type="button" className="btn btn-ghost btn-sm"
                  onClick={onDelete} aria-label={`Remove the ${budget.category} budget`}
                  style={{ padding: '1px 6px' }}><span aria-hidden="true">✕</span></button>
        </div>
      </div>
      <div
        style={{
          position: 'relative', background: 'var(--bg-secondary)',
          borderRadius: 4, height: 6,
        }}
        role="progressbar"
        aria-label={`${budget.category} budget`}
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuetext={`${budget.percent_used}% of ${fmt$(budget.monthly_limit)} used${chip ? ` — ${chip.label}` : ''}`}
      >
        <div style={{
          borderRadius: 4, height: '100%', overflow: 'hidden',
        }}>
          <div style={{ width: `${pct}%`, height: '100%', background: barColor, transition: 'width .3s' }} />
          {overflow > 0 && (
            <div style={{ width: `${Math.min(overflow, 100)}%`, height: '100%',
                          background: '#dc2626', marginTop: -6, opacity: 0.7 }} />
          )}
        </div>
        {/* Elapsed month: spend to the left of this mark is ahead of time. */}
        {(progress !== null && progress !== undefined) && (
          <div
            role="img"
            aria-label={`${Math.round(progress)}% of the month elapsed`}
            title={`${Math.round(progress)}% of the month elapsed`}
            style={{
              position: 'absolute', top: -2, bottom: -2,
              left: `${Math.min(progress, 100)}%`,
              width: 2, background: 'var(--text-muted)', opacity: 0.8,
            }}
          />
        )}
      </div>
      {(projected !== null && projected !== undefined) && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          Pacing to {fmt$(projected)} by month end
          {budget.projected_overage ? ` — ${fmt$(budget.projected_overage)} over` : ''}
        </div>
      )}
    </div>
  );
}
