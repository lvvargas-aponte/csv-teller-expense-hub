import React, { useState } from 'react';
import { fmt$, calculateHalf } from '../../utils/formatting';

const parseDollars = (s) => {
  const n = parseFloat(String(s).replace(/[^0-9.-]/g, ''));
  return isNaN(n) ? 0 : n;
};

export default function SplitAdjustRow({ txn, otherPersonName, colSpan, onSave, onClose }) {
  const half = calculateHalf(txn.amount);
  const initialP1 = txn.is_shared ? Number(txn.person_1_owes ?? half) : half;
  const initialP2 = txn.is_shared ? Number(txn.person_2_owes ?? half) : half;

  const [you,   setYou]   = useState(fmt$(initialP1));
  const [other, setOther] = useState(fmt$(initialP2));
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await onSave({
        person_1_owes: parseFloat(parseDollars(you).toFixed(2)),
        person_2_owes: parseFloat(parseDollars(other).toFixed(2)),
      });
    } finally {
      setSaving(false);
    }
  };

  const onKey = (e) => {
    if (e.key === 'Enter')  { e.preventDefault(); save(); }
    if (e.key === 'Escape') { e.preventDefault(); onClose(); }
  };

  return (
    <tr className="tx-adj-row">
      <td colSpan={colSpan}>
        <div className="tx-adj-inner">
          <span className="tx-adj-label">Adjust split</span>
          <span className="tx-adj-note">Total: {fmt$(txn.amount)}</span>
          <span className="tx-adj-mini-label">You pay</span>
          <input
            className="tx-adj-input"
            value={you}
            onChange={(e) => setYou(e.target.value)}
            onKeyDown={onKey}
            autoFocus
            aria-label="You pay"
          />
          <span className="tx-adj-mini-label">{otherPersonName} pays</span>
          <input
            className="tx-adj-input"
            value={other}
            onChange={(e) => setOther(e.target.value)}
            onKeyDown={onKey}
            aria-label={`${otherPersonName} pays`}
          />
          <button type="button" className="tx-adj-save" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button type="button" className="tx-adj-close" onClick={onClose} aria-label="Close adjuster">✕</button>
        </div>
      </td>
    </tr>
  );
}
