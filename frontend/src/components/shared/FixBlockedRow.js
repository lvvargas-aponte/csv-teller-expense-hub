import React, { useState } from 'react';
import { fmt$, calculateHalf } from '../../utils/formatting';
import {
  parseDollars, parsePercent, round2, shareOf, remainderOf, percentOf,
} from '../../utils/splitMath';

// Repairing a blocked row where it is reported, rather than sending someone to
// Transactions to find it again. Which editor appears is driven by the
// backend's ``blocked_kind`` — the same check order a sync itself applies — so
// the form always addresses the reason sync would actually refuse on first.

function SplitFields({ total, peerName, iPaid, value, onChange }) {
  const half = calculateHalf(total);
  const mineFirst = iPaid;

  const setFromPct = (next) => {
    const p = parsePercent(next);
    if (p === null) return onChange({ ...value, pct: next });
    const first = shareOf(total, p);
    onChange({ pct: next, first: fmt$(first), second: fmt$(remainderOf(total, first)) });
  };

  const setFirst = (raw) => {
    const amt = parseDollars(raw);
    onChange({
      pct: total > 0 ? String(percentOf(total, amt)) : value.pct,
      first: raw,
      second: fmt$(remainderOf(total, amt)),
    });
  };

  const setSecond = (raw) => {
    const amt = parseDollars(raw);
    onChange({
      pct: total > 0 ? String(percentOf(total, total - amt)) : value.pct,
      first: fmt$(remainderOf(total, amt)),
      second: raw,
    });
  };

  const fillHalf = () =>
    onChange({ pct: '50', first: fmt$(half), second: fmt$(remainderOf(total, half)) });

  return (
    <>
      <span className="sh-fix-note">Total {fmt$(total)}</span>
      <button type="button" className="sh-mini" onClick={fillHalf}>50/50</button>

      <span className="sh-fix-field">
        <label className="sh-fix-label" htmlFor="fix-pct">
          {mineFirst ? 'Your' : `${peerName}'s`} %
        </label>
        <input
          id="fix-pct"
          className="sh-fix-input sh-fix-input--pct"
          value={value.pct}
          onChange={(e) => setFromPct(e.target.value)}
          inputMode="decimal"
        />
      </span>

      <span className="sh-fix-field">
        <label className="sh-fix-label" htmlFor="fix-first">
          {mineFirst ? 'You pay' : `${peerName} pays`}
        </label>
        <input
          id="fix-first"
          className="sh-fix-input"
          value={value.first}
          onChange={(e) => setFirst(e.target.value)}
        />
      </span>

      <span className="sh-fix-field">
        <label className="sh-fix-label" htmlFor="fix-second">
          {mineFirst ? `${peerName} pays` : 'You pay'}
        </label>
        <input
          id="fix-second"
          className="sh-fix-input"
          value={value.second}
          onChange={(e) => setSecond(e.target.value)}
        />
      </span>
    </>
  );
}

export default function FixBlockedRow({
  row, peerName, personNames, mySlot, onSave, onCancel,
}) {
  const kind = row.blocked_kind;
  const editable = row.editable || {};
  const total = Math.abs(Number(editable.raw_amount) || Number(row.amount) || 0);

  // Whose money is whose comes from the slot the backend already resolved.
  // Matching `who` against a name here would be wrong twice over: a blank
  // `who` means us, and this instance is not necessarily person 1.
  const payerSlot = row.payer_slot ?? mySlot;
  const iPaid = payerSlot === mySlot;
  const payerIsPerson1 = payerSlot === 1;

  const half = calculateHalf(total);
  const [split, setSplit] = useState({
    pct: '50',
    first: fmt$(half),
    second: fmt$(remainderOf(total, half)),
  });
  // Blank when the payer is what's wrong: the stored name is precisely the one
  // sync could not resolve, so offering it back as the default would let Save
  // "fix" the row to the value that blocked it.
  const [who, setWho] = useState(kind === 'who' ? '' : (row.who || ''));
  const [date, setDate] = useState(editable.raw_date || '');
  const [amount, setAmount] = useState(
    editable.raw_amount === null || editable.raw_amount === undefined
      ? ''
      : String(editable.raw_amount),
  );
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState(null);

  const patchFor = () => {
    if (kind === 'split') {
      const first = round2(parseDollars(split.first));
      const second = round2(parseDollars(split.second));
      if (first <= 0 && second <= 0) {
        return { error: 'One of you has to owe something for this to publish.' };
      }
      // person_1_owes / person_2_owes are absolute slots, not "mine / theirs":
      // `first` is always the payer's share, so it lands on the payer's slot.
      return {
        patch: {
          is_shared: true,
          person_1_owes: payerIsPerson1 ? first : second,
          person_2_owes: payerIsPerson1 ? second : first,
        },
      };
    }
    if (kind === 'who') {
      if (who !== personNames.person_1 && who !== personNames.person_2) {
        return { error: 'Pick who paid.' };
      }
      return { patch: { who } };
    }
    if (kind === 'date') {
      if (!date) return { error: 'Pick a date.' };
      return { patch: { date } };
    }
    if (kind === 'amount') {
      const n = parseFloat(amount);
      if (!Number.isFinite(n)) return { error: 'Enter the amount as a number.' };
      return { patch: { amount: n } };
    }
    return { error: 'This one has to be fixed in Transactions.' };
  };

  const save = async () => {
    const { patch, error } = patchFor();
    if (error) return setProblem(error);
    setProblem(null);
    setSaving(true);
    try {
      await onSave(patch);
    } catch (e) {
      setProblem('Could not save that — please try again.');
    } finally {
      setSaving(false);
    }
  };

  const onKey = (e) => {
    if (e.key === 'Enter') { e.preventDefault(); save(); }
    if (e.key === 'Escape') { e.preventDefault(); onCancel(); }
  };

  return (
    <div className="sh-fix" role="presentation" onKeyDown={onKey}>
      <span className="sh-fix-title">
        {kind === 'split' && 'Set the split'}
        {kind === 'who' && 'Who paid?'}
        {kind === 'date' && 'Fix the date'}
        {kind === 'amount' && 'Fix the amount'}
      </span>

      {kind === 'split' && (
        <SplitFields
          total={total}
          peerName={peerName}
          iPaid={iPaid}
          value={split}
          onChange={setSplit}
        />
      )}

      {kind === 'who' && (
        <>
          <span className="sh-fix-field">
          <label className="sh-fix-label" htmlFor="fix-who">Paid by</label>
          <select
            id="fix-who"
            className="sh-fix-input"
            value={who}
            onChange={(e) => setWho(e.target.value)}
          >
            <option value="">Choose…</option>
            <option value={personNames.person_1}>{personNames.person_1}</option>
            <option value={personNames.person_2}>{personNames.person_2}</option>
          </select>
          </span>
          <span className="sh-fix-note">
            Sync fills the owes column for whoever did not pay.
          </span>
        </>
      )}

      {kind === 'date' && (
        <>
          <label className="sh-fix-label" htmlFor="fix-date">Date</label>
          <input
            id="fix-date"
            type="date"
            className="sh-fix-input"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
          <span className="sh-fix-note">
            The date decides which month settles this row.
          </span>
        </>
      )}

      {kind === 'amount' && (
        <>
          <label className="sh-fix-label" htmlFor="fix-amount">Amount</label>
          <input
            id="fix-amount"
            className="sh-fix-input"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            inputMode="decimal"
            placeholder="-24.50"
          />
          <span className="sh-fix-note">
            Negative for money out, the way it was imported.
          </span>
        </>
      )}

      {problem && <span className="sh-fix-problem" role="alert">{problem}</span>}

      <span className="sh-fix-actions">
        <button
          type="button"
          className="sh-mini sh-mini--go"
          onClick={save}
          disabled={saving}
        >{saving ? 'Saving…' : 'Save'}</button>
        <button type="button" className="sh-mini" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </span>
    </div>
  );
}
