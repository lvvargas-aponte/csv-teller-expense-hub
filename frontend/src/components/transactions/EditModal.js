import React, { useState } from 'react';
import Backdrop from '../ui/Backdrop';
import { fmt$, fmtDate, calculateHalf } from '../../utils/formatting';

export default function EditModal({ txn, personNames, onSave, onClose }) {
  const [form, setForm] = useState({
    is_shared:     txn.is_shared     || false,
    who:           txn.who           || personNames.person_1 || '',
    what:          txn.what          || '',
    person_1_owes: txn.person_1_owes || 0,
    person_2_owes: txn.person_2_owes || 0,
    notes:         txn.notes         || '',
    category:      txn.category      || '',
  });

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const split50 = (e) => {
    e.preventDefault();
    const half = calculateHalf(txn.amount);
    setForm((f) => ({ ...f, person_1_owes: half, person_2_owes: half }));
  };

  return (
    <Backdrop onClose={onClose}>
      <div className="modal">
        <div className="modal-header">
          <div className="modal-header-text">
            <div className="modal-title">{txn.description}</div>
            <div className="modal-sub">{fmtDate(txn.date)} · {fmt$(txn.amount)}</div>
          </div>
          <button type="button" className="close-btn" aria-label="Close" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          <div className="field-group">
            <label className="field-label" htmlFor="txn-category">Category</label>
            <input id="txn-category" className="form-input" type="text"
                   value={form.category}
                   onChange={(e) => set('category', e.target.value)}
                   placeholder="e.g. Groceries, Dining" />
          </div>

          <div className="toggle-row">
            <span className="field-label">Type</span>
            <div className="segmented">
              {['Personal', 'Shared'].map((opt) => (
                <button
                  key={opt} type="button"
                  onClick={() => set('is_shared', opt === 'Shared')}
                  className={`seg${form.is_shared === (opt === 'Shared') ? ' seg--active' : ''}`}
                >
                  {opt}
                </button>
              ))}
            </div>
          </div>

          {form.is_shared && (
            <>
              <div className="form-row-2">
                <div className="field-group">
                  <label className="field-label">Who paid?</label>
                  <input className="form-input" type="text" value={form.who}
                         onChange={(e) => set('who', e.target.value)} placeholder="Name" />
                </div>
                <div className="field-group">
                  <label className="field-label">What for?</label>
                  <input className="form-input" type="text" value={form.what}
                         onChange={(e) => set('what', e.target.value)} placeholder="Category / item" />
                </div>
              </div>

              <div className="split-row">
                <div className="field-group">
                  <label className="field-label">{personNames.person_1} owes</label>
                  <input className="form-input" type="number" step="0.01" min="0"
                         value={form.person_1_owes}
                         onChange={(e) => set('person_1_owes', parseFloat(e.target.value) || 0)} />
                </div>
                <button type="button" className="split-btn" onClick={split50}>50/50</button>
                <div className="field-group">
                  <label className="field-label">{personNames.person_2} owes</label>
                  <input className="form-input" type="number" step="0.01" min="0"
                         value={form.person_2_owes}
                         onChange={(e) => set('person_2_owes', parseFloat(e.target.value) || 0)} />
                </div>
              </div>

              <div className="field-group">
                <label className="field-label">Notes</label>
                <textarea className="form-input form-input--textarea"
                          value={form.notes} onChange={(e) => set('notes', e.target.value)}
                          placeholder="Optional notes…" />
              </div>
            </>
          )}
        </div>

        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="btn btn-primary" onClick={() => onSave(
            form.is_shared ? form : { ...form, who: '', what: '', person_1_owes: 0, person_2_owes: 0 }
          )}>Save</button>
        </div>
      </div>
    </Backdrop>
  );
}
