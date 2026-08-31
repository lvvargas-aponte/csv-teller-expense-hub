import React, { useEffect, useMemo, useState } from 'react';
import Backdrop from '../ui/Backdrop';
import Spin from '../ui/Spin';
import { fmt$ } from '../../utils/formatting';
import { upsertBudget } from '../../api/budgets';
import { getRatios } from '../../api/health';

const RULES = [
  { id: '503020', label: '50/30/20', needs: 50, wants: 30, savings: 20,
    desc: 'Classic — half on needs, 30% wants, 20% savings/debt' },
  { id: '702010', label: '70/20/10', needs: 70, wants: 20, savings: 10,
    desc: 'Tight budget — needs heavy, modest savings' },
  { id: '602020', label: '60/20/20', needs: 60, wants: 20, savings: 20,
    desc: 'Balanced — moderate savings' },
  { id: '801010', label: '80/10/10', needs: 80, wants: 10, savings: 10,
    desc: 'High cost-of-living variant' },
];

const BUCKETS = ['needs', 'wants', 'savings', 'skip'];
const BUCKET_LABEL = { needs: 'Needs', wants: 'Wants', savings: 'Savings', skip: 'Skip' };
const BUCKET_COLOR = {
  needs: 'var(--chart-1)', wants: 'var(--chart-3)', savings: 'var(--good)', skip: 'var(--text-muted)',
};

const NEEDS_HINTS = [
  'mortgage', 'rent', 'utilit', 'electric', 'gas', 'water', 'internet', 'phone',
  'grocer', 'food', 'insurance', 'medical', 'health', 'doctor', 'pharmacy',
  'transport', 'fuel', 'car', 'transit', 'childcare', 'daycare', 'tuition', 'education',
];
const WANTS_HINTS = [
  'dining', 'restaurant', 'entertain', 'travel', 'shop', 'cloth', 'hobby',
  'subscription', 'stream', 'gym', 'coffee', 'alcohol', 'gift', 'fun',
];
const SAVINGS_HINTS = [
  'saving', 'invest', 'retire', '401k', 'ira', 'brokerage', 'debt', 'loan',
];

function classify(category) {
  const c = category.toLowerCase();
  if (SAVINGS_HINTS.some((h) => c.includes(h))) return 'savings';
  if (NEEDS_HINTS.some((h) => c.includes(h)))   return 'needs';
  if (WANTS_HINTS.some((h) => c.includes(h)))   return 'wants';
  return 'wants';
}

function evenSplit(assignments, bucketTotals) {
  const next = { ...assignments };
  ['needs', 'wants', 'savings'].forEach((b) => {
    const cats = Object.entries(next).filter(([, v]) => v.bucket === b);
    const per = cats.length ? +(bucketTotals[b] / cats.length).toFixed(2) : 0;
    cats.forEach(([c]) => { next[c] = { ...next[c], amount: per }; });
  });
  return next;
}

export default function BudgetPresetModal({ categories, existingBudgets, onClose, onApplied }) {
  const [step, setStep] = useState(1);
  const [ruleId, setRuleId] = useState(RULES[0].id);
  const [income, setIncome] = useState('');
  const [assignments, setAssignments] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [incomeSource, setIncomeSource] = useState(null);

  // The app already knows this figure — asking the user to retype it is how
  // the wizard ended up with a third income number nobody reconciled.
  useEffect(() => {
    let cancelled = false;
    getRatios()
      .then((r) => {
        const detected = r.data?.income;
        if (cancelled || !detected?.monthly) return;
        setIncome((typed) => (typed === '' ? String(detected.monthly) : typed));
        setIncomeSource(detected.source);
      })
      .catch(() => { /* the field just stays empty */ });
    return () => { cancelled = true; };
  }, []);

  const rule = useMemo(() => RULES.find((r) => r.id === ruleId) || RULES[0], [ruleId]);
  // Tolerate "$", ",", and stray whitespace so the Next button enables for inputs like "5,000".
  const incomeNum = parseFloat(String(income).replace(/[^0-9.]/g, '')) || 0;

  const bucketTotals = useMemo(() => ({
    needs:   +(incomeNum * rule.needs   / 100).toFixed(2),
    wants:   +(incomeNum * rule.wants   / 100).toFixed(2),
    savings: +(incomeNum * rule.savings / 100).toFixed(2),
  }), [incomeNum, rule]);

  const goToStep2 = () => {
    const seed = {};
    (categories || []).forEach((c) => { seed[c] = { bucket: classify(c), amount: 0 }; });
    setAssignments(evenSplit(seed, bucketTotals));
    setStep(2);
  };

  const setBucket = (cat, bucket) => {
    setAssignments((prev) => {
      const next = { ...prev, [cat]: { ...prev[cat], bucket } };
      return evenSplit(next, bucketTotals);
    });
  };

  const setAmount = (cat, val) => {
    setAssignments((prev) => ({
      ...prev,
      [cat]: { ...prev[cat], amount: parseFloat(val) || 0 },
    }));
  };

  const allocatedBy = useMemo(() => {
    const out = { needs: 0, wants: 0, savings: 0 };
    Object.values(assignments).forEach((v) => {
      if (v.bucket !== 'skip') out[v.bucket] += v.amount;
    });
    return out;
  }, [assignments]);

  const existingSet = useMemo(
    () => new Set(existingBudgets.map((b) => b.category.toLowerCase())),
    [existingBudgets],
  );
  const overwriteCount = useMemo(
    () => Object.entries(assignments)
      .filter(([c, v]) => v.bucket !== 'skip' && v.amount > 0 && existingSet.has(c.toLowerCase()))
      .length,
    [assignments, existingSet],
  );

  const apply = async () => {
    setSaving(true);
    setError(null);
    try {
      const entries = Object.entries(assignments)
        .filter(([, v]) => v.bucket !== 'skip' && v.amount > 0);
      const results = await Promise.allSettled(
        entries.map(([cat, v]) => upsertBudget(cat, {
          category:      cat,
          monthly_limit: v.amount,
          notes:         `${rule.label} · ${BUCKET_LABEL[v.bucket]}`,
        }))
      );
      const failed = results.filter((r) => r.status === 'rejected').length;
      if (failed > 0) {
        setError(`${failed} budget${failed === 1 ? '' : 's'} could not be saved.`);
        setSaving(false);
        return;
      }
      onApplied();
    } catch {
      setError('Could not save budgets — please try again.');
      setSaving(false);
    }
  };

  const incomeReady = incomeNum > 0;
  const anyAssigned = Object.values(assignments).some((v) => v.bucket !== 'skip' && v.amount > 0);

  return (
    <Backdrop onClose={onClose}>
      <div
        className="modal"
        style={{
          maxWidth: 760,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <div className="modal-header">
          <div className="modal-header-text">
            <div className="modal-title">Budget preset · Step {step} of 2</div>
            <div className="modal-sub">
              {step === 1
                ? 'Pick a rule and enter your monthly take-home income.'
                : 'Map your categories into buckets. Amounts split evenly by default — tweak as needed.'}
            </div>
          </div>
          <button type="button" className="close-btn" aria-label="Close" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body" style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
          {step === 1 && (
            <div>
              <div className="field-group" style={{ marginBottom: 16 }}>
                <label className="field-label" htmlFor="preset-income">Monthly take-home income ($)</label>
                <input
                  id="preset-income"
                  className="form-input"
                  type="text"
                  inputMode="decimal"
                  placeholder="e.g. 5000"
                  value={income}
                  onChange={(e) => setIncome(e.target.value)}
                  autoFocus
                />
                {!incomeReady && (
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                    Enter your monthly take-home income to enable Next.
                  </div>
                )}
                {incomeReady && incomeSource === 'profile' && (
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                    From your financial profile — edit it here for this plan only.
                  </div>
                )}
                {incomeReady && incomeSource === 'detected' && (
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                    Detected from your deposits — edit if it looks wrong.
                  </div>
                )}
              </div>

              <div className="field-label" style={{ marginBottom: 8 }}>Pick a rule</div>
              <div style={{ display: 'grid', gap: 8 }}>
                {RULES.map((r) => {
                  const selected = r.id === ruleId;
                  return (
                    <label
                      key={r.id}
                      htmlFor={`rule-${r.id}`}
                      style={{
                        display: 'flex', gap: 12, alignItems: 'flex-start',
                        padding: 12,
                        border: `1px solid ${selected ? 'var(--accent)' : 'var(--border)'}`,
                        borderRadius: 8,
                        background: selected ? 'color-mix(in srgb, var(--brand) 8%, transparent)' : 'transparent',
                        cursor: 'pointer',
                      }}
                    >
                      <input
                        id={`rule-${r.id}`}
                        type="radio"
                        name="rule"
                        checked={selected}
                        onChange={() => setRuleId(r.id)}
                        style={{ marginTop: 3 }}
                      />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600 }}>{r.label}</div>
                        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{r.desc}</div>
                        {incomeReady && (
                          <div style={{ fontSize: 12, marginTop: 6, color: 'var(--text-secondary)' }}>
                            Needs {fmt$(incomeNum * r.needs / 100)}
                            {' · '}Wants {fmt$(incomeNum * r.wants / 100)}
                            {' · '}Savings {fmt$(incomeNum * r.savings / 100)}
                          </div>
                        )}
                      </div>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          {step === 2 && (
            <div>
              <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8,
                marginBottom: 12,
              }}>
                {['needs', 'wants', 'savings'].map((b) => {
                  const over = allocatedBy[b] > bucketTotals[b] + 0.01;
                  return (
                    <div key={b} style={{
                      padding: 10,
                      border: `1px solid ${BUCKET_COLOR[b]}`,
                      borderRadius: 8,
                      background: 'color-mix(in srgb, var(--brand) 4%, transparent)',
                    }}>
                      <div style={{ fontSize: 12, color: BUCKET_COLOR[b], fontWeight: 600 }}>
                        {BUCKET_LABEL[b]} · target {fmt$(bucketTotals[b])}
                      </div>
                      <div style={{ fontSize: 13, color: over ? 'var(--status-bad-text)' : 'var(--text-secondary)' }}>
                        Allocated {fmt$(allocatedBy[b])}
                        {over && ' (over)'}
                      </div>
                    </div>
                  );
                })}
              </div>

              {overwriteCount > 0 && (
                <div style={{
                  fontSize: 12, color: 'var(--status-warn-text)', marginBottom: 12,
                  padding: 8, border: '1px solid var(--warn)', borderRadius: 6,
                }}>
                  {overwriteCount} existing budget{overwriteCount === 1 ? '' : 's'} will be overwritten.
                </div>
              )}

              {categories.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: 16 }}>
                  No categories yet — categorize some transactions first.
                </div>
              ) : (
                <table className="txn-table eh-table" style={{ fontSize: 13 }}>
                  <caption className="sr-only">Suggested budgets by category</caption>
                  <thead>
                    <tr>
                      <th scope="col">Category</th>
                      <th scope="col" style={{ width: 280 }}>Bucket</th>
                      <th scope="col" className="col-amount" style={{ width: 120 }}>Monthly $</th>
                    </tr>
                  </thead>
                  <tbody>
                    {categories.map((cat) => {
                      const a = assignments[cat] || { bucket: 'wants', amount: 0 };
                      return (
                        <tr key={cat}>
                          <td>{cat}</td>
                          <td>
                            <div style={{ display: 'flex', gap: 4 }} role="radiogroup" aria-label={`Bucket for ${cat}`}>
                              {BUCKETS.map((b) => {
                                const selected = a.bucket === b;
                                return (
                                  <button
                                    key={b}
                                    type="button"
                                    onClick={() => setBucket(cat, b)}
                                    style={{
                                      flex: 1,
                                      padding: '4px 6px',
                                      fontSize: 11,
                                      border: `1px solid ${selected ? BUCKET_COLOR[b] : 'var(--border)'}`,
                                      background: selected ? BUCKET_COLOR[b] : 'transparent',
                                      color: selected ? 'var(--text-inverse)' : 'var(--text-secondary)',
                                      borderRadius: 4,
                                      cursor: 'pointer',
                                    }}
                                  >
                                    {BUCKET_LABEL[b]}
                                  </button>
                                );
                              })}
                            </div>
                          </td>
                          <td className="col-amount">
                            <input
                              type="number"
                              min="0"
                              step="0.01"
                              className="form-input"
                              value={a.bucket === 'skip' ? '' : a.amount}
                              disabled={a.bucket === 'skip'}
                              onChange={(e) => setAmount(cat, e.target.value)}
                              aria-label={`Monthly limit for ${cat}`}
                              style={{ padding: '4px 6px', fontSize: 13, textAlign: 'right' }}
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {error && (
            <div style={{ color: 'var(--status-bad-text)', fontSize: 13, marginTop: 12 }}>{error}</div>
          )}
        </div>

        <div className="modal-footer">
          {step === 2 && (
            <button type="button" className="btn btn-secondary" onClick={() => setStep(1)} disabled={saving}>
              ← Back
            </button>
          )}
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          {step === 1 ? (
            <button type="button" className="btn btn-primary"
                    onClick={goToStep2}
                    disabled={!incomeReady}>
              Next →
            </button>
          ) : (
            <button type="button" className="btn btn-primary"
                    onClick={apply}
                    disabled={saving || !anyAssigned}>
              {saving ? <><Spin /> Saving…</> : 'Apply budgets'}
            </button>
          )}
        </div>
      </div>
    </Backdrop>
  );
}
