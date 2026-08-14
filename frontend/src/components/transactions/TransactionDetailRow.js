import React, { useEffect, useMemo, useState } from 'react';
import {
  fmt$, fmtDate, calculateHalf, channelLabel, formatAccountType,
} from '../../utils/formatting';
import CategoryCombobox from './CategoryCombobox';

function formToState(txn) {
  return {
    category:      txn.category      || '',
    is_shared:     !!txn.is_shared,
    who:           txn.who           || '',
    what:          txn.what          || '',
    person_1_owes: txn.person_1_owes || 0,
    person_2_owes: txn.person_2_owes || 0,
    notes:         txn.notes         || '',
    reviewed:      !!txn.reviewed,
    transaction_type: txn.transaction_type === 'credit' ? 'credit' : 'debit',
  };
}

function MetaRow({ label, value }) {
  if (value === null || value === undefined || value === '') return null;
  return (
    <>
      <dt className="tx-detail-meta-key">{label}</dt>
      <dd className="tx-detail-meta-val" title={String(value)}>{value}</dd>
    </>
  );
}

// Inline detail editor rendered as a full-width table row directly beneath
// the clicked transaction row (design handoff A2). Edits go to a local draft;
// Save commits, Cancel/Collapse discard.
export default function TransactionDetailRow({
  txn,
  colSpan,
  personNames = {},
  categories = [],
  onSave,
  onRemoveCategory,
  onDelete,
  onClose,
  onDraftChange,
}) {
  const [form, setForm] = useState(() => formToState(txn));
  const [saving, setSaving] = useState(false);

  // Switching rows re-seeds the form and discards any unsaved edits.
  useEffect(() => { setForm(formToState(txn)); }, [txn.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const pristine = useMemo(() => formToState(txn), [txn]);
  const dirty = useMemo(
    () => Object.keys(pristine).some((k) => form[k] !== pristine[k]),
    [form, pristine]
  );

  useEffect(() => {
    if (onDraftChange) onDraftChange({ category: form.category, is_shared: form.is_shared });
  }, [form.category, form.is_shared, onDraftChange]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const split50 = () => {
    const half = calculateHalf(txn.amount);
    setForm((f) => ({ ...f, person_1_owes: half, person_2_owes: half }));
  };

  const handleSave = async () => {
    if (saving) return;
    setSaving(true);
    try {
      await onSave(txn, form.is_shared ? form : {
        ...form, who: '', what: '', person_1_owes: 0, person_2_owes: 0,
      });
    } finally {
      setSaving(false);
    }
  };

  const isCredit = form.transaction_type === 'credit';

  return (
    <tr className="tx-detail-row">
      <td colSpan={colSpan}>
        <div className="tx-detail-grid" role="group" aria-label="Transaction details">
          <div className="tx-detail-col">
            <div className="tx-detail-head">
              <span className={`tx-detail-amount${isCredit ? ' tx-detail-amount--cr' : ''}`}>
                {fmt$(txn.amount)}
              </span>
              <span className="tx-detail-sub">
                {fmtDate(txn.date)}
                {txn.institution ? ` · ${txn.institution}` : ''}
                {txn.account_type ? ` ${formatAccountType(txn.account_type)}` : ''}
              </span>
            </div>

            <div className="field-group">
              <span className="field-label">Category</span>
              <CategoryCombobox
                value={form.category}
                categories={categories}
                onChange={(next) => set('category', next)}
                onRemoveCategory={onRemoveCategory}
              />
            </div>

            <div className="tx-detail-stack-row">
              <span className="field-label">Split</span>
              <div className={`segmented${form.is_shared ? ' segmented--shared' : ''}`}>
                {['Personal', 'Shared'].map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => set('is_shared', opt === 'Shared')}
                    className={`seg${form.is_shared === (opt === 'Shared') ? ' seg--active' : ''}`}
                    aria-pressed={form.is_shared === (opt === 'Shared')}
                  >{opt}</button>
                ))}
              </div>
            </div>

            {form.is_shared && (
              <>
                <div className="form-row-2">
                  <div className="field-group">
                    <label className="field-label" htmlFor="tx-detail-who">Who paid?</label>
                    <input
                      id="tx-detail-who" className="form-input" type="text" placeholder="Name"
                      value={form.who} onChange={(e) => set('who', e.target.value)}
                    />
                  </div>
                  <div className="field-group">
                    <label className="field-label" htmlFor="tx-detail-what">What for?</label>
                    <input
                      id="tx-detail-what" className="form-input" type="text" placeholder="Category / item"
                      value={form.what} onChange={(e) => set('what', e.target.value)}
                    />
                  </div>
                </div>

                <div className="split-row">
                  <div className="field-group">
                    <label className="field-label" htmlFor="tx-detail-p1">
                      {personNames.person_1 || 'Person 1'} owes
                    </label>
                    <input
                      id="tx-detail-p1" className="form-input" type="number" step="0.01" min="0"
                      value={form.person_1_owes}
                      onChange={(e) => set('person_1_owes', parseFloat(e.target.value) || 0)}
                    />
                  </div>
                  <button type="button" className="split-btn" onClick={split50}>50/50</button>
                  <div className="field-group">
                    <label className="field-label" htmlFor="tx-detail-p2">
                      {personNames.person_2 || 'Person 2'} owes
                    </label>
                    <input
                      id="tx-detail-p2" className="form-input" type="number" step="0.01" min="0"
                      value={form.person_2_owes}
                      onChange={(e) => set('person_2_owes', parseFloat(e.target.value) || 0)}
                    />
                  </div>
                </div>
              </>
            )}

            <div className="tx-detail-stack-row">
              <span className="field-label">Type</span>
              <div className="segmented">
                {[['debit', 'Debit'], ['credit', 'Credit']].map(([val, label]) => (
                  <button
                    key={val}
                    type="button"
                    onClick={() => set('transaction_type', val)}
                    className={`seg${form.transaction_type === val ? ' seg--active' : ''}`}
                    aria-pressed={form.transaction_type === val}
                  >{label}</button>
                ))}
              </div>
            </div>

            <div className="tx-detail-stack-row">
              <span className="field-label">Reviewed</span>
              <button
                type="button"
                role="switch"
                aria-checked={form.reviewed}
                aria-label="Reviewed"
                className={`tx-switch${form.reviewed ? ' tx-switch--on' : ''}`}
                onClick={() => set('reviewed', !form.reviewed)}
              />
            </div>
          </div>

          <div className="tx-detail-col">
            <div className="field-group">
              <label className="field-label" htmlFor="tx-detail-notes">Notes</label>
              <textarea
                id="tx-detail-notes" className="form-input form-input--textarea tx-detail-notes"
                value={form.notes} onChange={(e) => set('notes', e.target.value)}
                placeholder="Why this was categorized this way, who to bill, anything to remember…"
              />
            </div>
          </div>

          <div className="tx-detail-col">
            <span className="field-label">Source record</span>
            <dl className="tx-detail-meta">
              <MetaRow label="Posted" value={txn.post_date ? fmtDate(txn.post_date) : ''} />
              <MetaRow label="Institution" value={txn.institution} />
              <MetaRow label="Account type" value={txn.account_type ? formatAccountType(txn.account_type) : ''} />
              <MetaRow label="Source" value={channelLabel(txn.source)} />
              <MetaRow label="Direction" value={txn.direction} />
              <MetaRow label="Transfer to" value={txn.transfer_to_account_id} />
              <MetaRow label="Account ID" value={txn.account_id} />
              <MetaRow label="Transaction ID" value={txn.transaction_id || txn.id} />
            </dl>
          </div>
        </div>

        <div className="tx-detail-actions">
          {onDelete && (
            <button type="button" className="tx-detail-btn tx-detail-btn--delete" onClick={() => onDelete(txn)}>
              Delete
            </button>
          )}
          {dirty && <span className="tx-detail-dirty">Unsaved changes</span>}
          {dirty && (
            <button type="button" className="tx-detail-btn" onClick={() => setForm(pristine)}>
              Cancel
            </button>
          )}
          <button
            type="button"
            className="tx-detail-btn tx-detail-btn--save"
            onClick={handleSave}
            disabled={!dirty || saving}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button type="button" className="tx-detail-btn" onClick={onClose}>
            Collapse
          </button>
        </div>
      </td>
    </tr>
  );
}
