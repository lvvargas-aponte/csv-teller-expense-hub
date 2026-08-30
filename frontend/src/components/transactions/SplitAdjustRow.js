import React, { useState } from 'react';
import { fmt$, calculateHalf } from '../../utils/formatting';
import {
  parseDollars, parsePercent, round2, shareOf, remainderOf, percentOf,
} from '../../utils/splitMath';

export default function SplitAdjustRow({ txn, otherPersonName, colSpan, onSave, onClose }) {
  const total = Number(txn.amount) || 0;
  const half  = calculateHalf(total);
  const initialP1 = txn.is_shared ? Number(txn.person_1_owes ?? half) : half;
  const initialP2 = txn.is_shared ? Number(txn.person_2_owes ?? half) : half;
  const initialPct = total > 0 ? percentOf(total, initialP1) : 50;

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
    const youAmt = shareOf(total, p);
    setYou(fmt$(youAmt));
    setOther(fmt$(remainderOf(total, youAmt)));
  };

  const onYouChange = (e) => {
    const v = e.target.value;
    setYou(v);
    const youAmt = parseDollars(v);
    if (total > 0) setPct(String(percentOf(total, youAmt)));
    setOther(fmt$(remainderOf(total, youAmt)));
  };

  const onOtherChange = (e) => {
    const v = e.target.value;
    setOther(v);
    const otherAmt = parseDollars(v);
    if (total > 0) setPct(String(percentOf(total, total - otherAmt)));
  };

  const fillFiftyFifty = () => {
    setPct('50');
    setYou(fmt$(half));
    setOther(fmt$(remainderOf(total, half)));
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
