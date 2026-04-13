import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import Backdrop from './Backdrop';
import Spin from './Spin';
import { prevMonthRange, thisMonthRange } from '../utils/formatting';

const API = process.env.REACT_APP_BACKEND_URL || '';

export default function SyncModal({ onSync, onClose }) {
  const pm = prevMonthRange();
  const tm = thisMonthRange();
  const [fromDate, setFromDate] = useState(pm.from);
  const [toDate,   setToDate]   = useState(pm.to);
  const [preset,   setPreset]   = useState('prev');

  const [accounts,  setAccounts]  = useState([]);
  const [acctLoad,  setAcctLoad]  = useState(true);
  // Set of selected account IDs; null means "all" (default before accounts load)
  const [selected,  setSelected]  = useState(null);

  useEffect(() => {
    axios.get(`${API}/api/accounts`)
      .then((res) => {
        // Only include healthy (non-error) accounts
        const healthy = res.data.filter((a) => !a._connection_error);
        setAccounts(healthy);
        setSelected(new Set(healthy.map((a) => a.id)));
      })
      .catch(() => {
        // If fetch fails just leave selected as null (all)
      })
      .finally(() => setAcctLoad(false));
  }, []);

  const applyPreset = (p) => {
    setPreset(p);
    if (p === 'prev') { setFromDate(pm.from); setToDate(pm.to); }
    if (p === 'this') { setFromDate(tm.from); setToDate(tm.to); }
  };

  const allChecked = selected !== null && selected.size === accounts.length;
  const someChecked = selected !== null && selected.size > 0 && !allChecked;

  const toggleAll = () => {
    if (allChecked || someChecked) {
      setSelected(new Set());
    } else {
      setSelected(new Set(accounts.map((a) => a.id)));
    }
  };

  const toggleAccount = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Group accounts by institution for display
  const byInstitution = useMemo(() => accounts.reduce((groups, acct) => {
    const inst = acct.institution?.name || '—';
    if (!groups[inst]) groups[inst] = [];
    groups[inst].push(acct);
    return groups;
  }, {}), [accounts]);

  const handleSync = () => {
    // null selected means accounts failed to load — send no filter (sync all)
    const accountIds = selected !== null ? [...selected] : null;
    onSync(fromDate, toDate, accountIds);
  };

  const noneSelected = selected !== null && selected.size === 0;

  return (
    <Backdrop onClose={onClose} zIndex={210}>
      <div className="modal modal--md">
        <div className="modal-header">
          <div className="modal-header-text">
            <div className="modal-title">🏦 Sync Bank Transactions</div>
            <div className="modal-sub">Choose a date range and accounts to pull from Teller</div>
          </div>
          <button type="button" className="close-btn" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          {/* ── Date range ── */}
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

          {/* ── Account selection ── */}
          <div style={{ marginTop: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <span className="field-label" style={{ margin: 0 }}>Accounts</span>
              {acctLoad
                ? <Spin />
                : accounts.length > 0 && (
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer', color: 'var(--text-muted)' }}>
                    <input
                      type="checkbox"
                      checked={allChecked}
                      ref={(el) => { if (el) el.indeterminate = someChecked; }}
                      onChange={toggleAll}
                    />
                    All
                  </label>
                )
              }
            </div>

            {acctLoad ? (
              <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Loading accounts…</div>
            ) : accounts.length === 0 ? (
              <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>No accounts found — will sync all.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {Object.entries(byInstitution).map(([inst, instAccounts]) => (
                  <div key={inst}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      {inst}
                    </div>
                    {instAccounts.map((acct) => (
                      <label key={acct.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, cursor: 'pointer', padding: '3px 0' }}>
                        <input
                          type="checkbox"
                          checked={selected?.has(acct.id) ?? true}
                          onChange={() => toggleAccount(acct.id)}
                        />
                        <span>{acct.name}</span>
                        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                          {acct.subtype || acct.type}
                        </span>
                      </label>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="btn btn-teller"
                  onClick={handleSync}
                  disabled={!fromDate || !toDate || fromDate > toDate || noneSelected}
          >
            Sync {fromDate} → {toDate}
            {selected !== null && accounts.length > 0 && !allChecked && (
              <span style={{ marginLeft: 6, opacity: 0.75 }}>({selected.size} account{selected.size !== 1 ? 's' : ''})</span>
            )}
          </button>
        </div>
      </div>
    </Backdrop>
  );
}
