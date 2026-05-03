import React, { useState, useEffect } from 'react';
import Backdrop from '../ui/Backdrop';
import Field from '../ui/Field';
import Spin from '../ui/Spin';
import { getBalancesSummary } from '../../api/balances';
import { Z_BACKDROP_DIALOG } from '../../utils/zIndex';

const TODAY = () => new Date().toISOString().slice(0, 10);

export default function UploadCsvModal({ file, onSubmit, onClose }) {
  const [accounts, setAccounts] = useState([]);
  const [loadingAccounts, setLoadingAccounts] = useState(true);

  // "skip" | "<account_id>" | "__new__"
  const [target, setTarget] = useState('skip');

  const [newAcct, setNewAcct] = useState({
    institution: '', name: '', type: 'depository',
  });

  const [statementBalance, setStatementBalance] = useState('');
  const [statementDate,    setStatementDate]    = useState(TODAY());

  const [uploading, setUploading] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    getBalancesSummary()
      .then((r) => setAccounts((r.data.accounts || []).filter((a) => a.manual)))
      .catch(() => setAccounts([]))
      .finally(() => setLoadingAccounts(false));
  }, []);

  const needsNewAcctFields = target === '__new__';
  const showStatementFields = target !== 'skip';

  // Only the "create new account" path gates submit on extra fields; skip
  // and existing-account selections can submit as soon as a file is present.
  const canSubmit = target !== '__new__'
    || (newAcct.institution.trim() && newAcct.name.trim());

  const handleSubmit = async (e) => {
    e.preventDefault();
    setUploading(true);
    setErr(null);

    const fd = new FormData();
    fd.append('file', file);

    if (target !== 'skip') {
      if (target === '__new__') {
        fd.append('institution', newAcct.institution.trim());
        fd.append('name',        newAcct.name.trim());
        fd.append('type',        newAcct.type);
      } else {
        fd.append('account_id', target);
      }
      if (statementBalance !== '' && !Number.isNaN(parseFloat(statementBalance))) {
        fd.append('statement_balance', parseFloat(statementBalance));
        fd.append('statement_date',    `${statementDate}T00:00:00+00:00`);
      }
    }

    try {
      await onSubmit(fd);
    } catch (e2) {
      setErr(e2.response?.data?.detail || e2.message || 'Upload failed');
      setUploading(false);
    }
  };

  return (
    <Backdrop onClose={uploading ? undefined : onClose} zIndex={Z_BACKDROP_DIALOG}>
      <div className="modal modal--sm">
        <div className="modal-header">
          <div className="modal-header-text">
            <div className="modal-title">Upload CSV</div>
            <div className="modal-sub">{file?.name}</div>
          </div>
          {!uploading && (
            <button type="button" className="close-btn" aria-label="Close" onClick={onClose}>✕</button>
          )}
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="field-group">
              <label className="field-label">Attach to an account</label>
              {loadingAccounts ? (
                <div style={{ padding: '6px 0' }}><Spin /> Loading accounts…</div>
              ) : (
                <select className="form-input"
                        value={target}
                        onChange={(e) => setTarget(e.target.value)}>
                  <option value="skip">Skip — import transactions only</option>
                  {accounts.length > 0 && (
                    <optgroup label="Existing accounts">
                      {accounts.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.institution} · {a.name}
                        </option>
                      ))}
                    </optgroup>
                  )}
                  <option value="__new__">+ Create new account</option>
                </select>
              )}
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                Attaching transactions to an account lets dashboards group them by card
                and record a balance snapshot for net-worth history.
              </div>
            </div>

            {needsNewAcctFields && (
              <div className="form-row-2" style={{ marginTop: 12 }}>
                <Field label="Institution">
                  <input className="form-input" type="text" placeholder="e.g. Discover"
                         value={newAcct.institution}
                         onChange={(e) => setNewAcct((a) => ({ ...a, institution: e.target.value }))} />
                </Field>
                <Field label="Account Name">
                  <input className="form-input" type="text" placeholder="e.g. Discover It"
                         value={newAcct.name}
                         onChange={(e) => setNewAcct((a) => ({ ...a, name: e.target.value }))} />
                </Field>
                <div style={{ gridColumn: '1 / -1' }}>
                  <Field label="Type">
                    <select className="form-input" value={newAcct.type}
                            onChange={(e) => setNewAcct((a) => ({ ...a, type: e.target.value }))}>
                      <option value="depository">Checking / Savings</option>
                      <option value="credit">Credit Card</option>
                    </select>
                  </Field>
                </div>
              </div>
            )}

            {showStatementFields && (
              <div className="form-row-2" style={{ marginTop: 12 }}>
                <Field label="Statement Closing Balance ($)"
                       hint="For a credit card, enter the amount owed as a positive number.">
                  <input className="form-input" type="number" step="0.01"
                         placeholder="optional"
                         value={statementBalance}
                         onChange={(e) => setStatementBalance(e.target.value)} />
                </Field>
                <Field label="Statement Date">
                  <input className="form-input" type="date"
                         value={statementDate}
                         onChange={(e) => setStatementDate(e.target.value)} />
                </Field>
              </div>
            )}

            {err && (
              <div style={{ color: '#f87171', fontSize: 13, marginTop: 8 }}>{err}</div>
            )}
          </div>

          <div className="modal-footer" style={{ justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" className="btn btn-secondary"
                    onClick={onClose} disabled={uploading}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary"
                    disabled={uploading || !canSubmit}>
              {uploading ? <><Spin /> Uploading…</> : 'Upload'}
            </button>
          </div>
        </form>
      </div>
    </Backdrop>
  );
}
