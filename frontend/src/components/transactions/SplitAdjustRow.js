import React, { useState } from 'react';
import { fmt$, calculateHalf } from '../../utils/formatting';

const parseDollars = (s) => {
  const n = parseFloat(String(s).replace(/[^0-9.-]/g, ''));
  return isNaN(n) ? 0 : n;
};

const parsePercent = (s) => {
  const n = parseFloat(String(s).replace(/[^0-9.]/g, ''));
  if (isNaN(n)) return null;
  return Math.max(0, Math.min(100, n));
};

const round2 = (n) => Math.round(n * 100) / 100;

export default function SplitAdjustRow({ txn, otherPersonName, colSpan, onSave, onClose }) {
  const total = Number(txn.amount) || 0;
  const half  = calculateHalf(total);
  const initialP1 = txn.is_shared ? Number(txn.person_1_owes ?? half) : half;
  const initialP2 = txn.is_shared ? Number(txn.person_2_owes ?? half) : half;
  const initialPct = total > 0 ? round2((initialP1 / total) * 100) : 50;

  const [you,    setYou]    = useState(fmt$(initialP1));
  const [other,  setOther]  = useState(fmt$(initialP2));
  const [pct,    setPct]    = useState(String(initialPct));
  const [saving, setSaving] = useState(false);

  // Percentage drives both dollar fields. Editing dollars only updates pct
  // when "You pay" changes, so typing in the second field doesn't yank the
  // first one around mid-edit.
  const applyPct = (next) => {
    const p = parsePercent(next);
    setPct(next);
    if (p === null) return;
    const youAmt = round2((total * p) / 100);
    setYou(fmt$(youAmt));
    setOther(fmt$(round2(total - youAmt)));
  };

  const onYouChange = (e) => {
    const v = e.target.value;
    setYou(v);
    const youAmt = parseDollars(v);
    if (total > 0) setPct(String(round2((youAmt / total) * 100)));
    setOther(fmt$(round2(total - youAmt)));
  };

  const onOtherChange = (e) => {
    const v = e.target.value;
    setOther(v);
    const otherAmt = parseDollars(v);
    if (total > 0) setPct(String(round2(((total - otherAmt) / total) * 100)));
  };

  const fillFiftyFifty = () => {
    setPct('50');
    setYou(fmt$(half));
    setOther(fmt$(round2(total - half)));
  };

  const save = async () => {
    setSaving(true);
    try {
      await onSave({
        person_1_owes: round2(parseDollars(you)),
        person_2_owes: round2(parseDollars(other)),
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
          <span className="tx-adj-note">Total: {fmt$(total)}</span>

          <button
            type="button"
            className="tx-adj-quick"
            onClick={fillFiftyFifty}
            title="Reset to 50/50"
          >50/50</button>

          <span className="tx-adj-mini-label">You %</span>
          <input
            className="tx-adj-input tx-adj-input--pct"
            value={pct}
            onChange={(e) => applyPct(e.target.value)}
            onKeyDown={onKey}
            inputMode="decimal"
            aria-label="Your percentage"
          />

          <span className="tx-adj-mini-label">You pay</span>
          <input
            className="tx-adj-input"
            value={you}
            onChange={onYouChange}
            onKeyDown={onKey}
            autoFocus
            aria-label="You pay"
          />
          <span className="tx-adj-mini-label">{otherPersonName} pays</span>
          <input
            className="tx-adj-input"
            value={other}
            onChange={onOtherChange}
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
