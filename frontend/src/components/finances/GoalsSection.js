import React, { useState, useEffect, useCallback } from 'react';
import Spin from '../ui/Spin';
import { fmt$ } from '../../utils/formatting';
import { listGoals, createGoal, deleteGoal } from '../../api/goals';
import { getBalancesSummary } from '../../api/balances';
import { classifyAccountBucket, loadInvestmentSubtypes } from '../../utils/accountBucket';

// Where a goal's money can actually sit. Filtering on `type === 'depository'`
// excluded every brokerage, so a house deposit held in a taxable account
// could not be linked to the goal it was funding. Cards and houses are not
// funding sources.
const FUNDING_BUCKETS = new Set(['cash', 'investment']);

const EMPTY_DRAFT = {
  name: '', target_amount: '', target_date: '',
  current_balance: '', linked_account_id: '', kind: 'savings', notes: '',
};

export default function GoalsSection() {
  const [goals,    setGoals]    = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [draft,    setDraft]    = useState(EMPTY_DRAFT);
  const [saving,   setSaving]   = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([listGoals(), getBalancesSummary(false), loadInvestmentSubtypes()])
      .then(([g, b]) => {
        setGoals(g.data);
        setAccounts((b.data?.accounts ?? [])
          .filter((a) => FUNDING_BUCKETS.has(classifyAccountBucket(a))));
      })
      .catch(() => setError('Could not load goals — is the backend running?'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSave = useCallback(async () => {
    if (!draft.name.trim() || !draft.target_amount) return;
    setSaving(true);
    try {
      await createGoal({
        name:              draft.name.trim(),
        target_amount:     parseFloat(draft.target_amount) || 0,
        target_date:       draft.target_date || null,
        current_balance:   parseFloat(draft.current_balance) || 0,
        linked_account_id: draft.linked_account_id || null,
        kind:              draft.kind,
        notes:             draft.notes,
      });
      setDraft(EMPTY_DRAFT);
      setShowForm(false);
      load();
    } catch {
      setError('Could not save goal.');
    } finally {
      setSaving(false);
    }
  }, [draft, load]);

  const handleDelete = useCallback(async (id) => {
    try {
      await deleteGoal(id);
      load();
    } catch { /* silent */ }
  }, [load]);

  return (
    <div className="finances-section">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 className="finances-section-title" style={{ margin: 0 }}>Savings Goals</h2>
        <button type="button" className="btn btn-secondary btn-sm"
                onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ Add Goal'}
        </button>
      </div>

      {showForm && (
        <div className="manual-acct-form">
          <div className="form-row-2">
            <div className="field-group">
              <label className="field-label" htmlFor="goal-name">Goal Name</label>
              <input id="goal-name" className="form-input" type="text" placeholder="e.g. Emergency Fund"
                     value={draft.name}
                     onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
            </div>
            <div className="field-group">
              <label className="field-label" htmlFor="goal-kind">Type</label>
              <select id="goal-kind" className="form-input" value={draft.kind}
                      onChange={(e) => setDraft((d) => ({ ...d, kind: e.target.value }))}>
                <option value="savings">Savings goal</option>
                <option value="emergency_fund">Emergency fund</option>
                <option value="travel">Travel</option>
                <option value="big_purchase">Big purchase (car, house, etc.)</option>
              </select>
            </div>
          </div>
          <div className="form-row-2">
            <div className="field-group">
              <label className="field-label" htmlFor="goal-target-amount">Target Amount ($)</label>
              <input id="goal-target-amount" className="form-input" type="number" min="0" step="0.01" placeholder="0.00"
                     value={draft.target_amount}
                     onChange={(e) => setDraft((d) => ({ ...d, target_amount: e.target.value }))} />
            </div>
            <div className="field-group">
              <label className="field-label" htmlFor="goal-target-date">Target Date (optional)</label>
              <input id="goal-target-date" className="form-input" type="date"
                     value={draft.target_date}
                     onChange={(e) => setDraft((d) => ({ ...d, target_date: e.target.value }))} />
            </div>
          </div>
          <div className="form-row-2">
            <div className="field-group">
              <label className="field-label" htmlFor="goal-linked-account">Linked Account (optional)</label>
              <select id="goal-linked-account" className="form-input" value={draft.linked_account_id}
                      onChange={(e) => setDraft((d) => ({ ...d, linked_account_id: e.target.value }))}>
                <option value="">— none (track manually) —</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.institution} · {a.name} ({fmt$(a.available)})
                  </option>
                ))}
              </select>
            </div>
            <div className="field-group">
              <label className="field-label" htmlFor="goal-current-balance">Current Balance ($)</label>
              <input id="goal-current-balance" className="form-input" type="number" min="0" step="0.01" placeholder="0.00"
                     disabled={!!draft.linked_account_id}
                     value={draft.current_balance}
                     onChange={(e) => setDraft((d) => ({ ...d, current_balance: e.target.value }))} />
            </div>
          </div>
          <div style={{ marginTop: 8 }}>
            <button type="button" className="btn btn-primary"
                    onClick={handleSave}
                    disabled={saving || !draft.name.trim() || !draft.target_amount}>
              {saving ? <><Spin /> Saving…</> : 'Save Goal'}
            </button>
          </div>
        </div>
      )}

      {loading && <div style={{ textAlign: 'center', padding: '20px 0' }}><Spin /> Loading…</div>}
      {error && <div style={{ color: '#f87171', fontSize: 14 }}>{error}</div>}

      {!loading && !error && goals.length === 0 && (
        <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>
          No goals yet — set one to give the advisor something to pace against.
        </div>
      )}

      {!loading && goals.map((g) => (
        <GoalRow key={g.id} goal={g} onDelete={() => handleDelete(g.id)} />
      ))}
    </div>
  );
}

const KIND_BADGE = {
  emergency_fund: { label: 'Emergency',    color: '#3b82f6' },
  travel:         { label: 'Travel',       color: '#8b5cf6' },
  big_purchase:   { label: 'Big purchase', color: '#f59e0b' },
};
const KIND_BAR_COLOR = {
  emergency_fund: '#3b82f6',
  travel:         '#8b5cf6',
  big_purchase:   '#f59e0b',
};

function GoalRow({ goal, onDelete }) {
  const pct = Math.min(goal.progress_pct, 100);
  const reached = goal.progress_pct >= 100;
  const barColor = reached ? '#10b981' : (KIND_BAR_COLOR[goal.kind] || '#10b981');
  const badge = KIND_BADGE[goal.kind];

  return (
    <div className="balance-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div className="balance-row-name">
            {goal.name}
            {badge && (
              <span
                className="manual-badge"
                style={{ background: `${badge.color}26`, color: badge.color }}
              >
                {badge.label}
              </span>
            )}
          </div>
          {goal.target_date && (
            <div className="balance-row-inst">
              By {goal.target_date}
              {(goal.monthly_required !== null && goal.monthly_required !== undefined) && goal.monthly_required > 0 && (
                <> · save {fmt$(goal.monthly_required)}/mo to hit it</>
              )}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ textAlign: 'right' }}>
            <div className="balance-available">
              {fmt$(goal.current_balance)}
              <span style={{ fontSize: 11, opacity: 0.6, marginLeft: 4 }}>
                / {fmt$(goal.target_amount)}
              </span>
            </div>
            <div style={{ fontSize: 12, color: reached ? '#10b981' : 'var(--text-muted)' }}>
              {goal.progress_pct}% {reached ? '✓ reached' : ''}
            </div>
          </div>
          <button type="button" className="btn btn-ghost btn-sm"
                  onClick={onDelete} aria-label="Remove goal"
                  style={{ padding: '1px 6px' }}>✕</button>
        </div>
      </div>
      <div style={{ background: 'var(--bg-secondary)', borderRadius: 4, height: 6, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: barColor, transition: 'width .3s' }} />
      </div>
    </div>
  );
}
