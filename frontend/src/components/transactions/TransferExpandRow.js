import React, { useEffect, useState } from 'react';
import { getBalancesSummary } from '../../api/balances';

export default function TransferExpandRow({ txn, colSpan, onSave, onClose }) {
  const [value, setValue] = useState(txn.transfer_to_account_id || '');
  const [saving, setSaving] = useState(false);
  const [manualAccounts, setManualAccounts] = useState(null);
  const [error, setError] = useState(null);

  // Load-once: row mounts on expand, manual accounts are stable for its lifetime.
  useEffect(() => {
    getBalancesSummary(false)
      .then((r) => {
        const accounts = (r.data?.accounts || []).filter((a) => a.manual);
        setManualAccounts(accounts);
      })
      .catch(() => setError('Could not load accounts.'));
  }, []);

  const save = async () => {
    setSaving(true);
    try { await onSave(value); } finally { setSaving(false); }
  };

  const onKey = (e) => { if (e.key === 'Escape') { e.preventDefault(); onClose(); } };

  return (
    <tr className="tx-note-row">
      <td colSpan={colSpan}>
        <div className="tx-note-inner">
          <span className="tx-note-label">Transfer to</span>
          {manualAccounts === null && !error && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Loading accounts…</span>}
          {error && <span style={{ fontSize: 12, color: 'var(--bad-text)' }}>{error}</span>}
          {manualAccounts !== null && (
            <select
              className="tx-note-input"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={onKey}
              autoFocus
              aria-label="Transfer destination account"
            >
              <option value="">— Not a transfer —</option>
              {manualAccounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.institution ? `${a.institution} · ${a.name}` : a.name}
                </option>
              ))}
            </select>
          )}
          <button type="button" className="tx-note-save" onClick={save} disabled={saving || manualAccounts === null}>
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button type="button" className="tx-note-close" onClick={onClose} aria-label="Close transfer">✕</button>
        </div>
      </td>
    </tr>
  );
}
