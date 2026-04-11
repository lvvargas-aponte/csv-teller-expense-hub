import React, { useState } from 'react';
import Backdrop from './Backdrop';
import { prevMonthRange, thisMonthRange } from '../utils/formatting';

export default function SyncModal({ onSync, onClose }) {
  const pm = prevMonthRange();
  const tm = thisMonthRange();
  const [fromDate, setFromDate] = useState(pm.from);
  const [toDate,   setToDate]   = useState(pm.to);
  const [preset,   setPreset]   = useState('prev');

  const applyPreset = (p) => {
    setPreset(p);
    if (p === 'prev') { setFromDate(pm.from); setToDate(pm.to); }
    if (p === 'this') { setFromDate(tm.from); setToDate(tm.to); }
  };

  return (
    <Backdrop onClose={onClose} zIndex={210}>
      <div className="modal modal--sm">
        <div className="modal-header">
          <div className="modal-header-text">
            <div className="modal-title">🏦 Sync Bank Transactions</div>
            <div className="modal-sub">Choose a date range to pull from Teller</div>
          </div>
          <button type="button" className="close-btn" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          <div className="preset-group">
            {[
              { key: 'prev', label: 'Previous month' },
              { key: 'this', label: 'This month' },
              { key: 'custom', label: 'Custom range' },
            ].map(({ key, label }) => (
              <button key={key} type="button"
                      onClick={() => applyPreset(key)}
                      className={`btn btn-sm ${preset === key ? 'btn-primary' : 'btn-secondary'}`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="form-row-2">
            <div className="field-group">
              <label className="field-label">From</label>
              <input className="form-input" type="date" value={fromDate}
                     onChange={(e) => { setFromDate(e.target.value); setPreset('custom'); }} />
            </div>
            <div className="field-group">
              <label className="field-label">To</label>
              <input className="form-input" type="date" value={toDate}
                     onChange={(e) => { setToDate(e.target.value); setPreset('custom'); }} />
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="btn btn-teller"
                  onClick={() => onSync(fromDate, toDate)}
                  disabled={!fromDate || !toDate || fromDate > toDate}
          >
            Sync {fromDate} → {toDate}
          </button>
        </div>
      </div>
    </Backdrop>
  );
}
