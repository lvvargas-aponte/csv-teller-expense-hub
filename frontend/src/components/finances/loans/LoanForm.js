import React, { useState } from 'react';

import Backdrop from '../../ui/Backdrop';
import { Z_BACKDROP_DIALOG } from '../../../utils/zIndex';

const EMPTY = {
  name: '', loan_type: 'mortgage', property_id: '', lender: '', lien_position: 1,
  original_principal: '', current_principal: '', interest_rate_pct: '',
  rate_type: 'fixed', term_months: 360, origination_date: '', first_payment_date: '',
  payment_amount: '', escrow_monthly: '', pmi_monthly: '', extra_monthly: '',
  io_months: 0, notes: '',
};

const LOAN_TYPES = [
  ['mortgage', 'Mortgage'], ['heloc', 'HELOC'], ['auto', 'Auto'],
  ['student', 'Student'], ['personal', 'Personal'],
  ['business', 'Business'], ['other', 'Other'],
];

const num = (v) => (v === '' || v === null || v === undefined ? null : parseFloat(v));

export default function LoanForm({ initial, properties, onSubmit, onClose, saving }) {
  const [draft, setDraft] = useState(() => ({ ...EMPTY, ...(initial || {}) }));
  const [error, setError] = useState(null);

  const set = (key) => (e) => setDraft((d) => ({ ...d, [key]: e.target.value }));

  const submit = (e) => {
    e.preventDefault();
    if (!draft.name.trim()) { setError('Give the loan a name.'); return; }
    if (!num(draft.original_principal)) { setError('Enter the original loan amount.'); return; }
    if (!draft.origination_date) { setError('Enter the origination date.'); return; }
    setError(null);
    onSubmit({
      ...draft,
      name: draft.name.trim(),
      property_id: draft.property_id || null,
      lien_position: parseInt(draft.lien_position, 10) || 1,
      term_months: parseInt(draft.term_months, 10) || 360,
      io_months: parseInt(draft.io_months, 10) || 0,
      original_principal: num(draft.original_principal),
      current_principal: num(draft.current_principal),
      interest_rate_pct: num(draft.interest_rate_pct) ?? 0,
      payment_amount: num(draft.payment_amount),
      escrow_monthly: num(draft.escrow_monthly) ?? 0,
      pmi_monthly: num(draft.pmi_monthly) ?? 0,
      extra_monthly: num(draft.extra_monthly) ?? 0,
      first_payment_date: draft.first_payment_date || null,
    });
  };

  const field = (key, label, type = 'number', extra = {}) => (
    <label className="prop-field">
      <span className="prop-field-label">{label}</span>
      <input
        type={type}
        value={draft[key] ?? ''}
        onChange={set(key)}
        step={type === 'number' ? 'any' : undefined}
        {...extra}
      />
    </label>
  );

  return (
    <Backdrop onClose={onClose} zIndex={Z_BACKDROP_DIALOG}>
      <form className="modal prop-form" onSubmit={submit}>
        <h3>{initial?.name ? 'Edit loan' : 'Add a loan'}</h3>

        <div className="prop-form-grid">
          {field('name', 'Name', 'text')}
          {field('lender', 'Lender', 'text')}

          <label className="prop-field">
            <span className="prop-field-label">Type</span>
            <select value={draft.loan_type} onChange={set('loan_type')}>
              {LOAN_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>

          <label className="prop-field">
            <span className="prop-field-label">Secured by</span>
            <select value={draft.property_id || ''} onChange={set('property_id')}>
              <option value="">Nothing (auto, student, personal…)</option>
              {(properties || []).map((p) => (
                <option key={p.property_id} value={p.property_id}>{p.name}</option>
              ))}
            </select>
          </label>

          {field('lien_position', 'Lien position', 'number', { min: 1 })}
        </div>

        <div className="prop-form-section">Terms</div>
        <div className="prop-form-grid">
          {field('original_principal', 'Original amount')}
          {field('current_principal', 'Current balance (optional)')}
          {field('interest_rate_pct', 'Rate %')}
          {field('term_months', 'Term (months)')}
          {field('origination_date', 'Origination date', 'date')}
          {field('first_payment_date', 'First payment date', 'date')}
          {field('io_months', 'Interest-only months')}
        </div>

        <div className="prop-form-section">
          Payment
          <span className="prop-form-hint">
            Leave the payment blank to derive it from the amount, rate and term.
            Escrow is kept separate — it doesn&apos;t pay down principal.
          </span>
        </div>
        <div className="prop-form-grid">
          {field('payment_amount', 'Principal & interest')}
          {field('escrow_monthly', 'Escrow (taxes + insurance)')}
          {field('pmi_monthly', 'PMI')}
          {field('extra_monthly', 'Extra principal each month')}
        </div>

        {error && <div className="ov-error">{error}</div>}

        <div className="modal-actions">
          <button type="button" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? 'Saving…' : 'Save loan'}
          </button>
        </div>
      </form>
    </Backdrop>
  );
}
