import React, { useState } from 'react';
import { fmt$, fmtDate } from '../../utils/formatting';

function formatOwesCell(value) {
  return value === null || value === undefined ? '—' : fmt$(value);
}

export default function SharedRow({ row, onDispute }) {
  const isMe = row.owner === 'me';
  const hasDispute = row.dispute_flag === 'Y';
  const rowClass = `shared-row${row.publishable === false ? ' shared-row--blocked' : ''}`;

  const [formOpen, setFormOpen] = useState(false);
  const [note, setNote] = useState('');
  const [editingFlag, setEditingFlag] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const openRaise = () => { setNote(''); setEditingFlag(null); setFormOpen(true); };
  const openEdit = () => { setNote(row.dispute_note || ''); setEditingFlag(row.dispute_flag); setFormOpen(true); };
  const cancel = () => setFormOpen(false);

  const submit = async () => {
    setSubmitting(true);
    try {
      await onDispute(row.transaction_id, { flag: editingFlag || 'Y', note });
      setFormOpen(false);
    } catch (e) {
      // error already surfaced by the caller; keep the form open with the note
    } finally {
      setSubmitting(false);
    }
  };

  const withdraw = async () => {
    setSubmitting(true);
    try {
      await onDispute(row.transaction_id, { flag: null, note: null });
    } catch (e) {
      // error already surfaced by the caller
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <tr className={rowClass}>
      <td className="shared-td-owner">
        <span
          className={`shared-owner-dot${isMe ? ' shared-owner-dot--me' : ' shared-owner-dot--peer'}`}
          aria-hidden="true"
        >
          {isMe ? '●' : '○'}
        </span>
        <span className="shared-owner-name">{row.owner_name}</span>
      </td>
      <td className="shared-td-date">{fmtDate(row.date)}</td>
      <td className="shared-td-desc">
        {row.description}
        {isMe && hasDispute && (
          <span
            className="shared-flag shared-flag--dispute"
            title={`${row.dispute_by} is disputing this: ${row.dispute_note}`}
          >
            ⚑ {row.dispute_by} is disputing this: {row.dispute_note}
          </span>
        )}
        {!isMe && hasDispute && !formOpen && (
          <span
            className="shared-flag shared-flag--dispute"
            title={`You disputed this: ${row.dispute_note}`}
          >
            ⚑ You disputed this: {row.dispute_note}
          </span>
        )}
        {!isMe && hasDispute && !formOpen && (
          <span className="shared-dispute-actions">
            <button
              type="button"
              className="shared-dispute-btn"
              onClick={openEdit}
              aria-label={`Edit dispute for ${row.description}`}
            >Edit</button>
            <button
              type="button"
              className="shared-dispute-btn"
              onClick={withdraw}
              disabled={submitting}
              aria-label={`Withdraw dispute for ${row.description}`}
            >Withdraw</button>
          </span>
        )}
        {!isMe && !hasDispute && !formOpen && (
          <button
            type="button"
            className="shared-dispute-btn"
            onClick={openRaise}
            aria-label={`Dispute ${row.description}`}
          >Dispute</button>
        )}
        {!isMe && formOpen && (
          <span className="shared-dispute-form">
            <label htmlFor={`dispute-note-${row.transaction_id}`} className="shared-dispute-label">
              Dispute note
            </label>
            <input
              id={`dispute-note-${row.transaction_id}`}
              className="shared-dispute-input"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              autoFocus
            />
            <button
              type="button"
              className="shared-dispute-btn shared-dispute-btn--primary"
              onClick={submit}
              disabled={submitting}
            >{submitting ? 'Saving…' : 'Save'}</button>
            <button
              type="button"
              className="shared-dispute-btn"
              onClick={cancel}
              disabled={submitting}
            >Cancel</button>
          </span>
        )}
        {row.publishable === false && (
          <span className="shared-flag shared-flag--blocked" title={row.blocked_reason}>
            ⚠ {row.blocked_reason}
          </span>
        )}
      </td>
      <td className="shared-td-amt">{fmt$(row.amount)}</td>
      <td className="shared-td-amt">{formatOwesCell(row.you_owe)}</td>
      <td className="shared-td-amt">{formatOwesCell(row.they_owe)}</td>
    </tr>
  );
}
